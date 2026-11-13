"""Escopo de acesso aos dados por nível de usuário. Único lugar que decide quem enxerga o quê; os routers só
declaram a dependência (por rota) ou passam o usuário às listagens.

- plataforma: tudo, leitura e escrita.
- tomador: SÓ LEITURA, lotes cujo contrato é do seu tomador (ativo ou não: é o histórico do cliente).
- prestador: leitura e escrita em lotes de contratos ATIVOS do seu prestador (com tomador e prestador ativos).
- Lote sem contrato: só plataforma. Fora do escopo = 404, igual a inexistente.

Listagens filtram na consulta SQL (`condicao_lote`, `condicao_contrato`); recurso por id passa pelas dependências
`lote_para_leitura`/`lote_para_escrita`/`documento_para_leitura`/`documento_para_escrita`."""
import psycopg
from fastapi import Depends, HTTPException, Request

from app import config
from app.routers.auth.actions import ID_MAX, UsuarioContexto, exigir_plataforma, exigir_usuario  # noqa: F401

METODOS_LEITURA = frozenset({"GET", "HEAD", "OPTIONS"})
_NEGADO_ESCRITA = "somente leitura: usuários do nível tomador não alteram dados"


def condicao_contrato(usuario: UsuarioContexto, c: str = "c", t: str = "t", p: str = "p") -> tuple[str, list]:
    """Condição SQL sobre contrato `c` já unido a tomador `t` e prestador `p`, e seus parâmetros."""
    if usuario.nivel == "plataforma":
        return "TRUE", []
    if usuario.nivel == "tomador":
        return f"({c}.tomador_id = %s AND {t}.ativo)", [usuario.tomador_id]
    if usuario.nivel == "prestador":
        return f"({c}.prestador_id = %s AND {c}.ativo AND {t}.ativo AND {p}.ativo)", [usuario.prestador_id]
    return "FALSE", []  # nível desconhecido: falha fechada


def condicao_lote(usuario: UsuarioContexto, l: str = "l") -> tuple[str, list]:
    """Condição SQL sobre a tabela `lote` (alias `l`): o lote está no escopo do usuário."""
    if usuario.nivel == "plataforma":
        return "TRUE", []
    cond, args = condicao_contrato(usuario, "ce", "te", "pe")
    return (f"EXISTS (SELECT 1 FROM contrato ce JOIN tomador te ON te.id = ce.tomador_id "
            f"JOIN prestador pe ON pe.id = ce.prestador_id WHERE ce.id = {l}.contrato_id AND {cond})"), args


def pode_convidar(usuario: UsuarioContexto, nivel: str, papel: str,
                  tomador_id: int | None, prestador_id: int | None) -> bool:
    """Único lugar que decide quem pode convidar quem. Hoje só a plataforma convida (qualquer nível e papel);
    o admin do tomador e o do prestador entram aqui, nos limites da própria organização."""
    return usuario.nivel == "plataforma"


def _id_valido(id_: int) -> bool:
    return 1 <= id_ <= ID_MAX


def _checar_escrita(usuario: UsuarioContexto, escrita: bool) -> None:
    if escrita and usuario.nivel not in ("plataforma", "prestador"):
        raise HTTPException(403, _NEGADO_ESCRITA)


def exigir_lote_no_escopo(conn, usuario: UsuarioContexto, lote_id: int, escrita: bool = False) -> None:
    """403 se o nível não pode escrever; 404 se o lote não existe ou está fora do escopo."""
    _checar_escrita(usuario, escrita)
    cond, args = condicao_lote(usuario, "l")
    if not _id_valido(lote_id) or conn.execute(
            f"SELECT 1 FROM lote l WHERE l.id = %s AND {cond}", [lote_id, *args]).fetchone() is None:
        raise HTTPException(404, "lote não encontrado")


def exigir_documento_no_escopo(conn, usuario: UsuarioContexto, documento_id: int, escrita: bool = False) -> None:
    """Idem para documento: vale o escopo do lote a que ele pertence."""
    _checar_escrita(usuario, escrita)
    cond, args = condicao_lote(usuario, "l")
    if not _id_valido(documento_id) or conn.execute(
            f"SELECT 1 FROM documento d JOIN lote l ON l.id = d.lote_id WHERE d.id = %s AND {cond}",
            [documento_id, *args]).fetchone() is None:
        raise HTTPException(404, "documento não encontrado")


def exigir_contrato_de_upload(conn, usuario: UsuarioContexto, contrato_id: int | None) -> None:
    """Prestador: contrato_id obrigatório (422) e tem que ser um contrato seu ativo (404). Plataforma: sem exigência
    aqui (a validação de existência/atividade é a de sempre). Tomador não chega aqui (403 antes)."""
    if usuario.nivel == "plataforma":
        return
    _checar_escrita(usuario, True)
    if contrato_id is None:
        raise HTTPException(422, "contrato_id é obrigatório para o upload")
    cond, args = condicao_contrato(usuario)
    if not _id_valido(contrato_id) or conn.execute(
            "SELECT 1 FROM contrato c JOIN tomador t ON t.id = c.tomador_id "
            f"JOIN prestador p ON p.id = c.prestador_id WHERE c.id = %s AND {cond}",
            [contrato_id, *args]).fetchone() is None:
        raise HTTPException(404, f"contrato {contrato_id} não encontrado")


# ---------- dependências do FastAPI ----------

def acesso_a_dados(request: Request, usuario: UsuarioContexto = Depends(exigir_usuario)) -> UsuarioContexto:
    """Nível dos routers de dados: qualquer usuário logado lê (filtrado); tomador nunca escreve (403)."""
    if usuario.nivel == "tomador" and request.method not in METODOS_LEITURA:
        raise HTTPException(403, _NEGADO_ESCRITA)
    return usuario


def _verificar(verificador, escrita: bool, id_: int, usuario: UsuarioContexto) -> int:
    with psycopg.connect(config.DATABASE_URL) as conn:
        verificador(conn, usuario, id_, escrita=escrita)
    return id_


def lote_para_leitura(lote_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados)) -> int:
    return _verificar(exigir_lote_no_escopo, False, lote_id, usuario)


def lote_para_escrita(lote_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados)) -> int:
    return _verificar(exigir_lote_no_escopo, True, lote_id, usuario)


def documento_para_leitura(documento_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados)) -> int:
    return _verificar(exigir_documento_no_escopo, False, documento_id, usuario)


def documento_para_escrita(documento_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados)) -> int:
    return _verificar(exigir_documento_no_escopo, True, documento_id, usuario)


# Dependências que fecham o acesso por recurso; a varredura de rotas exige uma delas em toda rota com id na URL.
DEPENDENCIAS_DE_RECURSO = (lote_para_leitura, lote_para_escrita, documento_para_leitura, documento_para_escrita)
