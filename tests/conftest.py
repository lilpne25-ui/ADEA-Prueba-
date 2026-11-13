import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ENV = ("APP_MODE", "APP_ACCESS_TOKEN", "ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN",
        "SQLSERVER_CONNECTION_STRING", "VERCEL", "ENABLE_REAL_UPLOADS", "AUDIT_OUTBOX_DIR", "ORACLE_SP_PARAMS")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    from app import envfile
    # Aísla las pruebas de .env.local (credenciales locales reales) y del entorno del usuario.
    for key in set(_ENV) | set(envfile.read_env()) | {"ORACLE_SP_NAME", "ORACLE_COUNT_QUERY"}:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AUDIT_OUTBOX_DIR", str(tmp_path / "outbox"))
    from app import persistence
    persistence._seen_hashes.clear()
    persistence._last_test.clear()
    yield


def tesseract_available() -> bool:
    from app import ocr
    return ocr.available()


requires_tesseract = pytest.mark.skipif(not tesseract_available(), reason="Tesseract no instalado")
