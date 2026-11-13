"""Convites: link de uso único. O token (secrets.token_urlsafe) só existe na resposta da criação; o banco guarda
o sha256. As rotas públicas respondem 404 com o MESMO corpo para token inexistente, usado, expirado ou de
organização desativada. O token nunca vai para log, mensagem de erro nem resposta de listagem."""
import hashlib
import secrets
from datetime import timedelta

import psycopg
from fastapi import HTTPException

from app import config, senhas
from app.escopo import motivo_recusa_convite, prestador_tem_usuario_ativo
from app.routers.auth.actions import UsuarioContexto, emitir_token
from app.routers.convites.schemas import AceiteIn, NovoConvite

NAO_ENCONTRADO = "convite inválido, usado ou expirado"
TOKEN_MAX = 200  # token_urlsafe(32) tem 43 caracteres; acima disto nem consulta o banco

# Organização do convite ainda ativa (convite de plataforma não tem organização: conta como ativa).
_ORG_ATIVA = "COALESCE((SELECT ativo FROM tomador WHERE id = c.tomador_id), " \
             "(SELECT ativo FROM prestador WHERE id = c.prestador_id), true)"
# Convite utilizável: não usado, não expirado e com a organização ativa.
_UTILIZAVEL = f"c.usado_em IS NULL AND c.expira_em > now() AND {_ORG_ATIVA}"
_NOME_ORG = "COALESCE((SELECT nome FROM tomador WHERE id = c.tomador_id), " \
            "(SELECT razao_social FROM prestador WHERE id = c.prestador_id))"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _nao_encontrado() -> HTTPException:
    return HTTPException(404, NAO_ENCONTRADO)


def criar(corpo: NovoConvite, usuario: UsuarioContexto) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        if corpo.prestador_id is not None:
            travar_prestador(conn, corpo.prestador_id)
        motivo = motivo_recusa_convite(conn, usuario, corpo.nivel, corpo.papel, corpo.tomador_id, corpo.prestador_id)
        if motivo is not None:
            raise HTTPException(403, motivo)
        return criar_na_transacao(conn, corpo.email, corpo.nivel, corpo.papel, corpo.tomador_id, corpo.prestador_id,
                                  usuario.id)


def travar_prestador(conn, prestador_id: int) -> None:
    """Serializa, por prestador, a criação de convite e o aceite (que cria o primeiro usuário): a checagem 'prestador
    sem usuário' de escopo.pode_convidar vale até o fim da transação. NO KEY UPDATE não bloqueia as FKs."""
    conn.execute("SELECT 1 FROM prestador WHERE id = %s FOR NO KEY UPDATE", (prestador_id,))


def criar_na_transacao(conn, email: str, nivel: str, papel: str, tomador_id: int | None, prestador_id: int | None,
                       criado_por: int) -> dict:
    """Cria o convite na transação de quem chama (sem checar permissão: isso é de escopo.pode_convidar)."""
    token = secrets.token_urlsafe(32)
    if tomador_id is not None:
        ativo = conn.execute("SELECT ativo FROM tomador WHERE id = %s", (tomador_id,)).fetchone()
    elif prestador_id is not None:
        ativo = conn.execute("SELECT ativo FROM prestador WHERE id = %s", (prestador_id,)).fetchone()
    else:
        ativo = (True,)
    if ativo is None or not ativo[0]:
        raise HTTPException(404, "organização não encontrada ou desativada")
    # Serializa criações para o mesmo e-mail: sem isso, duas requisições simultâneas passariam pela checagem.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("convite:" + email,))
    if conn.execute("SELECT 1 FROM usuario WHERE lower(email) = %s", (email,)).fetchone():
        raise HTTPException(409, "já existe usuário com este e-mail")
    if conn.execute("SELECT 1 FROM convite WHERE lower(email) = %s AND usado_em IS NULL AND expira_em > now()",
                    (email,)).fetchone():
        raise HTTPException(409, "já existe convite pendente para este e-mail")
    linha = conn.execute(
        "INSERT INTO convite (token_hash, email, nivel, papel, tomador_id, prestador_id, criado_por, expira_em) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, now() + %s) RETURNING id, email, nivel, papel, expira_em",
        (hash_token(token), email, nivel, papel, tomador_id, prestador_id, criado_por,
         timedelta(days=config.CONVITE_VALIDADE_DIAS))).fetchone()
    return dict(zip(("id", "email", "nivel", "papel", "expira_em"), linha), token=token)


def listar(usuario: UsuarioContexto) -> list[dict]:
    """Plataforma: todos. Admin de tomador/prestador: os criados por usuários da própria organização. Membro: 403."""
    if usuario.nivel == "plataforma":
        onde, args = "TRUE", []
    elif usuario.papel != "admin":
        raise HTTPException(403, "apenas administradores listam convites")
    elif usuario.nivel == "tomador" and usuario.tomador_id is not None:
        onde, args = "c.criado_por IN (SELECT id FROM usuario WHERE tomador_id = %s)", [usuario.tomador_id]
    elif usuario.nivel == "prestador" and usuario.prestador_id is not None:
        onde, args = "c.criado_por IN (SELECT id FROM usuario WHERE prestador_id = %s)", [usuario.prestador_id]
    else:
        raise HTTPException(403, "sem permissão para listar convites")
    with psycopg.connect(config.DATABASE_URL) as conn:
        linhas = conn.execute(
            f"SELECT c.id, c.email, c.nivel, c.papel, c.tomador_id, c.prestador_id, {_NOME_ORG}, "
            "CASE WHEN c.usado_em IS NOT NULL THEN 'usado' WHEN c.expira_em <= now() THEN 'expirado' "
            "ELSE 'pendente' END, c.criado_por, c.criado_em, c.expira_em, c.usado_em, c.usuario_id "
            f"FROM convite c WHERE {onde} ORDER BY c.id DESC", args).fetchall()
    chaves = ("id", "email", "nivel", "papel", "tomador_id", "prestador_id", "organizacao_nome", "estado",
              "criado_por", "criado_em", "expira_em", "usado_em", "usuario_id")
    return [dict(zip(chaves, l)) for l in linhas]


def consultar(token: str) -> dict:
    if len(token) > TOKEN_MAX:
        raise _nao_encontrado()
    with psycopg.connect(config.DATABASE_URL) as conn:
        linha = conn.execute(
            f"SELECT c.email, c.nivel, {_NOME_ORG}, c.expira_em FROM convite c "
            f"WHERE c.token_hash = %s AND {_UTILIZAVEL}", (hash_token(token),)).fetchone()
    if linha is None:
        raise _nao_encontrado()
    return dict(zip(("email", "nivel", "organizacao_nome", "expira_em"), linha))


def aceitar(token: str, corpo: AceiteIn) -> dict:
    if not config.AUTH_SEGREDO:  # antes de criar o usuário: falha fechada sem deixar conta sem como entrar
        raise HTTPException(503, "autenticação não configurada: defina AUTH_SEGREDO")
    if len(token) > TOKEN_MAX:
        raise _nao_encontrado()
    # Rota pública: confere o convite ANTES do scrypt, para um token falso não custar CPU do servidor.
    # A checagem que vale continua sendo o UPDATE atômico abaixo.
    consultar(token)
    senha_hash = senhas.gerar_hash(corpo.senha)  # fora da transação: o scrypt é lento
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:  # uma transação: cria o usuário e gasta o convite, ou nada
            # Atômico: dois aceites simultâneos disputam a mesma linha; o segundo reavalia `usado_em IS NULL` e perde.
            convite = conn.execute(
                f"UPDATE convite c SET usado_em = now() WHERE c.token_hash = %s AND {_UTILIZAVEL} "
                "RETURNING c.id, c.email, c.nivel, c.papel, c.tomador_id, c.prestador_id, "
                "EXISTS (SELECT 1 FROM usuario u WHERE u.id = c.criado_por AND u.nivel = 'tomador')",
                (hash_token(token),)).fetchone()
            if convite is None:
                raise _nao_encontrado()
            id_convite, email, nivel, papel, tomador_id, prestador_id, criado_por_tomador = convite
            if prestador_id is not None:
                travar_prestador(conn, prestador_id)  # serializa com a checagem de escopo.pode_convidar
                # Convite de prestador criado por um CLIENTE só serve para o primeiro acesso: se o prestador já tem
                # alguém, a pessoa veria os contratos dele com outros clientes. Recusa sem gastar o convite.
                if criado_por_tomador and prestador_tem_usuario_ativo(conn, prestador_id):
                    raise _nao_encontrado()
            usuario_id = conn.execute(
                "INSERT INTO usuario (email, nome, senha_hash, nivel, papel, tomador_id, prestador_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (email, corpo.nome, senha_hash, nivel, papel, tomador_id, prestador_id)).fetchone()[0]
            conn.execute("UPDATE convite SET usuario_id = %s WHERE id = %s", (usuario_id, id_convite))
    except psycopg.errors.UniqueViolation:
        # O e-mail virou usuário depois do convite: a transação voltou e o convite segue pendente.
        raise HTTPException(409, "já existe usuário com o e-mail deste convite")
    return emitir_token(UsuarioContexto(id=usuario_id, email=email, nome=corpo.nome, nivel=nivel, papel=papel,
                                        tomador_id=tomador_id, prestador_id=prestador_id))
