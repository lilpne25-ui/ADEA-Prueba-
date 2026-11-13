"""Pruebas de integración REALES contra Oracle Free (Docker) y SQL Server LocalDB locales.

Solo se ejecutan con ADEA_REAL_DB=1 y credenciales en .env.local (ver scripts/setup_*.py).
Usan exclusivamente documentos sintéticos. Cada imagen se vuelve única (1 píxel aleatorio) para que el
hash no colisione con ejecuciones anteriores.
"""

import base64
import io
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

from app import envfile, persistence as p
from app.samples import SAMPLE_NAMES, sample_bytes

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(os.getenv("ADEA_REAL_DB") != "1" or not envfile.ENV_PATH.exists(),
                                reason="Integración real deshabilitada (ADEA_REAL_DB=1 para activarla)")


@pytest.fixture
def real_env(monkeypatch, tmp_path):
    for k, val in envfile.read_env().items():
        monkeypatch.setenv(k, val)
    monkeypatch.setenv("AUDIT_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setattr(p, "oracle_factory", p._oracle_connect)
    monkeypatch.setattr(p, "sqlserver_factory", p._sqlserver_connect)
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app, headers={"X-Access-Token": os.environ["APP_ACCESS_TOKEN"]})


def unique(png: bytes) -> bytes:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.putpixel((3, 3), tuple(secrets.randbelow(256) for _ in range(3)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def payload(name, data, **extra):
    return {"archivo": name, "imagen": "data:image/png;base64," + base64.b64encode(data).decode(), **extra}


def oracle_rows(sha):
    conn = p._oracle_connect()
    try:
        cur = conn.cursor()
        owner = os.environ["ORACLE_SP_NAME"].split(".")[0]
        cur.execute(f"SELECT COUNT(*) FROM {owner}.INE_EXPEDIENTES_DEMO WHERE FILE_SHA256 = :s", s=sha)
        return cur.fetchone()[0]
    finally:
        conn.close()


def audit_rows(sha):
    conn = p._sqlserver_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DocumentType, Outcome, PersistenceState, ErrorCode, DurationMs "
                    "FROM dbo.IneAuditLog WHERE FileSha256 = ? ORDER BY Id", sha)
        return cur.fetchall()
    finally:
        conn.close()


def test_0_real_connections(real_env):
    res = p.test_connections()
    assert res["oracle"]["estado"] == p.CONECTADO and res["sqlserver"]["estado"] == p.CONECTADO


def test_1_fictitious_ine_registered_in_oracle(real_env):
    data = unique(sample_bytes(SAMPLE_NAMES[0]))
    r = real_env.post("/api/process", json={"archivos": [payload("INE_FICTICIA.png", data)]}).json()["resultados"][0]
    assert r["clasificacion"] == "ine" and r["estado"] == "listo"
    assert r["persistencia"]["estado"] == "registrado", r["persistencia"]
    assert oracle_rows(r["sha256"]) == 1
    assert audit_rows(r["sha256"])[0][2] == "oracle_ok"
    # Reenviar el mismo archivo ⇒ duplicado, no segunda fila.
    again = real_env.post("/api/process", json={"archivos": [payload("INE_FICTICIA.png", data)]}).json()
    assert again["resultados"][0]["persistencia"]["oracle"] == "duplicado" and oracle_rows(r["sha256"]) == 1


def test_2_non_ine_is_audited_in_sqlserver(real_env):
    data = unique(sample_bytes(SAMPLE_NAMES[2]))
    r = real_env.post("/api/process", json={"archivos": [payload("CONTRATO.png", data)]}).json()["resultados"][0]
    assert r["estado"] == "descartado" and r["persistencia"]["sqlserver"] == "auditado"
    rows = audit_rows(r["sha256"])
    assert rows and rows[0][0] == "no_ine" and rows[0][1] == "descartado" and rows[0][2] == "no_aplica"
    assert oracle_rows(r["sha256"]) == 0


def test_3_heterogeneous_batch(real_env):
    files = [payload(n, unique(sample_bytes(n))) for n in SAMPLE_NAMES]
    files[0]["grupo"] = files[1]["grupo"] = "1"
    files[0]["cara"], files[1]["cara"] = "front", "back"
    files.append({"archivo": "CORRUPTO.png", "imagen": base64.b64encode(b"\x89PNG roto").decode()})
    start = time.monotonic()
    body = real_env.post("/api/process", json={"archivos": files}).json()
    elapsed = time.monotonic() - start
    by = {x["archivo"]: x for x in body["resultados"]}
    assert by[SAMPLE_NAMES[0]]["estado"] == "listo" and by[SAMPLE_NAMES[0]]["campos"]["curp"]["valor"]
    assert by[SAMPLE_NAMES[2]]["estado"] == "descartado"
    assert by[SAMPLE_NAMES[3]]["estado"] == "repetir"  # imagen insuficiente: no se confunde con documento ajeno
    assert by["CORRUPTO.png"]["estado"] == "error" and by["CORRUPTO.png"]["persistencia"]["sqlserver"] == "auditado"
    for name in SAMPLE_NAMES:
        assert by[name]["duracion_ms"] > 0 and by[name]["persistencia"]["sqlserver"] == "auditado"
        assert audit_rows(by[name]["sha256"])
    assert oracle_rows(by[SAMPLE_NAMES[0]]["sha256"]) == 1
    print(f"\nLote de 5 archivos procesado y persistido en {elapsed:.1f} s")


def test_4_controlled_connection_failures(real_env, monkeypatch):
    # Oracle inaccesible: se informa y se audita; nada se pierde en silencio.
    monkeypatch.setenv("ORACLE_DSN", "127.0.0.1:1599/FREEPDB1")
    data = unique(sample_bytes(SAMPLE_NAMES[0]))
    r = real_env.post("/api/process", json={"archivos": [payload("INE.png", data)]}).json()["resultados"][0]
    assert r["persistencia"]["estado"] == "error_oracle" and r["persistencia"]["codigo_error"]
    assert audit_rows(r["sha256"])[0][2] == "error_oracle"
    # SQL Server inaccesible con Oracle OK: registrado_sin_auditoria + bandeja + reenvío real.
    good_dsn = envfile.read_env()["ORACLE_DSN"]
    monkeypatch.setenv("ORACLE_DSN", good_dsn)
    real_conn = os.environ["SQLSERVER_CONNECTION_STRING"]
    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", real_conn.replace("ADEA_INE", "NO_EXISTE_ADEA"))
    data2 = unique(sample_bytes(SAMPLE_NAMES[0]))
    r2 = real_env.post("/api/process", json={"archivos": [payload("INE2.png", data2)]}).json()["resultados"][0]
    assert r2["persistencia"]["estado"] == "registrado_sin_auditoria"
    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", real_conn)
    assert p.replay_outbox()["reenviados"] >= 1
    assert audit_rows(r2["sha256"])


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_5_restart_application_reconnects():
    port = _free_port()
    env = {**os.environ, **envfile.read_env()}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                             "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import httpx
        for _ in range(40):
            try:
                resp = httpx.get(f"http://127.0.0.1:{port}/api/infra",
                                 headers={"X-Access-Token": env["APP_ACCESS_TOKEN"]}, timeout=30)
                break
            except httpx.TransportError:
                time.sleep(0.5)
        data = resp.json()
        assert data["oracle"]["ok"] and data["sqlserver"]["ok"]
        assert data["sqlserver"]["eventos_auditoria"] >= 1 and data["oracle"]["expedientes"] >= 1
    finally:
        proc.terminate()
        proc.wait(timeout=20)
