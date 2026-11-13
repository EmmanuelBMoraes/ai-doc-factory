"""Rodar no compose: docker compose exec api python -m pytest tests (usa Postgres e poppler)."""
import io
import os
import random
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdf2image import convert_from_bytes
from PIL import Image, ImageDraw

from app import api, config
from app.routers.lotes import actions as lotes_actions
from app.imagem import ArquivoInvalido, imagem_para_pdf


def _imagem(tamanho=(900, 1200), cor="white"):
    im = Image.new("RGB", tamanho, cor)
    d = ImageDraw.Draw(im)
    d.rectangle((tamanho[0] // 10, tamanho[1] // 10, tamanho[0] // 2, tamanho[1] // 5), fill="black")
    return im


def _bytes(im, formato, **kw):
    buf = io.BytesIO()
    im.save(buf, formato, **kw)
    return buf.getvalue()


def _ruido(tamanho=(400, 400)):
    # conteúdo pouco compressível, para o truncamento realmente perder dados
    rnd = random.Random(1)
    return Image.frombytes("RGB", tamanho, bytes(rnd.randrange(256) for _ in range(tamanho[0] * tamanho[1] * 3)))


@pytest.mark.parametrize("formato", ["JPEG", "PNG", "TIFF"])
def test_converte_formatos_mantendo_pixels_a_150_dpi(formato):
    original = _imagem()
    pdf = imagem_para_pdf(_bytes(original, formato))
    assert pdf.startswith(b"%PDF")
    paginas = convert_from_bytes(pdf, dpi=150)  # mesmo dpi do OCR
    assert [p.size for p in paginas] == [original.size]


def test_tiff_multipagina_vira_pdf_multipagina():
    quadros = [_imagem((800, 1000)), _imagem((800, 1000), "lightgray")]
    pdf = imagem_para_pdf(_bytes(quadros[0], "TIFF", save_all=True, append_images=quadros[1:]))
    assert len(convert_from_bytes(pdf, dpi=150)) == 2


def test_exif_rotacionado_e_corrigido():
    im = _imagem((600, 400))  # paisagem
    exif = Image.Exif()
    exif[0x0112] = 6  # precisa girar 90 graus: vira retrato
    pdf = imagem_para_pdf(_bytes(im, "JPEG", exif=exif))
    assert convert_from_bytes(pdf, dpi=150)[0].size == (400, 600)


def test_mpo_usa_so_o_primeiro_quadro():
    q1, q2 = _imagem((900, 1200)), _imagem((300, 400), "gray")
    dados = _bytes(q1, "MPO", save_all=True, append_images=[q2])
    with Image.open(io.BytesIO(dados)) as im:
        assert im.format == "MPO" and im.n_frames == 2
    paginas = convert_from_bytes(imagem_para_pdf(dados), dpi=150)
    assert [p.size for p in paginas] == [q1.size]


def test_png_com_transparencia_vira_fundo_branco():
    rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    pagina = convert_from_bytes(imagem_para_pdf(_bytes(rgba, "PNG")), dpi=150)[0]
    assert pagina.getpixel((50, 50)) == (255, 255, 255)


def test_texto_e_formato_nao_suportado_sao_rejeitados():
    with pytest.raises(ArquivoInvalido):
        imagem_para_pdf(b"isto e apenas texto")
    with pytest.raises(ArquivoInvalido, match="não suportado"):
        imagem_para_pdf(_bytes(_imagem(), "GIF"))


def test_imagem_truncada_e_rejeitada():
    dados = _bytes(_ruido(), "PNG")
    with pytest.raises(ArquivoInvalido):
        imagem_para_pdf(dados[: len(dados) // 2])


def test_imagem_gigante_e_rejeitada(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(ArquivoInvalido, match="grande demais"):
        imagem_para_pdf(_bytes(_imagem((100, 100)), "PNG"))  # 10 mil pixels, acima do dobro do limite
    with pytest.raises(ArquivoInvalido, match="grande demais"):
        imagem_para_pdf(_bytes(_imagem((40, 40)), "PNG"))  # só acima do limite: o aviso também vira erro


# --- endpoint ---


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda *a, **k: None)  # os workers não devem pegar estes lotes
    criados = []
    yield TestClient(api.app), criados
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        for id_ in criados:
            conn.execute("DELETE FROM lote WHERE id = %s", (id_,))


def _contagem():
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute("SELECT count(*) FROM lote").fetchone()[0]


def test_upload_imagem_grava_original_pdf_e_e_idempotente(cliente):
    http, criados = cliente
    dados = _bytes(_imagem((700 + os.getpid() % 100, 900)), "JPEG")  # bytes únicos por execução
    r1 = http.post("/lotes", files={"arquivo": ("foto.jpg", dados, "image/jpeg")})
    assert r1.status_code == 200 and r1.json()["existente"] is False
    id_ = r1.json()["lote_id"]
    criados.append(id_)
    pdf = Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    antes = _contagem()
    r2 = http.post("/lotes", files={"arquivo": ("outro_nome.bin", dados, "application/octet-stream")})
    assert r2.json() == {"lote_id": id_, "estado": "recebido", "existente": True, "contrato_id": None}
    assert _contagem() == antes


@pytest.mark.parametrize("conteudo", [b"so texto", _bytes(_ruido(), "PNG")[:300]])
def test_upload_invalido_devolve_400_sem_criar_lote(cliente, conteudo):
    http, _ = cliente
    antes = _contagem()
    r = http.post("/lotes", files={"arquivo": ("x.pdf", conteudo, "application/pdf")})
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]
    assert _contagem() == antes
