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
        ranked = []
        for candidate, candidate_count in exact.items():
            candidate_result = validator(candidate)
            ranked.append((candidate_result["estado"] == v.VALIDADO, -len(candidate_result["alertas"]),
                           candidate_count, candidate, candidate_result))
        _, _, count, value, res = max(ranked, key=lambda item: item[:3])
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


def _blocks_after(texts: list[str], label_re: str, count: int, stoppers: str) -> list[list[str]]:
    blocks = []
    for text in texts:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        block = _lines_after(lines, label_re, count, stoppers)
        if block:
            blocks.append(block)
    return blocks


def _consensus_text(values: list[str], *, trim_short_noise: bool = True) -> str | None:
    """Conserva tokens repetidos entre preprocesamientos y descarta ruido aislado.

    Con una sola lectura se conserva el texto original para no alterar el contrato
    histórico. Con varias, se exige presencia en al menos dos variantes.
    """
    values = [plain(value).strip(" :.,-_") for value in values if value]
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    tokenized = [re.findall(r"[A-Z0-9]+", value) for value in values]
    votes = Counter(token for tokens in tokenized for token in set(tokens))
    reference = max(tokenized, key=lambda tokens: sum(votes[token] for token in tokens))
    kept = [token for token in reference if votes[token] >= 2]
    particles = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "SAN"}
    while trim_short_noise and kept and len(kept[-1]) <= 2 and kept[-1] not in particles:
        kept.pop()
    return " ".join(kept) or None


def _value_below_label(text: str, label_re: str, value_re: str) -> str | None:
    """Recupera un valor en la línea inmediatamente inferior a una fila de etiquetas."""
    lines = [plain(line) for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        if not re.search(label_re, line):
            continue
        values = re.findall(value_re, lines[index + 1])
        if values:
            return values[-1] if isinstance(values[-1], str) else values[-1][0]
    return None


def _section_below_label(text: str) -> str | None:
    lines = [plain(line) for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        if not re.search(r"SECC?ION", line):
            continue
        values = re.findall(r"(?<!\d)\d{3,5}(?!\d)", lines[index + 1])
        values = [value for value in values if not 1900 <= int(value) <= 2099]
        if values:
            return values[0]
    return None


def _home_lines_from_blocks(blocks: list[list[str]]) -> list[str]:
    """Alinea domicilio por contenido para tolerar basura OCR junto a la etiqueta."""
    street_candidates, colony_candidates, place_candidates = [], [], []
    for block in blocks:
        for line in block:
            value = plain(line).strip(" :.,-_")
            if re.search(r"\bCOL(?:ONIA)?\b", value) or re.search(r"(?<!\d)\d{5}(?!\d)", value):
                colony_candidates.append(value)
            elif "," in line and not re.search(r"CLAVE|CURP|ELECTOR", value):
                place_candidates.append(value)
            elif re.search(r"(?<!\d)\d{1,4}(?!\d)", value) and not re.search(_STOP, value):
                street_candidates.append(value)
    out = []
    for candidates in (street_candidates, colony_candidates):
        value = _consensus_text(candidates, trim_short_noise=False)
        if value:
            out.append(value)
    place = _consensus_text(place_candidates, trim_short_noise=False)
    if place:
        parts = place.split()
        out.append(" ".join(parts[:-1]) + ", " + parts[-1] if len(parts) > 1 else place)
    return out


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
    name_blocks = _blocks_after(texts, r"\bNOMBRE\b", 3, _STOP)
    name_lines = name_blocks[0] if name_blocks else []
    paterno = materno = nombres = None
    name_alerts: list[str] = []
    complete_name_blocks = [block for block in name_blocks if len(block) >= 3]
    if complete_name_blocks:
        if len(complete_name_blocks) == 1:
            block = complete_name_blocks[0]
            paterno, materno, nombres = block[0], block[1], " ".join(block[2:])
        else:
            paterno = _consensus_text([block[0] for block in complete_name_blocks])
            materno = _consensus_text([block[1] for block in complete_name_blocks])
            nombres = _consensus_text([" ".join(block[2:]) for block in complete_name_blocks])
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
    home_blocks = _blocks_after(texts, r"\bDOMICILIO\b", 3, _STOP)
    home_lines = home_blocks[0] if home_blocks else []
    if len(home_blocks) >= 2:
        semantic_lines = _home_lines_from_blocks(home_blocks)
        if semantic_lines:
            home_lines = semantic_lines
    home_text = " ".join(home_lines) if home_lines else None
    cp = re.search(r"(?<!\d)(\d{5})(?!\d)", home_text or "")
    street = ext = interior = colonia = municipio_dom = estado_dom = None
    if home_lines:
        first = home_lines[0]
        m_int = re.search(r"\b(?:INT|INTERIOR)\.?\s*([A-Z0-9-]+)\b", first)
        interior = m_int.group(1) if m_int else None
        first_wo_int = re.sub(r"\b(?:INT|INTERIOR)\.?\s*[A-Z0-9-]+\b", "", first).strip()
        # Algunas credenciales imprimen edificio/departamento sin la palabra INT (p. ej. "123 C 4").
        m_unit = re.search(r"^(.*?)(?:\bNO\.?\s*|\s)(\d+[A-Z]?)\s+([A-Z])\s*(\d+)\s*$", first_wo_int)
        m_num = re.search(r"^(.*?)(?:\bNO\.?\s*|\s)(\d+[A-Z]?)\s*$", first_wo_int)
        if m_unit:
            street, ext, interior = m_unit.group(1).strip(" ,") or None, m_unit.group(2), m_unit.group(3) + m_unit.group(4)
        elif m_num:
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
        values = []
        for text in texts:
            m = re.search(r"(?<![A-Z])" + key + r"\s*[:.\-]?\s*(" + pattern + r")(?!\d)", plain(text))
            if m:
                values.append(m.group(1))
        return _text_field(Counter(values).most_common(1)[0][0] if values else None)

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
    if not campos["seccion"]["valor"]:
        values = [_section_below_label(text) for text in texts]
        values = [value for value in values if value]
        if values:
            campos["seccion"] = _text_field(Counter(values).most_common(1)[0][0])
    if not campos["anio_registro"]["valor"]:
        values = [_value_below_label(text, r"(?:ANO\s*DE\s*REGISTRO|REGISTRO)", r"(?<!\d)20\d{2}(?!\d)") for text in texts]
        values = [value for value in values if value]
        if values:
            campos["anio_registro"] = _text_field(Counter(values).most_common(1)[0][0])
    if not campos["vigencia"]["valor"]:
        values = [_value_below_label(text, r"VIGENCIA", r"20\d{2}\s*[-/]\s*20\d{2}") for text in texts]
        values = [value for value in values if value]
        if values:
            campos["vigencia"] = _text_field(Counter(values).most_common(1)[0][0])
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
    0: "LLLLLAAAAAAAAADAAAAAAAAAAAAAAA",   # IDMEX + n.º documento + verificador + datos opcionales
    1: "DDDDDDDLDDDDDDDLLLAAAAAAAAAAAD",   # nacimiento, sexo, vencimiento, nacionalidad, opcionales, compuesto
}


def _mrz_positional(line: str, shape: str) -> tuple[str, list[str]]:
    """Corrige solo posiciones inequívocas de letra/dígito.

    Las zonas opcionales TD1 aceptan datos o relleno, por lo que nunca se
    convierten a ``<`` para forzar una forma sintética. Cada cambio se registra
    y el resultado sigue siendo una hipótesis, no un dato confirmado.
    """
    out, notes = [], []
    aligned = len(line) == len(shape)  # con longitud distinta las posiciones no son fiables
    for i, ch in enumerate(line[:len(shape)]):
        kind, new = shape[i], ch
        if not aligned:
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
