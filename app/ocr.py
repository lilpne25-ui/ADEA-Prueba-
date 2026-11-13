"""Envoltorio de Tesseract local. Nada se envía a servicios externos."""

from __future__ import annotations

import io
import statistics
import subprocess
from dataclasses import dataclass

from PIL import Image

from app import config


@dataclass
class OcrResult:
    text: str
    mean_confidence: float | None  # media de confianza por palabra reportada por Tesseract (0-100)
    words: int


def available() -> bool:
    return config.tesseract_cmd() is not None


def run(image: Image.Image, psm: int = 6, whitelist: str | None = None, lang: str | None = None) -> OcrResult:
    cmd = config.tesseract_cmd()
    if not cmd:
        raise RuntimeError("Tesseract no está instalado o no se encuentra en PATH.")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    args = [cmd, "stdin", "stdout", "-l", lang or config.ocr_lang(), "--psm", str(psm)]
    tessdata = config.tessdata_dir()
    if tessdata:
        args += ["--tessdata-dir", tessdata]
    if whitelist:
        args += ["-c", f"tessedit_char_whitelist={whitelist}"]
    args.append("tsv")
    try:
        proc = subprocess.run(args, input=buf.getvalue(), capture_output=True,
                              timeout=config.OCR_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Tesseract excedió el tiempo límite.") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("Tesseract no está instalado.") from exc
    if proc.returncode:
        raise RuntimeError("Tesseract falló al analizar la imagen.")
    return _parse_tsv(proc.stdout.decode("utf-8", errors="replace"))


def _parse_tsv(tsv: str) -> OcrResult:
    lines: dict[tuple[str, str, str], list[str]] = {}
    confs: list[float] = []
    words = 0
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        word = cols[11].strip()
        if not word:
            continue
        key = (cols[2], cols[3], cols[4])
        lines.setdefault(key, []).append(word)
        try:
            conf = float(cols[10])
        except ValueError:
            conf = -1
        if conf >= 0:
            confs.append(conf)
        words += 1
    text = "\n".join(" ".join(ws) for ws in lines.values())
    return OcrResult(text, round(statistics.fmean(confs), 1) if confs else None, words)
