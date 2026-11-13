"""Muestras 100% sintéticas para demos y pruebas. Ninguna contiene datos reales ni imita un documento oficial
(todas llevan una leyenda visible de invalidez)."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app import validation as v
from app.pipeline import SYNTH, synthetic_ine, zxingcpp

SAMPLE_NAMES = ("INE_FICTICIA_FRENTE.png", "INE_FICTICIA_REVERSO.png",
                "CONTRATO_FICTICIO_CON_CURP.png", "FOTO_RUIDO_FICTICIA.png")


def _font(mono: bool, size: int):
    for path in (r"C:\Windows\Fonts\consola.ttf" if mono else r"C:\Windows\Fonts\arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf" if mono
                 else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _barcode(fmt: str, text: str, scale: int, height_scale: int | None = None) -> Image.Image | None:
    if zxingcpp is None:
        return None
    arr = np.asarray(zxingcpp.write_barcode(getattr(zxingcpp.BarcodeFormat, fmt), text))
    im = Image.fromarray(arr, "L").convert("RGB")
    return im.resize((arr.shape[1] * scale, arr.shape[0] * (height_scale or scale)), Image.NEAREST)


def mrz_lines() -> list[str]:
    doc = "123456789"
    l1 = ("IDMEX" + doc + str(v.mrz_check_digit(doc))).ljust(30, "<")
    birth, expiry = "991231", "310101"
    body2 = birth + str(v.mrz_check_digit(birth)) + "F" + expiry + str(v.mrz_check_digit(expiry)) + "MEX" + "<" * 11
    composite = str(v.mrz_check_digit(l1[5:30] + body2[:7] + body2[8:15] + body2[18:29]))
    l2 = body2 + composite
    l3 = "DEMO<PRUEBA<<ANA".ljust(30, "<")
    return [l1, l2, l3]


def synthetic_back() -> bytes:
    im = Image.new("RGB", (1100, 700), (247, 249, 252))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((18, 18, 1080, 680), radius=30, outline="#234473", width=8)
    qr = _barcode("QRCode", "https://ejemplo.invalid/muestra-ficticia", 7)
    pdf = _barcode("PDF417", "MUESTRA FICTICIA NO VALIDA 0001", 5, 10)
    if qr:
        im.paste(qr, (60, 70))
    if pdf:
        im.paste(pdf, (330, 90))
    d.text((60, 410), "MUESTRA FICTICIA / DOCUMENTO NO VALIDO", fill="#a22b32", font=_font(False, 22))
    mono = _font(True, 40)
    for i, line in enumerate(mrz_lines()):
        d.text((40, 490 + i * 55), line, fill="#111111", font=mono)
    return _png(im)


def synthetic_contract_with_curp() -> bytes:
    """Documento ajeno que SÍ contiene una CURP válida: debe descartarse."""
    im = Image.new("RGB", (1000, 1300), "white")
    d = ImageDraw.Draw(im)
    f, fb = _font(False, 30), _font(False, 40)
    d.text((80, 70), "CONTRATO DE PRESTACION DE SERVICIOS", fill="black", font=fb)
    body = ["Entre las partes de ejemplo se celebra el presente contrato",
            "de caracter ficticio para pruebas del sistema.", "",
            f"El cliente declara su CURP {SYNTH['curp']}", "y acepta las clausulas siguientes:", "",
            "PRIMERA. Objeto del servicio de demostracion.", "SEGUNDA. Vigencia de un anio.",
            "TERCERA. Jurisdiccion de tribunales de ejemplo.", "", "MUESTRA FICTICIA / DOCUMENTO NO VALIDO"]
    for i, line in enumerate(body):
        d.text((80, 190 + i * 52), line, fill="black", font=f)
    return _png(im)


def synthetic_noise_photo() -> bytes:
    rng = np.random.default_rng(7)
    arr = rng.integers(60, 190, (500, 700, 3), dtype=np.uint8)
    return _png(Image.fromarray(arr).filter(ImageFilter.GaussianBlur(3)))


def sample_bytes(name: str) -> bytes:
    return {"INE_FICTICIA_FRENTE.png": synthetic_ine, "INE_FICTICIA_REVERSO.png": synthetic_back,
            "CONTRATO_FICTICIO_CON_CURP.png": synthetic_contract_with_curp,
            "FOTO_RUIDO_FICTICIA.png": synthetic_noise_photo}[name]()
