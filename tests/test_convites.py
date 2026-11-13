"""Convites: criação (só plataforma, por enquanto), listagem, consulta pública, aceite atômico e uso único.
Contra o Postgres real; só valores falsos. O banco é compartilhado: cada teste usa e-mails e organizações próprios e
apaga o que criou. O token só aparece aqui em variáveis locais e nunca em mensagem de asserção."""
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import config, senhas
from app.api import app
from app.escopo import pode_convidar
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from conftest import cnpj_valido

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)

SENHA = "senha-falsa-do-convite"
NAO_ENCONTRADO = {"detail": "convite inválido, usado ou expirado"}


def _email() -> str:
    return f"convidado-{uuid.uuid4().hex}@exemplo.invalid"


def _h_id(uid: int) -> dict:
    agora = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": str(uid), "iat": agora - 5, "exp": agora + 600}, config.AUTH_SEGREDO, algorithm="HS256")}


class Mundo:
    pass


@pytest.fixture
def mundo():
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    m = Mundo()
    m.db, m.emails, m.tomadores, m.prestadores = conn, [], [], []
    m.tomador = conn.execute("INSERT INTO tomador (nome) VALUES (%s) RETURNING id",
                             (f"Tomador {uuid.uuid4().hex}",)).fetchone()[0]
    m.prestador = conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) RETURNING id",
                               (cnpj_valido(uuid.uuid4().int), f"Prestador {uuid.uuid4().hex}")).fetchone()[0]
    m.tomadores.append(m.tomador)
    m.prestadores.append(m.prestador)

    def usuario(nivel="plataforma", papel="admin", tomador_id=None, prestador_id=None):
        email = _email()
        m.emails.append(email)
        uid = conn.execute(
            "INSERT INTO usuario (email, nome, senha_hash, nivel, papel, tomador_id, prestador_id) "
            "VALUES (%s, 'Pessoa de Teste', 'x', %s, %s, %s, %s) RETURNING id",
            (email, nivel, papel, tomador_id, prestador_id)).fetchone()[0]
        return uid
    m.usuario = usuario
    m.plat = usuario()
    m.h = _h_id(m.plat)

    def convidar(email=None, nivel="tomador", papel="admin", headers=None, **ids):
        email = email or _email()
        m.emails.append(email.strip().lower())
        if not ids and nivel == "tomador":
            ids = {"tomador_id": m.tomador}
        if not ids and nivel == "prestador":
            ids = {"prestador_id": m.prestador}
        return client.post("/convites", headers=headers or m.h,
                           json={"email": email, "nivel": nivel, "papel": papel, **ids})
    m.convidar = convidar

    def criar_ok(**kw):
        r = convidar(**kw)
        assert r.status_code == 201, r.text
        return r.json()
    m.criar_ok = criar_ok

    def inativar(tabela, id_):
        conn.execute(f"UPDATE {tabela} SET ativo = false WHERE id = %s", (id_,))
    m.inativar = inativar
    try:
        yield m
    finally:
        conn.execute("DELETE FROM convite WHERE lower(email) = ANY(%s)", ([e.lower() for e in m.emails],))
        conn.execute("DELETE FROM usuario WHERE lower(email) = ANY(%s)", ([e.lower() for e in m.emails],))
        conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (m.tomadores,))
        conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (m.prestadores,))
        conn.close()


def _aceitar(token, nome="Fulano de Tal", senha=SENHA):
    return client.post(f"/convites/{token}/aceitar", json={"nome": nome, "senha": senha})


# ---------- criação ----------

def test_plataforma_cria_convite_201_e_devolve_o_token_uma_vez(mundo):
    r = mundo.convidar(email="  Maiusculas-" + uuid.uuid4().hex + "@Exemplo.INVALID ")
    assert r.status_code == 201
    corpo = r.json()
    assert set(corpo) == {"id", "email", "nivel", "papel", "expira_em", "token"}
    assert corpo["email"] == corpo["email"].lower() and corpo["nivel"] == "tomador" and corpo["papel"] == "admin"
    assert len(corpo["token"]) >= 43
    expira = datetime.fromisoformat(corpo["expira_em"])
    esperado = datetime.now(timezone.utc) + timedelta(days=config.CONVITE_VALIDADE_DIAS)
    assert abs((expira - esperado).total_seconds()) < 60
    assert config.CONVITE_VALIDADE_DIAS == 7


def test_banco_guarda_so_o_hash_nunca_o_token(mundo):
    corpo = mundo.criar_ok()
    token = corpo["token"]
    linha = mundo.db.execute("SELECT * FROM convite WHERE id = %s", (corpo["id"],)).fetchone()
    colunas = [d.name for d in mundo.db.execute("SELECT * FROM convite WHERE id = %s", (corpo["id"],)).description]
    assert "token" not in colunas
    assert all(token not in str(valor) for valor in linha)
    assert dict(zip(colunas, linha))["token_hash"] == hashlib.sha256(token.encode()).hexdigest()


def test_token_e_unico_por_convite(mundo):
    assert mundo.criar_ok()["token"] != mundo.criar_ok()["token"]


def test_criacao_com_prestador_e_com_plataforma(mundo):
    assert mundo.criar_ok(nivel="prestador", papel="membro")["nivel"] == "prestador"
    assert mundo.criar_ok(nivel="plataforma", papel="membro")["nivel"] == "plataforma"


def test_409_se_ja_existe_usuario_com_o_email_sem_diferenciar_caixa(mundo):
    uid_email = mundo.db.execute("SELECT email FROM usuario WHERE id = %s", (mundo.plat,)).fetchone()[0]
    r = mundo.convidar(email=uid_email.upper())
    assert r.status_code == 409


def test_409_se_ja_existe_convite_pendente_para_o_email(mundo):
    email = _email()
    mundo.criar_ok(email=email)
    assert mundo.convidar(email=email.upper()).status_code == 409


def test_convite_expirado_nao_bloqueia_novo_convite(mundo):
    email = _email()
    antigo = mundo.criar_ok(email=email)
    mundo.db.execute("UPDATE convite SET expira_em = now() - interval '1 minute' WHERE id = %s", (antigo["id"],))
    assert mundo.convidar(email=email).status_code == 201


def test_criacao_simultanea_para_o_mesmo_email_cria_so_um(mundo):
    email = _email()
    with ThreadPoolExecutor(6) as pool:
        codigos = list(pool.map(lambda _: mundo.convidar(email=email).status_code, range(6)))
    assert sorted(codigos) == [201] + [409] * 5


@pytest.mark.parametrize("corpo", [
    {"nivel": "tomador"}, {"nivel": "prestador"}, {"nivel": "plataforma", "tomador_id": 1},
    {"nivel": "tomador", "tomador_id": 1, "prestador_id": 1}, {"nivel": "tomador", "prestador_id": 1},
    {"nivel": "prestador", "tomador_id": 1}, {"nivel": "nenhum", "tomador_id": 1},
    {"nivel": "tomador", "tomador_id": 0}, {"nivel": "tomador", "tomador_id": 1, "papel": "dono"},
    {"nivel": "tomador", "tomador_id": 1, "email": "sem-arroba"},
])
def test_corpo_incoerente_da_422(mundo, corpo):
    completo = {"email": _email(), "papel": "admin", **corpo}
    assert client.post("/convites", headers=mundo.h, json=completo).status_code == 422


def test_organizacao_inexistente_ou_inativa_da_404(mundo):
    assert mundo.convidar(nivel="tomador", tomador_id=2 ** 62).status_code == 404
    assert mundo.convidar(nivel="prestador", prestador_id=2 ** 62).status_code == 404
    mundo.inativar("tomador", mundo.tomador)
    mundo.inativar("prestador", mundo.prestador)
    assert mundo.convidar(nivel="tomador").status_code == 404
    assert mundo.convidar(nivel="prestador").status_code == 404


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_tomador_e_prestador_nao_criam_convite_403(mundo, nivel):
    vinculo = {"tomador_id": mundo.tomador} if nivel == "tomador" else {"prestador_id": mundo.prestador}
    h = _h_id(mundo.usuario(nivel=nivel, papel="admin", **vinculo))
    r = mundo.convidar(headers=h)
    assert r.status_code == 403 and "token" not in r.json()
    assert mundo.db.execute("SELECT count(*) FROM convite WHERE lower(email) = ANY(%s)", (mundo.emails,)
                            ).fetchone()[0] == 0


def test_sem_token_criar_e_listar_da_401(mundo):
    assert client.post("/convites", json={"email": _email(), "nivel": "plataforma", "papel": "admin"}).status_code == 401
    assert client.get("/convites").status_code == 401


def test_pode_convidar_hoje_libera_so_plataforma():
    def u(nivel, papel="admin"):
        return UsuarioContexto(id=1, email="a@b.invalid", nome="A", nivel=nivel, papel=papel,
                               tomador_id=1 if nivel == "tomador" else None,
                               prestador_id=1 if nivel == "prestador" else None)
    assert pode_convidar(u("plataforma"), "prestador", "admin", None, 1)
    assert pode_convidar(u("plataforma", "membro"), "tomador", "membro", 1, None)
    for nivel in ("tomador", "prestador"):
        assert not pode_convidar(u(nivel), nivel, "membro", u(nivel).tomador_id, u(nivel).prestador_id)


# ---------- listagem ----------

def test_listagem_so_plataforma(mundo):
    for nivel in ("tomador", "prestador"):
        vinculo = {"tomador_id": mundo.tomador} if nivel == "tomador" else {"prestador_id": mundo.prestador}
        h = _h_id(mundo.usuario(nivel=nivel, **vinculo))
        assert client.get("/convites", headers=h).status_code == 403


def test_listagem_mostra_estados_e_nunca_token_nem_hash(mundo):
    pendente, usado, expirado = (mundo.criar_ok() for _ in range(3))
    assert _aceitar(usado["token"]).status_code == 200
    mundo.db.execute("UPDATE convite SET expira_em = now() - interval '1 second' WHERE id = %s", (expirado["id"],))
    r = client.get("/convites", headers=mundo.h)
    assert r.status_code == 200
    por_id = {c["id"]: c for c in r.json()}
    assert por_id[pendente["id"]]["estado"] == "pendente"
    assert por_id[usado["id"]]["estado"] == "usado" and por_id[usado["id"]]["usuario_id"]
    assert por_id[expirado["id"]]["estado"] == "expirado"
    assert por_id[pendente["id"]]["organizacao_nome"].startswith("Tomador ")
    assert por_id[pendente["id"]]["criado_por"] == mundo.plat
    for c in por_id.values():
        assert not {"token", "token_hash"} & set(c)
    for convite in (pendente, usado, expirado):
        assert convite["token"] not in r.text
        assert hashlib.sha256(convite["token"].encode()).hexdigest() not in r.text


# ---------- consulta pública ----------

def test_get_publico_devolve_o_minimo_sem_login(mundo):
    corpo = mundo.criar_ok(nivel="prestador", papel="membro")
    r = client.get(f"/convites/{corpo['token']}")  # sem Authorization
    assert r.status_code == 200
    dados = r.json()
    assert set(dados) == {"email", "nivel", "organizacao_nome", "expira_em"}
    assert dados["email"] == corpo["email"] and dados["nivel"] == "prestador"
    assert dados["organizacao_nome"].startswith("Prestador ")
    assert dados["expira_em"] == corpo["expira_em"]


def test_get_publico_plataforma_sem_organizacao(mundo):
    assert client.get(f"/convites/{mundo.criar_ok(nivel='plataforma')['token']}").json()["organizacao_nome"] is None


def test_get_publico_404_identico_para_invalido_usado_expirado_e_org_desativada(mundo):
    usado, expirado, org_off = mundo.criar_ok(), mundo.criar_ok(), mundo.criar_ok()
    assert _aceitar(usado["token"]).status_code == 200
    mundo.db.execute("UPDATE convite SET expira_em = now() - interval '1 second' WHERE id = %s", (expirado["id"],))
    mundo.inativar("tomador", mundo.tomador)  # derruba o org_off (e qualquer outro do mesmo tomador)
    respostas = [client.get(f"/convites/{t}") for t in
                 ("token-que-nao-existe", "x" * 500, usado["token"], expirado["token"], org_off["token"])]
    assert {r.status_code for r in respostas} == {404}
    assert all(r.json() == NAO_ENCONTRADO for r in respostas)
    assert len({r.text for r in respostas}) == 1


# ---------- aceite ----------

def test_aceitar_cria_usuario_e_ja_devolve_token_de_login(mundo):
    corpo = mundo.criar_ok(nivel="prestador", papel="membro")
    r = _aceitar(corpo["token"], nome="  Maria da Silva ")
    assert r.status_code == 200
    login = r.json()
    assert set(login) == {"access_token", "token_type", "expira_em"} and login["token_type"] == "bearer"
    u = mundo.db.execute("SELECT id, email, nome, nivel, papel, tomador_id, prestador_id, ativo, senha_hash "
                         "FROM usuario WHERE lower(email) = %s", (corpo["email"],)).fetchone()
    assert u[1:8] == (corpo["email"], "Maria da Silva", "prestador", "membro", None, mundo.prestador, True)
    assert u[8].startswith("scrypt$") and SENHA not in u[8] and senhas.verificar(SENHA, u[8])
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert me.status_code == 200 and me.json()["id"] == u[0] and me.json()["prestador_id"] == mundo.prestador
    ok = client.post("/auth/login", json={"usuario": corpo["email"].upper(), "senha": SENHA})
    assert ok.status_code == 200
    assert client.post("/auth/login", json={"usuario": corpo["email"], "senha": "outra"}).status_code == 401
    conv = mundo.db.execute("SELECT usado_em, usuario_id FROM convite WHERE id = %s", (corpo["id"],)).fetchone()
    assert conv[0] is not None and conv[1] == u[0]


def test_aceitar_convite_de_tomador_e_de_plataforma(mundo):
    t = mundo.criar_ok(nivel="tomador", papel="admin")
    assert _aceitar(t["token"]).status_code == 200
    p = mundo.criar_ok(nivel="plataforma", papel="admin")
    assert _aceitar(p["token"]).status_code == 200
    linhas = dict(mundo.db.execute("SELECT nivel, tomador_id FROM usuario WHERE lower(email) = ANY(%s)",
                                   ([t["email"], p["email"]],)).fetchall())
    assert linhas == {"tomador": mundo.tomador, "plataforma": None}


def test_segundo_aceite_do_mesmo_convite_da_404(mundo):
    corpo = mundo.criar_ok()
    assert _aceitar(corpo["token"]).status_code == 200
    r = _aceitar(corpo["token"], nome="Outra Pessoa", senha="outra-senha-falsa")
    assert r.status_code == 404 and r.json() == NAO_ENCONTRADO
    assert mundo.db.execute("SELECT count(*) FROM usuario WHERE lower(email) = %s", (corpo["email"],)
                            ).fetchone()[0] == 1


def test_aceite_expirado_da_404_e_nao_cria_usuario(mundo):
    corpo = mundo.criar_ok()
    mundo.db.execute("UPDATE convite SET expira_em = now() - interval '1 second' WHERE id = %s", (corpo["id"],))
    r = _aceitar(corpo["token"])
    assert r.status_code == 404 and r.json() == NAO_ENCONTRADO
    assert mundo.db.execute("SELECT count(*) FROM usuario WHERE lower(email) = %s", (corpo["email"],)
                            ).fetchone()[0] == 0


def test_aceite_com_token_inexistente_da_404(mundo):
    r = _aceitar("token-que-nao-existe")
    assert r.status_code == 404 and r.json() == NAO_ENCONTRADO


@pytest.mark.parametrize("tabela,nivel", [("tomador", "tomador"), ("prestador", "prestador")])
def test_organizacao_desativada_depois_do_convite_da_404(mundo, tabela, nivel):
    corpo = mundo.criar_ok(nivel=nivel)
    mundo.inativar(tabela, mundo.tomador if tabela == "tomador" else mundo.prestador)
    r = _aceitar(corpo["token"])
    assert r.status_code == 404 and r.json() == NAO_ENCONTRADO
    assert mundo.db.execute("SELECT usado_em FROM convite WHERE id = %s", (corpo["id"],)).fetchone()[0] is None
    assert mundo.db.execute("SELECT count(*) FROM usuario WHERE lower(email) = %s", (corpo["email"],)
                            ).fetchone()[0] == 0


@pytest.mark.parametrize("corpo", [
    {"nome": "Fulano", "senha": "curta"}, {"nome": "   ", "senha": SENHA}, {"nome": "x" * 201, "senha": SENHA},
    {"nome": "Fulano", "senha": "a" * (senhas.SENHA_MAX_BYTES + 1)}, {"senha": SENHA}, {"nome": "Fulano"},
])
def test_corpo_invalido_no_aceite_da_422_e_preserva_o_convite(mundo, corpo):
    convite = mundo.criar_ok()
    r = client.post(f"/convites/{convite['token']}/aceitar", json=corpo)
    assert r.status_code == 422
    assert convite["token"] not in r.text
    assert _aceitar(convite["token"]).status_code == 200  # o convite não foi gasto


def test_dois_aceites_simultaneos_criam_exatamente_um_usuario(mundo):
    corpo = mundo.criar_ok()
    with ThreadPoolExecutor(8) as pool:
        respostas = list(pool.map(lambda i: _aceitar(corpo["token"], senha=f"{SENHA}-{i}"), range(8)))
    assert sorted(r.status_code for r in respostas) == [200] + [404] * 7
    assert all(r.json() == NAO_ENCONTRADO for r in respostas if r.status_code == 404)
    assert mundo.db.execute("SELECT count(*) FROM usuario WHERE lower(email) = %s", (corpo["email"],)
                            ).fetchone()[0] == 1


def test_email_virou_usuario_depois_do_convite_da_409_e_o_convite_segue_pendente(mundo):
    corpo = mundo.criar_ok()
    mundo.db.execute("INSERT INTO usuario (email, nome, nivel, papel) VALUES (%s, 'Outro', 'plataforma', 'membro')",
                     (corpo["email"].upper(),))
    assert _aceitar(corpo["token"]).status_code == 409
    assert mundo.db.execute("SELECT usado_em FROM convite WHERE id = %s", (corpo["id"],)).fetchone()[0] is None


def test_sem_segredo_de_autenticacao_o_aceite_da_503_sem_criar_usuario(mundo, monkeypatch):
    corpo = mundo.criar_ok()
    monkeypatch.setattr(config, "AUTH_SEGREDO", "")
    assert _aceitar(corpo["token"]).status_code == 503
    monkeypatch.setattr(config, "AUTH_SEGREDO", "segredo-falso-de-teste-com-mais-de-32-bytes")
    assert _aceitar(corpo["token"]).status_code == 200


def test_token_nao_vai_para_o_log(mundo, caplog):
    caplog.set_level("DEBUG")
    corpo = mundo.criar_ok()
    _aceitar(corpo["token"])
    # O log do cliente de teste (httpx) mostra a URL que o próprio teste montou; só importa o que a app registra.
    da_app = "\n".join(r.getMessage() for r in caplog.records if r.name != "httpx")
    assert corpo["token"] not in da_app


# ---------- banco e rotas ----------

def test_checks_do_convite_batem_com_o_vocabulario_de_acesso(mundo):
    for coluna, valores in (("nivel", config.NIVEIS_ACESSO), ("papel", config.PAPEIS)):
        definicao = mundo.db.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
            (f"convite_{coluna}_check",)).fetchone()[0]
        assert all(f"'{v}'" in definicao for v in valores)
    with pytest.raises(psycopg.errors.CheckViolation):  # tomador sem tomador_id
        mundo.db.execute("INSERT INTO convite (token_hash, email, nivel, papel, expira_em) "
                         "VALUES (%s, 'x@x.invalid', 'tomador', 'admin', now())", (uuid.uuid4().hex * 2,))


def test_rotas_novas_estao_registradas_e_so_as_duas_por_token_sao_publicas():
    rotas = {(m, r.path): r for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    assert {("POST", "/convites"), ("GET", "/convites"), ("GET", "/convites/{token}"),
            ("POST", "/convites/{token}/aceitar")} <= set(rotas)

    def chamadas(dep):
        for sub in dep.dependencies:
            yield sub.call
            yield from chamadas(sub)
    publicas = {k for k, r in rotas.items() if k[1].startswith("/convites") and exigir_usuario not in set(chamadas(r.dependant))}
    assert publicas == {("GET", "/convites/{token}"), ("POST", "/convites/{token}/aceitar")}
