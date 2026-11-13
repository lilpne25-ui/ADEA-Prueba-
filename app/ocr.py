"""Envoltorio de Tesseract local. Nada se envía a servicios externos."""

from __future__ import annotations

import io
import os
import statistics
import sys
import subprocess
from dataclasses import dataclass

from PIL import Image

from app import config


@dataclass
class OcrResult:
    text: str
    mean_confidence: float | None  # media de confianza por palabra reportada por Tesseract (0-100)
    words: int


_rapid = None
_VENDOR = config.ROOT / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.append(str(_VENDOR))  # rapidocr_onnxruntime vendorizado (ver vendor/NOTICE.md)


def engine() -> str | None:
    """Motor OCR disponible. OCR_ENGINE=tesseract|rapidocr fuerza uno; por defecto Tesseract y, si no existe
    (p. ej. Vercel, donde no se pueden instalar binarios del sistema), RapidOCR (ONNX, 100 % Python/pip)."""
    wanted = os.getenv("OCR_ENGINE", "auto").lower()
    if wanted in ("auto", "tesseract") and config.tesseract_cmd():
        return "tesseract"
    if wanted in ("auto", "rapidocr"):
        try:
            import rapidocr_onnxruntime  # noqa: F401
            return "rapidocr"
        except ImportError:
            return None
    return None


def available() -> bool:
    return engine() is not None


def _run_rapidocr(image: Image.Image) -> OcrResult:
    """RapidOCR devuelve cajas con texto y probabilidad; se agrupan por renglón (centro vertical)."""
    global _rapid
    import numpy as np
    if _rapid is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid = RapidOCR()
    result, _ = _rapid(np.asarray(image.convert("RGB")))
    if not result:
        return OcrResult("", None, 0)
    boxes = []
    for box, text, score in result:
        ys = [p[1] for p in box]
        boxes.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(p[0] for p in box), text, float(score)))
    boxes.sort()
    lines: list[list[tuple]] = []
    for b in boxes:
        if lines and abs(b[0] - lines[-1][0][0]) < max(b[1], lines[-1][0][1]) * 0.5:
            lines[-1].append(b)
        else:
            lines.append([b])
    text = "\n".join(" ".join(t[3] for t in sorted(line, key=lambda t: t[2])) for line in lines)
    scores = [b[4] for b in boxes]
    return OcrResult(text, round(statistics.fmean(scores) * 100, 1), sum(len(b[3].split()) for b in boxes))


def run(image: Image.Image, psm: int = 6, whitelist: str | None = None, lang: str | None = None) -> OcrResult:
    if engine() == "rapidocr":
        return _run_rapidocr(image)  # psm/whitelist no aplican a RapidOCR
    cmd = config.tesseract_cmd()
    if not cmd:
        raise RuntimeError("No hay motor OCR disponible (instala Tesseract o rapidocr-onnxruntime).")
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
