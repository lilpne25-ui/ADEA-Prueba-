"""Visión computacional: localización de la credencial, perspectiva y variantes para OCR.

Cada paso informa honestamente si se aplicó. Si la tarjeta no se identifica con fiabilidad,
se trabaja sobre la imagen completa y se indica `tarjeta_localizada = False`.
"""

from __future__ import annotations

import io
import base64
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app import config

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - depende del entorno
    cv2 = None


class InvalidImage(ValueError):
    """Archivo no compatible, ilegible o de tamaño excesivo."""


Image.MAX_IMAGE_PIXELS = config.MAX_PIXELS


def load(data: bytes) -> Image.Image:
    if not data or len(data) > config.MAX_IMAGE_BYTES:
        raise InvalidImage("La imagen debe pesar entre 1 byte y 4 MB.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ("PNG", "JPEG", "WEBP", "BMP", "TIFF"):
                raise InvalidImage("Solo se admiten imágenes PNG, JPG, WEBP, BMP o TIFF.")
            if source.width * source.height > config.MAX_PIXELS:
                raise InvalidImage("La resolución supera los 14 megapíxeles permitidos.")
            return ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImage("El archivo no es una imagen válida.") from exc


@dataclass
class Localization:
    image: Image.Image
    found: bool
    perspective_applied: bool
    cropped: bool
    notes: list[str] = field(default_factory=list)
    quad: list[list[float]] | None = None


def _order_corners(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def locate_card(image: Image.Image) -> Localization:
    """Bordes (Canny) → contornos → cuadrilátero con proporción de tarjeta → warp."""
    if cv2 is None:
        return Localization(image, False, False, False, ["OpenCV no instalado: sin localización de tarjeta."])
    rgb = np.array(image)
    h, w = rgb.shape[:2]
    scale = 900 / max(h, w) if max(h, w) > 900 else 1.0
    small = cv2.resize(rgb, None, fx=scale, fy=scale) if scale != 1.0 else rgb
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    area_total = small.shape[0] * small.shape[1]
    candidates = []
    for low, high in ((40, 120), (60, 160), (20, 80)):
        edges = cv2.Canny(blur, low, high)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:16]:
            area = cv2.contourArea(contour)
            if area < area_total * 0.05:
                continue
            hull = cv2.convexHull(contour)
            peri = cv2.arcLength(hull, True)
            quad = None
            for epsilon in (0.02, 0.03, 0.04, 0.05, 0.06):
                attempt = cv2.approxPolyDP(hull, epsilon * peri, True)
                if len(attempt) == 4:
                    quad = attempt
                    break
            if quad is None:
                rect = cv2.minAreaRect(hull)
                rw, rh = rect[1]
                fill = area / max(rw * rh, 1.0)
                ratio = max(rw, rh) / max(min(rw, rh), 1.0)
                if fill >= 0.35 and 1.35 <= ratio <= 1.9:
                    quad = cv2.boxPoints(rect).reshape(4, 1, 2)
                else:
                    continue
            if len(quad) != 4:
                continue
            tl, tr, br, bl = _order_corners(quad)
            width = max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))
            height = max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))
            ratio = max(width, height) / max(min(width, height), 1.0)
            if height < 1 or not 1.35 <= ratio <= 1.9:  # proporción ID-1 ≈ 1.586
                continue
            candidates.append((area, (tl, tr, br, bl)))
        if candidates:
            break
    if not candidates:
        return Localization(image, False, False, False,
                            ["No se identificó un contorno rectangular con proporción de tarjeta."])
    area, (tl, tr, br, bl) = max(candidates, key=lambda item: item[0])
    if area > area_total * 0.97:  # el "contorno" es el marco de la foto completa
        return Localization(image, False, False, False,
                            ["El contorno coincide con el marco de la imagen; no hay tarjeta separable."])
    quad = np.array([tl, tr, br, bl], dtype=np.float32) / scale
    width = int(max(np.linalg.norm(quad[2] - quad[3]), np.linalg.norm(quad[1] - quad[0])))
    height = int(max(np.linalg.norm(quad[1] - quad[2]), np.linalg.norm(quad[0] - quad[3])))
    target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    matrix = cv2.getPerspectiveTransform(quad, target)
    warped = cv2.warpPerspective(rgb, matrix, (width, height), flags=cv2.INTER_CUBIC)
    if height > width:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        width, height = height, width
    skew = abs(float(quad[1][1] - quad[0][1])) + abs(float(quad[2][0] - quad[1][0]))
    return Localization(Image.fromarray(warped), True, True, True,
                        [f"Tarjeta localizada; perspectiva corregida ({width}×{height}px)."],
                        quad.round(1).tolist())


def upscale_if_small(image: Image.Image, min_width: int = 1200) -> Image.Image:
    if image.width >= min_width:
        return image
    factor = min_width / image.width
    return image.resize((min_width, round(image.height * factor)), Image.LANCZOS)


def variants(image: Image.Image) -> dict[str, Image.Image]:
    """Estrategias de preprocesamiento comparables. No se aplican todas indiscriminadamente."""
    base = upscale_if_small(image)
    out: dict[str, Image.Image] = {"original": base}
    gray = np.array(ImageOps.grayscale(base), dtype=np.uint8)
    if cv2 is not None:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        out["gris_contraste"] = Image.fromarray(clahe, "L")
        den = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        den = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(den)
        out["denoise_contraste"] = Image.fromarray(den, "L")
        out["binarizacion_adaptativa"] = Image.fromarray(
            cv2.adaptiveThreshold(cv2.GaussianBlur(clahe, (3, 3), 0), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 31, 11), "L")
    else:
        out["gris"] = Image.fromarray(gray, "L")
        out["autocontraste"] = ImageOps.autocontrast(Image.fromarray(gray, "L"), cutoff=1)
    return out


def adaptive_binarize(image: Image.Image) -> Image.Image:
    """Binarización adaptativa (compatibilidad con pruebas previas)."""
    gray = np.array(ImageOps.grayscale(image), dtype=np.uint8)
    if cv2 is not None:
        return Image.fromarray(cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                     cv2.THRESH_BINARY, 31, 11), "L")
    radius = 15
    padded = np.pad(gray.astype(np.float64), radius, mode="reflect")
    integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    k = radius * 2 + 1
    local = (integral[k:, k:] - integral[:-k, k:] - integral[k:, :-k] + integral[:-k, :-k]) / (k * k)
    return Image.fromarray(np.where(gray > local - 11, 255, 0).astype(np.uint8), "L")


def visual_features(image: Image.Image) -> dict[str, float | bool]:
    """Señales visuales medibles para la clasificación (no un modelo entrenado)."""
    w, h = image.size
    gray = np.array(ImageOps.grayscale(image), dtype=np.float32)
    contrast = float(gray.std())
    out: dict[str, float | bool] = {
        "relacion_aspecto": round(w / h, 3), "contraste": round(contrast, 1),
        "brillo_medio": round(float(gray.mean()), 1),
        "resolucion_ancho": w, "resolucion_alto": h,
        "imagen_vacia": contrast < 6.0,
    }
    if cv2 is not None:
        gray8 = gray.astype(np.uint8)
        edges = cv2.Canny(gray8, 60, 160)
        out["densidad_bordes"] = round(float((edges > 0).mean()), 4)
        out["nitidez_laplaciano"] = round(float(cv2.Laplacian(gray8, cv2.CV_64F).var()), 1)
        out["porcentaje_reflejo"] = round(float((gray8 >= 248).mean()) * 100, 2)
        # Bloque de retrato: región izquierda con textura moderada y sin texto denso.
        left = gray[int(h * .25):int(h * .75), int(w * .03):int(w * .33)]
        out["bloque_foto_izquierda"] = bool(left.size and 8 < left.std() < 90)
        out["calidad_insuficiente"] = bool(
            out["imagen_vacia"] or out["brillo_medio"] < 25 or out["brillo_medio"] > 245
            or out["nitidez_laplaciano"] < 12 or min(w, h) < 240
        )
    return out


def to_data_uri(image: Image.Image, max_side: int = 700, quality: int = 78) -> str:
    img = image.copy()
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")
