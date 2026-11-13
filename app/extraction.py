"""Extracción explicable de campos a partir de texto OCR.

Principios:
- Solo se reporta lo que el OCR leyó; lo ausente queda NO_DETECTADO.
- La corrección de caracteres OCR por contexto se registra aparte (`correcciones_ocr`) y el valor
  corregido queda PENDIENTE_CONFIRMACION: una hipótesis nunca se convierte en dato confirmado.
- Perfiles por región configurables (REGION_PROFILES). Solo el perfil del MRZ está comprobado con
  muestras sintéticas; los demás requieren calibración con documentos autorizados (PENDIENTE).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

from app import validation as v

# Regiones fraccionarias (x0, y0, x1, y1) por perfil de credencial. Configurables.
REGION_PROFILES: dict[str, dict[str, tuple[float, float, float, float]]] = {
    "horizontal_generico": {
        "mrz": (0.0, 0.62, 1.0, 1.0),
        "datos_electorales": (0.0, 0.55, 1.0, 0.95),
    },
}

_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}
_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}
_CURP_SHAPE = "LLLLDDDDDDLLLLLLAD"      # L letra, D dígito, A alfanumérico
_ELECTOR_SHAPE = "LLLLLLDDDDDDDDLDDD"


def plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.upper()) if not unicodedata.combining(c))


def _shape_correct(raw: str, shape: str) -> tuple[str, list[str]]:
    """Sustituye caracteres ambiguos según la posición esperada y documenta cada cambio."""
    out, changes = [], []
    for i, (ch, kind) in enumerate(zip(raw, shape)):
        new = ch
        if kind == "D" and not ch.isdigit() and ch in _TO_DIGIT:
            new = _TO_DIGIT[ch]
        elif kind == "L" and ch.isdigit() and ch in _TO_LETTER:
            new = _TO_LETTER[ch]
        if new != ch:
            changes.append(f"pos {i + 1}: '{ch}'→'{new}'")
        out.append(new)
    return "".join(out) + raw[len(shape):], changes


def _candidates(text: str, label: str, length: int = 18) -> list[str]:
    """Cadenas alfanuméricas de ~`length` caracteres, cerca de la etiqueta o sueltas."""
    t = plain(text)
    found: list[str] = []
    for m in re.finditer(label, t):
        tail = re.sub(r"[^A-Z0-9]", "", t[m.end():m.end() + length + 8].split("\n")[0])
        if len(tail) >= length - 1:
            found.append(tail[:length])
    for m in re.finditer(r"[A-Z0-9]{%d,%d}" % (length - 1, length + 1), t):
        found.append(m.group(0)[:length])
    return found


def _pick_identifier(texts: list[str], label: str, shape: str, regex: re.Pattern[str],
                     validator) -> dict[str, Any]:
    """Consenso entre variantes de preprocesamiento; exacto > corregido; registra evidencia."""
    exact: Counter[str] = Counter()
    fixed: dict[str, tuple[str, list[str]]] = {}
    for text in texts:
        for cand in dict.fromkeys(_candidates(text, label, len(shape))):  # únicos por lectura
            if len(cand) == len(shape) and regex.fullmatch(cand):
                exact[cand] += 1
            else:
                corrected, changes = _shape_correct(cand, shape)
                if len(corrected) == len(shape) and regex.fullmatch(corrected) and changes:
                    fixed.setdefault(corrected, (cand, changes))
    if exact:
        value, count = exact.most_common(1)[0]
        res = validator(value)
        res["evidencia"] = f"Leído sin correcciones en {count} de {len(texts)} variantes de imagen."
        century_clash = (shape == _CURP_SHAPE and value[16].isalpha() and int(value[4:6]) > 26)
        if shape == _CURP_SHAPE and (century_clash or any("verificador" in a for a in res["alertas"])):
            # La posición 17 admite letra o dígito: O/0 e I/1 son indistinguibles para el OCR.
            # Se acepta una alternativa solo si hace coincidir el dígito verificador (evidencia medible),
            # y siempre queda como hipótesis pendiente de confirmación.
            swaps = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B"}
            alt_char = swaps.get(value[16])
            if alt_char:
                alt = value[:16] + alt_char + value[17]
                alt_res = validator(alt, value, [f"pos 17: '{value[16]}'→'{alt_char}'"])
                better = (not any("verificador" in a for a in alt_res["alertas"])) and \
                         (alt_char.isdigit() if century_clash else True)
                if better:
                    alt_res["estado"] = v.PENDIENTE
                    alt_res["evidencia"] = ("Posición 17 ambigua (O/0, I/1…): la variante elegida cuadra con el dígito "
                                            "verificador y con la regla de siglo. Hipótesis a confirmar.")
                    return alt_res
        return res
    if fixed:
        value, (raw, changes) = next(iter(fixed.items()))
        res = validator(value, raw, changes)
        res["estado"] = v.PENDIENTE
        res["evidencia"] = "Valor obtenido tras corrección contextual de caracteres OCR."
        return res
    return v.missing()


def _lines_after(lines: list[str], label_re: str, count: int, stoppers: str) -> list[str]:
    for i, line in enumerate(lines):
        m = re.search(label_re, plain(line))
        if not m:
            continue
        out = []
        rest = plain(line)[m.end():].strip(" :.-")
        if len(rest) > 2:
            out.append(rest)
        for nxt in lines[i + 1:i + 1 + count + 1]:
            p = plain(nxt).strip(" :.-")
            if re.search(stoppers, p):
                break
            if len(p) > 1:
                out.append(p)
            if len(out) >= count:
                break
        return out
    return []


_STOP = r"\b(DOMICILIO|CLAVE DE ELECTOR|CURP|FECHA DE NACIMIENTO|SEXO|SECCION|ESTADO|MUNICIPIO|LOCALIDAD|EMISION|VIGENCIA|REGISTRO)\b"


def _text_field(value: str | None) -> dict[str, Any]:
    return v.field(value, v.DETECTADO) if value else v.missing()


def extract(texts: list[str], mrz_lines: list[str] | None = None,
            barcodes: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """`texts`: lecturas OCR de varias variantes; la primera es la mejor puntuada."""
    best = texts[0] if texts else ""
    lines = [x.strip() for x in best.splitlines() if x.strip()]
    curp = _pick_identifier(texts, r"\bCURP", _CURP_SHAPE, v.CURP_RE, v.validate_curp)
    elector = _pick_identifier(texts, r"CLAVE\s*DE\s*ELECTOR", _ELECTOR_SHAPE, v.ELECTOR_RE, v.validate_elector)

    # --- Nombre: en la credencial cada elemento suele ir en su propia línea (paterno/materno/nombres).
    name_lines = _lines_after(lines, r"\bNOMBRE\b", 3, _STOP)
    paterno = materno = nombres = None
    name_alerts: list[str] = []
    if len(name_lines) >= 3:
        paterno, materno, nombres = name_lines[0], name_lines[1], " ".join(name_lines[2:])
    elif name_lines:
        name_alerts.append("Texto de nombre con menos de 3 líneas: no se separan apellidos para no inventar.")
    full = " ".join(name_lines) if name_lines else None

    def part(value, alerts=None):
        res = _text_field(value)
        if value is None and name_alerts:
            res["alertas"] = list(name_alerts)
            res["estado"] = v.PENDIENTE if full else v.NO_DETECTADO
        return res

    # --- Domicilio
    home_lines = _lines_after(lines, r"\bDOMICILIO\b", 3, _STOP)
    home_text = " ".join(home_lines) if home_lines else None
    cp = re.search(r"(?<!\d)(\d{5})(?!\d)", home_text or "")
    street = ext = interior = colonia = municipio_dom = estado_dom = None
    if home_lines:
        first = home_lines[0]
        m_int = re.search(r"\b(?:INT|INTERIOR)\.?\s*([A-Z0-9-]+)\b", first)
        interior = m_int.group(1) if m_int else None
        first_wo_int = re.sub(r"\b(?:INT|INTERIOR)\.?\s*[A-Z0-9-]+\b", "", first).strip()
        m_num = re.search(r"^(.*?)(?:\bNO\.?\s*|\s)(\d+[A-Z]?)\s*$", first_wo_int)
        if m_num:
            street, ext = m_num.group(1).strip(" ,") or None, m_num.group(2)
        else:
            street = first_wo_int or None
        for ln in home_lines[1:]:
            m_col = re.search(r"\bCOL(?:ONIA)?\.?\s*(.+?)(?:\s*(?:C\.?P\.?\s*)?\d{5})?$", ln)
            if m_col and not colonia:
                colonia = m_col.group(1).strip()
        if len(home_lines) >= 3:
            tail = home_lines[-1].strip(" .")
            if "," in tail:
                municipio_dom, estado_dom = [s.strip(" .") for s in tail.split(",", 1)]
        elif len(home_lines) == 1:
            m_col = re.search(r"\bCOL(?:ONIA)?\.?\s+(.+?)(?:\s+(?:C\.?P\.?\s*)?\d{5})?$", first)
            colonia = m_col.group(1).strip() if m_col else None
            if m_col:
                street = None
                before = first[:m_col.start()].strip()
                street = re.sub(r"\s+\d+[A-Z]?\s*$", "", before).strip() or None
                m_n = re.search(r"(\d+[A-Z]?)\s*$", before)
                ext = m_n.group(1) if m_n else None

    def electoral(key: str, pattern: str) -> dict[str, Any]:
        # (?<![A-Z]) y (?!\d) en lugar de \b: tolera OCR sin espacios ("REGISTRO2020EMISION2021").
        m = re.search(r"(?<![A-Z])" + key + r"\s*[:.\-]?\s*(" + pattern + r")(?!\d)", plain(best))
        return _text_field(m.group(1) if m else None)

    campos = {
        "curp": curp, "clave_elector": elector,
        "apellido_paterno": part(paterno), "apellido_materno": part(materno), "nombres": part(nombres),
        "calle": _text_field(street), "numero_exterior": _text_field(ext), "numero_interior": _text_field(interior),
        "colonia": _text_field(colonia),
        "codigo_postal": v.field(cp.group(1), v.DETECTADO) if cp else v.missing(),
        "municipio_domicilio": _text_field(municipio_dom), "estado_domicilio": _text_field(estado_dom),
        "estado_electoral": electoral("ESTADO", r"\d{1,2}"), "seccion": electoral(r"SECC?ION", r"\d{1,5}"),
        "municipio_electoral": electoral("MUNICIPIO", r"\d{1,3}"), "localidad": electoral("LOCALIDAD", r"\d{1,4}"),
        "anio_registro": electoral(r"(?:ANO\s*DE\s*REGISTRO|REGISTRO)", r"\d{4}"),
        "emision": electoral("EMISION", r"\d{4}"),
        "vigencia": electoral("VIGENCIA", r"\d{4}(?:\s*[-/]\s*\d{4})?"),
    }
    mrz = v.parse_mrz(mrz_lines or [])
    return {
        "campos": campos,
        "nombre_completo_ocr": full,
        "domicilio_texto": home_text,
        "mrz": mrz,
        "codigos": barcodes or [],
        "consistencia": v.cross_checks(campos, mrz),
    }


_MRZ_SHAPES = {
    0: "LLLLLAAAAAAAAADFFFFFFFFFFFFFFF",   # IDMEX + n.º documento + verificador + relleno
    1: "DDDDDDDLDDDDDDDLLLFFFFFFFFFFFD",   # nacimiento, sexo, vencimiento, nacionalidad, relleno, compuesto
}


def _mrz_positional(line: str, shape: str) -> tuple[str, list[str]]:
    """Corrección posicional documentada: en zonas de relleno solo puede haber '<'; en zonas numéricas,
    dígitos. Cada cambio se registra; el resultado sigue siendo una hipótesis (no un dato confirmado)."""
    out, notes = [], []
    aligned = len(line) == len(shape)  # con longitud distinta las posiciones no son fiables
    for i, ch in enumerate(line[:len(shape)]):
        kind, new = shape[i], ch
        if kind == "F" and ch != "<":
            new = "<"
        elif not aligned:
            pass
        elif kind == "D" and not ch.isdigit() and ch in _TO_DIGIT:
            new = _TO_DIGIT[ch]
        elif kind == "L" and ch.isdigit() and ch in _TO_LETTER:
            new = _TO_LETTER[ch]
        if new != ch:
            notes.append(f"pos {i + 1}: '{ch}'→'{new}'")
        out.append(new)
    return "".join(out) + line[len(shape):], notes


def normalize_mrz_lines(text: str, corrections: list[str] | None = None) -> list[str]:
    """Líneas candidatas a MRZ (alfabeto A-Z0-9<). Recorta basura previa a «ID…» y corrige por posición."""
    cleaned = []
    for raw in text.splitlines():
        ln = plain(raw).replace(" ", "").replace("«", "<").replace("‹", "<").replace("{", "<")
        ln = re.sub(r"[^A-Z0-9<]", "", ln)
        if "IDMEX" in ln:
            ln = ln[ln.index("IDMEX"):]
        if 24 <= len(ln) <= 34 and ln.count("<") >= 2:
            cleaned.append(ln)
    cleaned = cleaned[-3:] if len(cleaned) >= 3 else cleaned
    if len(cleaned) == 3:
        for idx in (0, 1):
            cleaned[idx], notes = _mrz_positional(cleaned[idx], _MRZ_SHAPES[idx])
            if corrections is not None:
                corrections.extend(f"línea {idx + 1} {n}" for n in notes)
        # Línea 3: los restos aislados de 1 carácter tras el nombre son relleno mal leído.
        head, _, tail = cleaned[2].partition("<<")
        parts = tail.split("<")
        while parts and (parts[-1] == "" or (len(parts[-1]) == 1 and parts[-1] in "KCLES")):
            if parts[-1] and corrections is not None:
                corrections.append(f"línea 3: se descartó '{parts[-1]}' como relleno mal leído")
            parts.pop()
        cleaned[2] = head + "<<" + "<".join(parts) if tail else cleaned[2]
        cleaned[2] = cleaned[2].ljust(30, "<")
    return cleaned
