"""Lote ligado ao contrato: POST /lotes com `contrato_id`, deduplicação por contrato e reenvio. Contra o Postgres;
a fila é substituída (os workers não pegam estes lotes). Cada teste apaga os lotes que criou."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.routers.lotes import actions as lotes_actions

client = TestClient(app)


@pytest.fixture
def jobs(monkeypatch):
    enfileirados = []
    monkeypatch.setattr(lotes_actions, "enfileirar",
                        lambda r, fila, payload, *a, **k: enfileirados.append((fila, payload)))
    return enfileirados


@pytest.fixture
def enviar(jobs):
    """enviar(dados, contrato_id=None) -> resposta HTTP; apaga os lotes criados no fim."""
    criados = []

    def _enviar(dados, contrato_id=None):
        form = {} if contrato_id is None else {"contrato_id": str(contrato_id)}
        r = client.post("/lotes", files={"arquivo": ("a.pdf", dados, "application/pdf")}, data=form)
        if r.status_code == 200:
            criados.append(r.json()["lote_id"])
        return r
    yield _enviar
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (criados,))


def _pdf() -> bytes:
    return b"%PDF-1.4 contrato " + uuid.uuid4().hex.encode()


def _lote(id_):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        return conn.execute("SELECT contrato_id, estado FROM lote WHERE id = %s", (id_,)).fetchone()


def _estado(id_, novo):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE lote SET estado = %s WHERE id = %s", (novo, id_))


def _n_lotes():
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute("SELECT count(*) FROM lote").fetchone()[0]


def test_upload_com_contrato(enviar, orgs):
    c = orgs.contrato()
    r = enviar(_pdf(), c)
    assert r.status_code == 200
    corpo = r.json()
    assert set(corpo) == {"lote_id", "estado", "existente", "contrato_id"}
    assert corpo["contrato_id"] == c and corpo["existente"] is False
    assert _lote(corpo["lote_id"])[0] == c
    assert client.get(f"/lotes/{corpo['lote_id']}").json()["contrato_id"] == c


def test_upload_sem_contrato(enviar):
    r = enviar(_pdf())
    assert r.status_code == 200 and r.json()["contrato_id"] is None
    assert _lote(r.json()["lote_id"])[0] is None
    assert client.get(f"/lotes/{r.json()['lote_id']}").json()["contrato_id"] is None


def test_contrato_inexistente_404_sem_criar_lote(enviar):
    antes = _n_lotes()
    r = enviar(_pdf(), 999999999)
    assert r.status_code == 404 and "contrato 999999999" in r.json()["detail"]
    assert _n_lotes() == antes


@pytest.mark.parametrize("flags", [{"ativo": False}, {"tomador_ativo": False}, {"prestador_ativo": False}])
def test_contrato_inativo_409_sem_criar_lote(enviar, orgs, flags):
    c = orgs.contrato(**flags)
    antes = _n_lotes()
    r = enviar(_pdf(), c)
    assert r.status_code == 409 and "inativo" in r.json()["detail"]
    assert _n_lotes() == antes


def test_contrato_id_invalido_422(enviar):
    assert client.post("/lotes", files={"arquivo": ("a.pdf", _pdf(), "application/pdf")},
                       data={"contrato_id": "abc"}).status_code == 422
    assert enviar(_pdf(), 2 ** 70).status_code == 422


def test_mesmo_arquivo_em_dois_contratos_gera_dois_lotes(enviar, orgs, jobs):
    dados, a, b = _pdf(), orgs.contrato(), orgs.contrato()
    ra, rb = enviar(dados, a), enviar(dados, b)
    assert ra.json()["existente"] is False and rb.json()["existente"] is False
    assert ra.json()["lote_id"] != rb.json()["lote_id"]
    assert (_lote(ra.json()["lote_id"])[0], _lote(rb.json()["lote_id"])[0]) == (a, b)
    assert len(jobs) == 2  # cada lote tem a sua segmentação


def test_mesmo_arquivo_duas_vezes_no_mesmo_contrato_gera_um_lote(enviar, orgs, jobs):
    dados, c = _pdf(), orgs.contrato()
    r1, r2 = enviar(dados, c), enviar(dados, c)
    assert r2.json()["lote_id"] == r1.json()["lote_id"]
    assert r2.json()["existente"] is True and r2.json()["contrato_id"] == c
    # em 'recebido' o job pode ter se perdido, então o reenvio reenfileira (duplicado é aceitável); sempre o mesmo lote
    assert {j[1]["lote_id"] for j in jobs} == {r1.json()["lote_id"]}


def test_mesmo_arquivo_duas_vezes_sem_contrato_gera_um_lote(enviar):
    dados = _pdf()
    r1, r2 = enviar(dados), enviar(dados)
    assert r2.json()["lote_id"] == r1.json()["lote_id"]
    assert r2.json()["existente"] is True and r2.json()["contrato_id"] is None


def test_mesmo_arquivo_com_e_sem_contrato_gera_dois_lotes(enviar, orgs):
    dados, c = _pdf(), orgs.contrato()
    sem, com = enviar(dados), enviar(dados, c)
    assert sem.json()["lote_id"] != com.json()["lote_id"]
    assert _lote(sem.json()["lote_id"])[0] is None and _lote(com.json()["lote_id"])[0] == c
    # e o reenvio de cada um continua caindo no seu
    assert enviar(dados).json()["lote_id"] == sem.json()["lote_id"]
    assert enviar(dados, c).json()["lote_id"] == com.json()["lote_id"]


def test_reenvio_de_lote_em_erro_reprocessa_so_o_lote_do_contrato(enviar, orgs, jobs):
    dados, a, b = _pdf(), orgs.contrato(), orgs.contrato()
    la, lb = enviar(dados, a).json()["lote_id"], enviar(dados, b).json()["lote_id"]
    sem = enviar(dados).json()["lote_id"]
    for id_ in (la, lb, sem):
        _estado(id_, "erro")
    jobs.clear()
    r = enviar(dados, a)
    assert r.json() == {"lote_id": la, "estado": "recebido", "existente": True, "contrato_id": a,
                        "reprocessando": True}
    assert jobs == [(config.FILA_SEGMENTAR, {"lote_id": la})]
    assert _lote(la)[1] == "recebido" and _lote(lb)[1] == "erro" and _lote(sem)[1] == "erro"
    jobs.clear()
    r = enviar(dados)  # sem contrato: reprocessa só o lote sem contrato
    assert r.json()["lote_id"] == sem and r.json()["reprocessando"] is True
    assert jobs == [(config.FILA_SEGMENTAR, {"lote_id": sem})] and _lote(lb)[1] == "erro"


def test_lote_nunca_muda_de_contrato_por_reenvio(enviar, orgs):
    dados, c = _pdf(), orgs.contrato()
    sem = enviar(dados).json()["lote_id"]
    com = enviar(dados, c).json()["lote_id"]
    enviar(dados)
    enviar(dados, c)
    assert (_lote(sem)[0], _lote(com)[0]) == (None, c)


def test_documentos_filtra_pelo_contrato_do_lote(enviar, orgs):
    c = orgs.contrato()
    lote = enviar(_pdf(), c).json()["lote_id"]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
                     "VALUES (%s, 1, 1, 1, 'classificado', 'aso')", (lote,))
    docs = [d for g in client.get("/documentos", params={"contrato_id": c}).json()["grupos"] for d in g["documentos"]]
    assert [(d["lote_id"], d["contrato_id"]) for d in docs] == [(lote, c)]


@pytest.mark.parametrize("com_contrato", [True, False])
def test_corrida_uploads_simultaneos_do_mesmo_arquivo(enviar, orgs, jobs, com_contrato):
    """Vários envios simultâneos do mesmo arquivo no mesmo contrato: um único lote, nenhuma exceção."""
    dados = _pdf()
    c = orgs.contrato() if com_contrato else None
    with ThreadPoolExecutor(8) as pool:
        respostas = list(pool.map(lambda _: enviar(dados, c), range(8)))
    assert [r.status_code for r in respostas] == [200] * 8
    assert len({r.json()["lote_id"] for r in respostas}) == 1
    assert sorted(r.json()["existente"] for r in respostas) == [False] + [True] * 7
    with psycopg.connect(config.DATABASE_URL) as conn:
        n = conn.execute("SELECT count(*) FROM lote WHERE id = %s", (respostas[0].json()["lote_id"],)).fetchone()[0]
    assert n == 1
