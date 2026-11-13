"""Tomadores, prestadores e contratos (só a plataforma). A unicidade e as chaves estrangeiras são garantidas
pelo banco: o INSERT roda direto e a violação da constraint vira 409/404/422 (sem SELECT antes, sem corrida)."""
import psycopg
from fastapi import HTTPException

from app import config
from app.escopo import condicao_contrato
from app.routers.auth.actions import UsuarioContexto
from app.routers.organizacoes.schemas import NovoContrato, NovoPrestador, NovoTomador

_COLUNAS_TOMADOR = "id, nome, cnpj, ativo, criado_em"
_COLUNAS_PRESTADOR = "id, cnpj, razao_social, ativo, criado_em"
_SELECT_CONTRATO = """
    SELECT c.id, c.tomador_id, c.prestador_id, c.ativo, c.vigencia_inicio, c.vigencia_fim, c.criado_em,
           t.nome, t.ativo, p.razao_social, p.cnpj, p.ativo
      FROM contrato c
      JOIN tomador t ON t.id = c.tomador_id
      JOIN prestador p ON p.id = c.prestador_id
"""


def _tomador(l) -> dict:
    return dict(zip(("id", "nome", "cnpj", "ativo", "criado_em"), l))


def _prestador(l) -> dict:
    return dict(zip(("id", "cnpj", "razao_social", "ativo", "criado_em"), l))


def _contrato(l) -> dict:
    return dict(zip(("id", "tomador_id", "prestador_id", "ativo", "vigencia_inicio", "vigencia_fim", "criado_em",
                     "tomador_nome", "tomador_ativo", "prestador_razao_social", "prestador_cnpj", "prestador_ativo"), l))


def _existente(consulta: str, args: tuple) -> int | None:
    """Id da linha que causou o conflito (só para a mensagem); None se já sumiu."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        linha = conn.execute(consulta, args).fetchone()
    return linha[0] if linha else None


def _conflito(entidade: str, onde: str, id_: int | None) -> HTTPException:
    return HTTPException(409, f"já existe {entidade} {id_} com {onde}" if id_ else f"já existe {entidade} com {onde}")


def criar_tomador(corpo: NovoTomador) -> dict:
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:
            return _tomador(conn.execute(
                f"INSERT INTO tomador (nome, cnpj) VALUES (%s, %s) RETURNING {_COLUNAS_TOMADOR}",
                (corpo.nome, corpo.cnpj)).fetchone())
    except psycopg.errors.UniqueViolation as e:
        if e.diag.constraint_name == "tomador_cnpj_key":
            raise _conflito("o tomador", f"o CNPJ {corpo.cnpj}",
                            _existente("SELECT id FROM tomador WHERE cnpj = %s", (corpo.cnpj,)))
        raise _conflito("o tomador", f"o nome '{corpo.nome}' (sem diferenciar caixa nem espaços nas pontas)",
                        _existente("SELECT id FROM tomador WHERE lower(btrim(nome)) = lower(btrim(%s))", (corpo.nome,)))


def listar_tomadores() -> list[dict]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        return [_tomador(l) for l in conn.execute(f"SELECT {_COLUNAS_TOMADOR} FROM tomador ORDER BY id")]


def criar_prestador(corpo: NovoPrestador) -> dict:
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:
            return _prestador(conn.execute(
                f"INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) RETURNING {_COLUNAS_PRESTADOR}",
                (corpo.cnpj, corpo.razao_social)).fetchone())
    except psycopg.errors.UniqueViolation:
        raise _conflito("o prestador", f"o CNPJ {corpo.cnpj}",
                        _existente("SELECT id FROM prestador WHERE cnpj = %s", (corpo.cnpj,)))


def listar_prestadores() -> list[dict]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        return [_prestador(l) for l in conn.execute(f"SELECT {_COLUNAS_PRESTADOR} FROM prestador ORDER BY id")]


def criar_contrato(corpo: NovoContrato) -> dict:
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:
            id_ = conn.execute(
                "INSERT INTO contrato (tomador_id, prestador_id, vigencia_inicio, vigencia_fim) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (corpo.tomador_id, corpo.prestador_id, corpo.vigencia_inicio, corpo.vigencia_fim)).fetchone()[0]
            return _contrato(conn.execute(_SELECT_CONTRATO + " WHERE c.id = %s", (id_,)).fetchone())
    except psycopg.errors.UniqueViolation:
        raise _conflito("o contrato", f"o tomador {corpo.tomador_id} e o prestador {corpo.prestador_id}",
                        _existente("SELECT id FROM contrato WHERE tomador_id = %s AND prestador_id = %s",
                                   (corpo.tomador_id, corpo.prestador_id)))
    except psycopg.errors.ForeignKeyViolation as e:
        quem = "prestador" if "prestador" in (e.diag.constraint_name or "") else "tomador"
        id_ = corpo.prestador_id if quem == "prestador" else corpo.tomador_id
        raise HTTPException(404, f"{quem} {id_} não encontrado")
    except psycopg.errors.CheckViolation:  # contrato_vigencia_check (o schema já recusa antes; rede de segurança)
        raise HTTPException(422, "vigencia_fim não pode ser anterior a vigencia_inicio")


def listar_contratos(tomador_id: int | None = None, prestador_id: int | None = None, *,
                     usuario: UsuarioContexto) -> list[dict]:
    """Contratos no escopo de `usuario` (obrigatório), com filtros opcionais por tomador e prestador."""
    condicoes, args = [], []
    cond, cargs = condicao_contrato(usuario)
    condicoes.append(cond)
    args.extend(cargs)
    if tomador_id is not None:
        condicoes.append("c.tomador_id = %s")
        args.append(tomador_id)
    if prestador_id is not None:
        condicoes.append("c.prestador_id = %s")
        args.append(prestador_id)
    where = f" WHERE {' AND '.join(condicoes)}" if condicoes else ""
    with psycopg.connect(config.DATABASE_URL) as conn:
        return [_contrato(l) for l in conn.execute(_SELECT_CONTRATO + where + " ORDER BY c.id", args)]
