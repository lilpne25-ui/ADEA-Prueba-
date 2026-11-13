"""Configuración central. Todo secreto se lee de variables de entorno; nunca del código."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_PIXELS = 14_000_000
MAX_FILES_PER_BATCH = 8
MAX_REQUEST_BYTES = 4_300_000
OCR_TIMEOUT_S = 24

_WINDOWS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def tesseract_cmd() -> str | None:
    """Ruta del ejecutable: TESSERACT_CMD > PATH > ubicaciones estándar de Windows."""
    explicit = os.getenv("TESSERACT_CMD")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in _WINDOWS_TESSERACT:
        if Path(candidate).exists():
            return candidate
    return None


def tessdata_dir() -> str | None:
    """Datos de idioma locales del proyecto (spa/eng) si existen."""
    local = ROOT / "tessdata"
    return str(local) if local.is_dir() else os.getenv("TESSDATA_PREFIX")


def ocr_lang() -> str:
    """Español+inglés si spa.traineddata está disponible; si no, solo inglés."""
    wanted = os.getenv("OCR_LANG")
    if wanted:
        return wanted
    data = tessdata_dir()
    if data and (Path(data) / "spa.traineddata").exists():
        return "spa+eng"
    return "eng"


def upload_enabled() -> bool:
    """Las cargas reales están apagadas por defecto en Vercel (demo pública)."""
    default = "false" if os.getenv("VERCEL") else "true"
    return os.getenv("ENABLE_REAL_UPLOADS", default).lower() in ("true", "1", "yes")
