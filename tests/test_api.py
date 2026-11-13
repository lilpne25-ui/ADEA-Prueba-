import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.samples import SAMPLE_NAMES, sample_bytes
from conftest import requires_tesseract

client = TestClient(app)


def as_file(name, data=None, **extra):
    data = data or sample_bytes(name)
    return {"archivo": name, "imagen": "data:image/png;base64," + base64.b64encode(data).decode(), **extra}


def test_health_and_page():
    assert client.get("/").status_code == 200
    h = client.get("/api/health").json()
    assert h["servicio"] == "operativo" and h["persistencia"]["oracle"] == "NO_CONFIGURADO"
    assert "x-content-type-options" in client.get("/").headers and "default-src 'self'" in \
           client.get("/").headers["content-security-policy"]


@requires_tesseract
def test_demo_sample_real_ocr():
    r = client.post("/api/process", json={"archivos": [{"archivo": SAMPLE_NAMES[0]}], "solo_muestra": True})
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["clasificacion"] == "ine" and res["persistencia"]["estado"] == "demo_sin_persistencia"


@requires_tesseract
def test_mixed_batch_and_explicit_pairing():
    files = [as_file(SAMPLE_NAMES[0], grupo="g", cara="front"), as_file(SAMPLE_NAMES[1], grupo="g", cara="back"),
             as_file(SAMPLE_NAMES[2]), as_file(SAMPLE_NAMES[3])]
    body = client.post("/api/process", json={"archivos": files}).json()
    by = {x["archivo"]: x for x in body["resultados"]}
    assert by[SAMPLE_NAMES[0]]["clasificacion"] == "ine" and by[SAMPLE_NAMES[0]]["vinculacion"]["estado"] == "tentativa"
    assert by[SAMPLE_NAMES[2]]["estado"] == "descartado" and by[SAMPLE_NAMES[3]]["estado"] == "descartado"
    assert body["total"] == 4


def test_cloud_blocks_real_uploads(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    r = client.post("/api/process", json={"archivos": [as_file(SAMPLE_NAMES[0])]})
    assert r.status_code == 403
    r = client.post("/api/process", json={"archivos": [{"archivo": "mi_ine_real.jpg", "imagen": "x"}],
                                          "solo_muestra": True})
    assert r.status_code == 403


def test_invalid_inputs():
    assert client.post("/api/process", content=b"no json").status_code == 400
    assert client.post("/api/process", json={"archivos": []}).status_code == 422
    assert client.post("/api/process", json={"archivos": [None] * 9}).status_code == 422
    res = client.post("/api/process", json={"archivos": [None, {"archivo": "a.png", "imagen": "@@@"}]})
    assert [r["estado"] for r in res.json()["resultados"]] == ["error", "error"]


def test_corrupt_and_non_image_files_are_controlled_errors():
    bad = [as_file("a.png", b"\x89PNG corrupto"), as_file("b.png", b"texto plano")]
    res = client.post("/api/process", json={"archivos": bad}).json()
    assert all(r["estado"] == "error" for r in res["resultados"])


def test_size_limits():
    big = base64.b64encode(b"0" * 4_500_000).decode()
    assert client.post("/api/process", json={"archivos": [{"archivo": "x.png", "imagen": big}]}).status_code == 413
    huge = io.BytesIO()
    Image.new("L", (5000, 3000)).save(huge, "PNG")
    res = client.post("/api/process", json={"archivos": [as_file("g.png", huge.getvalue())]}).json()
    assert res["resultados"][0]["estado"] == "error"  # > 14 MP


def test_corporate_requires_token(monkeypatch):
    monkeypatch.setenv("APP_MODE", "corporate")
    assert client.post("/api/process", json={"archivos": [as_file(SAMPLE_NAMES[2])]}).status_code == 503
    monkeypatch.setenv("APP_ACCESS_TOKEN", "secreto")
    assert client.post("/api/process", json={"archivos": [as_file(SAMPLE_NAMES[2])]}).status_code == 401
    assert client.post("/api/persistence/test").status_code == 401
    ok = client.post("/api/persistence/test", headers={"X-Access-Token": "secreto"})
    assert ok.status_code == 200 and ok.json()["oracle"]["estado"] == "NO_CONFIGURADO"


def test_samples_endpoint():
    assert len(client.get("/api/samples").json()["muestras"]) == len(SAMPLE_NAMES)


def test_pwa_routes():
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.headers["content-type"].startswith("application/manifest+json")
    assert m.json()["display"] == "standalone" and len(m.json()["icons"]) >= 2
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "/api/" in sw.text  # el SW excluye la API de la caché


def test_pairing_requires_token_and_is_hidden_in_cloud(monkeypatch):
    monkeypatch.setenv("APP_MODE", "corporate")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "tok")
    assert client.get("/api/pairing").status_code == 401
    ok = client.get("/api/pairing", headers={"X-Access-Token": "tok"}).json()
    assert "tok" not in ok["url_visible"] and ok["qr"].startswith("data:image/png")
    monkeypatch.setenv("VERCEL", "1")
    assert client.get("/api/pairing", headers={"X-Access-Token": "tok"}).status_code == 404
