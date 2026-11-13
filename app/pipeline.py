"""Orquestación: imagen → localización → preprocesamiento comparado → OCR → extracción → clasificación.

El análisis nunca escribe imágenes en disco. El `Processor` recibe la función OCR por inyección para
poder probar la lógica sin Tesseract; las pruebas con OCR real se marcan aparte.
"""

from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app import classification, extraction, imaging, ocr as ocr_engine
from app import validation as v
from app.imaging import InvalidImage, adaptive_binarize, cv2  # noqa: F401  (re-export)
from app.validation import CURP_RE, ELECTOR_RE  # noqa: F401  (re-export)

try:
    import zxingcpp  # type: ignore
except ImportError:  # pragma: no cover
    zxingcpp = None

OcrFn = Callable[..., ocr_engine.OcrResult]
MRZ_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"


def decode_codes(image: Image.Image) -> list[dict[str, str]]:
    """QR y PDF417 con ZXing-cpp. Intenta imagen completa y una versión ampliada."""
    if zxingcpp is None:
        return []
    found: dict[tuple[str, str], dict[str, str]] = {}
    try:
        for attempt in (image, image.resize((image.width * 2, image.height * 2))):
            for item in zxingcpp.read_barcodes(np.asarray(attempt.convert("L"))):
                if item.text:
                    kind = str(item.format).replace("BarcodeFormat.", "")
                    found[(kind, item.text)] = {"tipo": kind, "valor": item.text[:512]}
            if found:
                break
    except (ValueError, RuntimeError):
        return []
    return list(found.values())


def _score(res: ocr_engine.OcrResult) -> float:
    """Calidad medible de lectura: confianza media de Tesseract ponderada por cantidad de palabras."""
    if res.mean_confidence is None:
        return 0.0
    return round(res.mean_confidence * min(res.words, 60) / 60, 1)


_VOCAB = ("ELECTORAL", "CREDENCIAL", "VOTAR", "NOMBRE", "DOMICILIO", "CURP", "CLAVE", "ELECTOR", "SECCION",
          "MUNICIPIO", "LOCALIDAD", "EMISION", "VIGENCIA", "REGISTRO", "INSTITUTO", "NACIONAL")


def _vocab_hits(text: str) -> int:
    t = extraction.plain(text)
    return sum(1 for word in _VOCAB if word in t)


@dataclass
class Processor:
    ocr_fn: OcrFn = ocr_engine.run

    def _read(self, image: Image.Image, **kw) -> ocr_engine.OcrResult:
        out = self.ocr_fn(image, **kw)
        if isinstance(out, str):  # compatibilidad con OCR simulado que solo devuelve texto
            return ocr_engine.OcrResult(out, 80.0, len(out.split()))
        return out

    def _read_mrz(self, image: Image.Image) -> tuple[list[str], list[str]]:
        """OCR de la banda inferior con alfabeto restringido; se elige la variante con más
        dígitos verificadores coincidentes (criterio medible)."""
        band = image.crop((0, int(image.height * .60), image.width, image.height))
        band = imaging.upscale_if_small(band, 1500)
        best: tuple[int, list[str], list[str]] = (-1, [], [])
        preps = [lambda b: b.convert("L"), imaging.adaptive_binarize]
        if ocr_engine.engine() == "rapidocr":
            preps = preps[:1]
        for prep in preps:
            try:
                text = self._read(prep(band), psm=6, whitelist=MRZ_WHITELIST, lang="eng").text
            except RuntimeError:
                continue
            notes: list[str] = []
            lines = extraction.normalize_mrz_lines(text, notes)
            parsed = v.parse_mrz(lines)
            score = (3 if parsed["lineas_validas"] else 0) + sum(c["coincide"] for c in parsed["verificadores"])
            if score > best[0]:
                best = (score, lines, notes)
        return best[1], best[2]

    def process(self, data: bytes, filename: str = "imagen.jpg") -> dict[str, Any]:
        started = time.monotonic()
        original = imaging.load(data)
        visual = imaging.visual_features(original)
        loc = imaging.locate_card(original)
        card = loc.image
        if max(card.size) > 1800:
            card = card.copy()
            card.thumbnail((1800, 1800))

        # --- Comparación de estrategias de preprocesamiento (se elige por calidad de lectura medida)
        comparison, reads = [], {}
        candidates = imaging.variants(card)
        if ocr_engine.engine() == "rapidocr":
            # RapidOCR ya normaliza internamente y es ~5× más lento por pasada en CPU: se comparan
            # solo dos estrategias para respetar los límites de tiempo de una función serverless.
            candidates = {k: candidates[k] for k in ("original", "gris_contraste") if k in candidates}
        for name, variant in candidates.items():
            res = self._read(variant, psm=6)
            reads[name] = (variant, res)
            comparison.append({"estrategia": name, "confianza_media": res.mean_confidence,
                               "palabras": res.words, "puntuacion": _score(res)})
        best_name = max(reads, key=lambda k: _score(reads[k][1]))
        best_img, best_res = reads[best_name]
        orientation = "sin cambios"
        if _vocab_hits(best_res.text) < 2:
            # Sin vocabulario de credencial legible: ¿la imagen está girada? Se prueban 90/180/270°
            # y solo se adopta un giro que haga aparecer vocabulario (criterio medible, no suposición).
            winner = None
            for angle in (180, 90, 270):
                rot = best_img.rotate(angle, expand=True)
                res = self._read(rot, psm=6)
                hits = _vocab_hits(res.text)
                if hits >= 2 and hits > (winner[3] if winner else _vocab_hits(best_res.text)):
                    winner = (angle, rot, res, hits)
                    if hits >= 4:
                        break
            if winner:
                angle, best_img, best_res, hits = winner
                orientation = f"rotada {angle}° ({hits} términos de credencial legibles tras el giro)"
        comparison_note = f"Mejor estrategia: {best_name}"

        ordered = [best_res.text] + [r.text for n, (_, r) in reads.items() if n != best_name]

        # --- MRZ: banda inferior con alfabeto restringido
        mrz_lines, mrz_notes = self._read_mrz(best_img)
        if len(mrz_lines) != 3:  # el reverso puede venir sin pasar por la tarjeta localizada
            alt_lines, alt_notes = self._read_mrz(original)
            if len(alt_lines) == 3:
                mrz_lines, mrz_notes = alt_lines, alt_notes

        codes = decode_codes(card) or decode_codes(original)
        info = extraction.extract(ordered, mrz_lines, codes)
        if mrz_notes and info["mrz"].get("lineas"):
            info["mrz"]["correcciones_ocr"] = mrz_notes
            info["mrz"]["nota"] = "MRZ con corrección posicional de caracteres OCR: hipótesis, no dato confirmado."
        category, evidence, signals = classification.classify("\n".join(ordered), info, visual, loc.found)

        status = {"ine": "revision", "revision": "revision", "no_ine": "descartado"}[category]
        campos = info["campos"]
        if category == "ine" and campos["curp"]["estado"] == v.VALIDADO \
                and campos["clave_elector"]["estado"] == v.VALIDADO \
                and all(c["resultado"] is not False for c in info["consistencia"]):
            status = "listo"
        alerts = [a for f in campos.values() for a in f["alertas"]]
        alerts += [f"Inconsistencia: {c['prueba']}" for c in info["consistencia"] if c["resultado"] is False]

        keep_text = category != "no_ine"
        return {
            "archivo": filename[:128], "sha256": hashlib.sha256(data).hexdigest(),
            "clasificacion": category, "estado": status, "evidencias": evidence, "senales": signals,
            "campos": campos, "mrz": info["mrz"], "codigos": codes, "consistencia": info["consistencia"],
            "nombre_completo_ocr": info["nombre_completo_ocr"], "domicilio_texto": info["domicilio_texto"],
            "alertas": alerts, "ocr": best_res.text[:5000] if keep_text else "",
            "preview_original": imaging.to_data_uri(original),
            "preview_limpieza": imaging.to_data_uri(best_img),
            "tecnicas": {
                "tarjeta_localizada": loc.found, "warp_perspective": loc.perspective_applied,
                "notas_localizacion": loc.notes, "orientacion": orientation,
                "estrategias_comparadas": comparison, "estrategia_elegida": best_name,
                "nota": comparison_note, "ocr": "Tesseract local", "idioma_ocr": __import__("app.config", fromlist=["x"]).ocr_lang(),
                "opencv": cv2 is not None, "qr_pdf417": zxingcpp is not None,
                "caracteristicas_visuales": visual,
            },
            "duracion_ms": round((time.monotonic() - started) * 1000),
            "persistencia": {"estado": "pendiente"},
        }


# ---------------------------------------------------------------------------------------------
def _curp_with_digit(prefix17: str) -> str:
    return prefix17 + str(v.curp_check_digit(prefix17))


SYNTH = {
    "curp": _curp_with_digit("PUDA991231MMCBNN7"),
    "elector": "PRDEAN99123115M678",
}


def synthetic_ine() -> bytes:
    """Credencial ficticia: NO reproduce un documento oficial ni contiene datos reales."""
    im = Image.new("RGB", (1100, 700), (247, 249, 252))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((18, 18, 1080, 680), radius=30, outline="#234473", width=8)
    fonts = {}
    for key, name, size in (("big", "arialbd.ttf", 34), ("m", "arial.ttf", 26), ("s", "arial.ttf", 22)):
        for path in (name, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if key == "big"
                     else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                fonts[key] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        fonts.setdefault(key, ImageFont.load_default())
    d.text((52, 40), "INSTITUTO NACIONAL ELECTORAL", fill="#15315f", font=fonts["big"])
    d.text((52, 90), "CREDENCIAL PARA VOTAR", fill="#15315f", font=fonts["m"])
    d.rectangle((50, 150, 290, 430), fill="#d7dfeb")
    d.text((105, 275), "FOTO", fill="#8394a8", font=fonts["big"])
    rows = [("NOMBRE", 150), ("DEMO", 182), ("PRUEBA", 212), ("ANA", 242),
            ("DOMICILIO", 285), ("CALLE EJEMPLO 10", 315), ("COL CENTRO 50000", 345), ("TOLUCA, MEXICO", 375),
            (f"CURP {SYNTH['curp']}", 420), (f"CLAVE DE ELECTOR {SYNTH['elector']}", 455)]
    for text, y in rows:
        d.text((320, y), text, fill="#142b50", font=fonts["m"] if text in ("NOMBRE", "DOMICILIO") else fonts["s"])
    d.text((50, 520), "ESTADO 15  SECCION 1234  MUNICIPIO 001  LOCALIDAD 0001", fill="#142b50", font=fonts["s"])
    d.text((50, 560), "REGISTRO 2020  EMISION 2021  VIGENCIA 2031", fill="#142b50", font=fonts["s"])
    d.text((50, 630), "MUESTRA FICTICIA / DOCUMENTO NO VALIDO", fill="#a22b32", font=fonts["s"])
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
