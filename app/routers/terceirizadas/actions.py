"""Cadastro de terceirizada pelo cliente. Uma transação: prestador (reutiliza o do mesmo CNPJ, sem alterar a razão
social), contrato ativo e, se o prestador ainda não tem acesso, o convite do administrador dele. A linha do prestador
fica travada até o commit, então cadastros simultâneos do mesmo CNPJ se serializam: um prestador, um contrato por
tomador e no máximo um convite."""
import psycopg
from fastapi import HTTPException

from app import config
from app.escopo import prestador_tem_convite_pendente, prestador_tem_usuario_ativo
from app.routers.auth.actions import UsuarioContexto
from app.routers.convites.actions import criar_na_transacao
from app.routers.terceirizadas.schemas import NovaTerceirizada


def _tomador_alvo(usuario: UsuarioContexto, corpo: NovaTerceirizada) -> int:
    if usuario.nivel == "plataforma":
        if corpo.tomador_id is None:
            raise HTTPException(422, "tomador_id é obrigatório para a plataforma")
        return corpo.tomador_id
    if usuario.nivel != "tomador" or usuario.papel != "admin" or usuario.tomador_id is None:
        raise HTTPException(403, "apenas o administrador do tomador cadastra terceirizadas")
    if corpo.tomador_id is not None and corpo.tomador_id != usuario.tomador_id:
        raise HTTPException(403, "tomador_id diferente do seu")
    return usuario.tomador_id


def _prestador_travado(conn, cnpj: str, razao_social: str) -> tuple:
    """(id, cnpj, razao_social, ativo) do prestador do CNPJ, criado se não existir, com a linha travada."""
    for _ in range(3):
        conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) ON CONFLICT (cnpj) DO NOTHING",
                     (cnpj, razao_social))
        linha = conn.execute("SELECT id, cnpj, razao_social, ativo FROM prestador WHERE cnpj = %s "
                             "FOR NO KEY UPDATE", (cnpj,)).fetchone()
        if linha:
            return linha
    raise HTTPException(503, "não foi possível cadastrar agora; tente de novo")


def cadastrar(corpo: NovaTerceirizada, usuario: UsuarioContexto) -> dict:
    tomador_id = _tomador_alvo(usuario, corpo)
    with psycopg.connect(config.DATABASE_URL) as conn:
        ativo = conn.execute("SELECT ativo FROM tomador WHERE id = %s", (tomador_id,)).fetchone()
        if ativo is None or not ativo[0]:
            raise HTTPException(404, "tomador não encontrado ou desativado")
        prestador_id, cnpj, razao_social, prestador_ativo = _prestador_travado(conn, corpo.cnpj, corpo.razao_social)
        if not prestador_ativo:
            raise HTTPException(409, "terceirizada desativada")
        contrato = conn.execute("INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s) "
                                "ON CONFLICT (tomador_id, prestador_id) DO NOTHING RETURNING id, ativo",
                                (tomador_id, prestador_id)).fetchone()
        if contrato is None:
            raise HTTPException(409, "terceirizada já cadastrada")
        convite = None
        if prestador_tem_usuario_ativo(conn, prestador_id):
            acesso = "ja_tem_acesso"
        elif prestador_tem_convite_pendente(conn, prestador_id):
            acesso = "convite_pendente"
        else:
            acesso = "convite_criado"
            c = criar_na_transacao(conn, corpo.email, "prestador", "admin", None, prestador_id, usuario.id)
            convite = {k: c[k] for k in ("id", "email", "expira_em", "token")}
    return {"contrato": {"id": contrato[0], "ativo": contrato[1]},
            "prestador": {"id": prestador_id, "cnpj": cnpj, "razao_social": razao_social},
            "acesso": acesso, "convite": convite}
