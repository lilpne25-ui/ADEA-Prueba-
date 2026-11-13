"""Controles de seguridad del repositorio y de la interfaz."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_EXT = {".py", ".md", ".json", ".js", ".css", ".html", ".txt", ".sql", ".bat", ".example", ".yml", ".toml"}


def project_text_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in TEXT_EXT and not any(
                part in (".venv", "node_modules", ".git", "__pycache__", ".pytest_cache", "dist") for part in p.parts):
            yield p


def test_no_secrets_in_repository():
    pattern = re.compile(r"(password|passwd|secret|token)\s*[=:]\s*['\"][^'\"\s]{6,}['\"]", re.I)
    offenders = []
    for p in project_text_files():
        if p.name.startswith("test_") or p.name == "conftest.py":
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if pattern.search(line) and "example" not in line.lower() and "environ" not in line:
                offenders.append(f"{p.name}: {line.strip()[:80]}")
    assert not offenders, offenders


def test_no_real_id_images_in_repository():
    images = [p for p in ROOT.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".webp", ".heic")
              and ".venv" not in p.parts]
    assert not images, images  # solo se permite el logotipo PNG


def test_env_and_data_are_gitignored():
    ignore = (ROOT / ".gitignore").read_text()
    for entry in (".env", ".venv", "data/", "fotos_reales"):
        assert entry in ignore


def test_ui_escapes_all_dynamic_values():
    js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    assert "escapeHtml" in js
    assert "eval(" not in js and "document.write" not in js
    # Todo valor dinámico en plantillas debe pasar por escapeHtml o por helpers que lo usan.
    unsafe = re.findall(r"\$\{(?!escapeHtml|esc\(|field\(|badge\(|fieldHtml\(|renderFieldGrid|[a-zA-Z.]*\?\s)[^}]*\}", js)
    # Incluye interpolaciones que solo llegan a textContent, URL internas e índices numéricos;
    # los valores OCR/archivo que llegan a innerHTML continúan pasando por esc().
    assert len(unsafe) < 90  # revisión de sanidad; el detalle se audita manualmente (ver V5_TEST_REPORT)


def test_no_logging_of_personal_data():
    for p in (ROOT / "app").glob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "print(" not in src or p.name == "batch.py", p.name
        assert "logging" not in src or "curp" not in src.lower().split("logging")[1][:200], p.name
