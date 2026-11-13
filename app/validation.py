"""Motor de validación independiente del OCR.

Estados (nunca se afirma autenticidad; solo coherencia sintáctica y cruzada):
  DETECTADO               valor leído por OCR sin regla de formato aplicable (p. ej. nombre).
  VALIDADO_POR_FORMATO    cumple expresión regular y verificaciones internas; NO prueba autenticidad.
  PENDIENTE_CONFIRMACION  hipótesis: formato dudoso, corrección OCR aplicada o inconsistencia cruzada.
  NO_DETECTADO            no se encontró evidencia en la imagen.
  INVALIDO                se leyó un candidato que no cumple el formato.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

DETECTADO = "DETECTADO"
VALIDADO = "VALIDADO_POR_FORMATO"
PENDIENTE = "PENDIENTE_CONFIRMACION"
NO_DETECTADO = "NO_DETECTADO"
INVALIDO = "INVALIDO"

CURP_RE = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d$")
ELECTOR_RE = re.compile(r"^[A-Z]{6}\d{8}[HM]\d{3}$")

CURP_STATES = {"AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR", "HG", "JC", "MC",
               "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP", "SL", "SR", "TC", "TS", "TL", "VZ",
               "YN", "ZS", "NE"}
_CURP_ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"


def field(value: str | None, status: str, source: str = "ocr", alerts: list[str] | None = None,
          raw: str | None = None, corrections: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    out = {"valor": value, "estado": status, "fuente": source, "alertas": alerts or []}
    if raw is not None and raw != value:
        out["lectura_original"] = raw
    if corrections:
        out["correcciones_ocr"] = corrections
    out.update(extra)
    return out


def missing() -> dict[str, Any]:
    return field(None, NO_DETECTADO, source="-")


def _valid_date(yy: str, mm: str, dd: str, century: int) -> bool:
    try:
        date(century + int(yy), int(mm), int(dd))
        return True
    except ValueError:
        return False


def curp_check_digit(curp17: str) -> int:
    total = sum(_CURP_ALPHABET.index(c) * (18 - i) for i, c in enumerate(curp17[:17]))
    return (10 - total % 10) % 10


def curp_checks(curp: str) -> list[str]:
    """Verificaciones internas de una CURP que ya cumple la expresión regular. Devuelve alertas."""
    alerts: list[str] = []
    century = 1900 if curp[16].isdigit() else 2000
    if not _valid_date(curp[4:6], curp[6:8], curp[8:10], century):
        alerts.append("La fecha de nacimiento embebida no es una fecha real.")
    if curp[11:13] not in CURP_STATES:
        alerts.append("La clave de entidad de la CURP no existe.")
    if curp_check_digit(curp) != int(curp[17]):
        alerts.append("El dígito verificador de la CURP no coincide.")
    return alerts


def elector_checks(key: str) -> list[str]:
    alerts: list[str] = []
    if not any(_valid_date(key[6:8], key[8:10], key[10:12], c) for c in (1900, 2000)):
        alerts.append("La fecha embebida en la clave de elector no es una fecha real.")
    state = int(key[12:14])
    if not 1 <= state <= 33:
        alerts.append("La clave de entidad de la clave de elector está fuera de rango (01-33).")
    return alerts


def validate_curp(candidate: str | None, raw: str | None = None, corrections: list[str] | None = None) -> dict[str, Any]:
    if not candidate:
        return missing()
    if not CURP_RE.fullmatch(candidate):
        return field(candidate, INVALIDO, alerts=["No cumple el formato de CURP de 18 caracteres."], raw=raw,
                     corrections=corrections)
    alerts = curp_checks(candidate)
    if corrections:
        alerts.append("Se aplicó corrección de caracteres OCR: confirmar contra el documento.")
    status = PENDIENTE if alerts else VALIDADO
    return field(candidate, status, alerts=alerts, raw=raw, corrections=corrections)


def validate_elector(candidate: str | None, raw: str | None = None, corrections: list[str] | None = None) -> dict[str, Any]:
    if not candidate:
        return missing()
    if not ELECTOR_RE.fullmatch(candidate):
        return field(candidate, INVALIDO, alerts=["No cumple el formato de clave de elector."], raw=raw,
                     corrections=corrections)
    alerts = elector_checks(candidate)
    if corrections:
        alerts.append("Se aplicó corrección de caracteres OCR: confirmar contra el documento.")
    return field(candidate, PENDIENTE if alerts else VALIDADO, alerts=alerts, raw=raw, corrections=corrections)


def cross_checks(fields: dict[str, dict[str, Any]], mrz: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Validación cruzada entre regiones. Cada resultado es True/False/None (no evaluable)."""
    checks: list[dict[str, Any]] = []
    curp = fields["curp"]["valor"] if fields["curp"]["estado"] in (VALIDADO, PENDIENTE) else None
    elector = fields["clave_elector"]["valor"] if fields["clave_elector"]["estado"] in (VALIDADO, PENDIENTE) else None

    def add(name: str, ok: bool | None, detail: str) -> None:
        checks.append({"prueba": name, "resultado": ok, "detalle": detail})

    if curp and elector:
        add("CURP vs clave de elector: fecha de nacimiento", curp[4:10] == elector[6:12],
            "YYMMDD embebido en ambos identificadores")
        add("CURP vs clave de elector: sexo", curp[10] == elector[14], "H/M en ambos identificadores")
    else:
        add("CURP vs clave de elector", None, "Falta al menos un identificador legible.")
    if mrz and mrz.get("lineas_validas"):
        if curp and mrz.get("fecha_nacimiento"):
            add("CURP vs MRZ: fecha de nacimiento", curp[4:10] == mrz["fecha_nacimiento"], "YYMMDD")
        if curp and mrz.get("sexo"):
            compatible = {"H": {"H", "M"}, "M": {"M", "F"}}
            add("CURP vs MRZ: sexo", mrz["sexo"] in compatible.get(curp[10], set()),
                "CURP usa H/M; la MRZ puede conservar H/M o usar M/F según el modelo")
        pat = fields["apellido_paterno"]["valor"]
        if pat and mrz.get("apellidos"):
            add("Apellido paterno vs MRZ", _plain(pat).replace(" ", "") in mrz["apellidos"].replace("<", ""),
                "El apellido del frente aparece en la línea 3 del MRZ")
    else:
        add("Frente vs MRZ", None, "Sin MRZ legible; no se puede validar el reverso.")
    return checks


def _plain(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text.upper()) if not unicodedata.combining(c))


# ---- MRZ (estructura TD1 de tres líneas × 30; ICAO 9303) -------------------------------------
_MRZ_W = (7, 3, 1)


def mrz_check_digit(data: str) -> int:
    total = 0
    for i, ch in enumerate(data):
        value = 0 if ch == "<" else int(ch) if ch.isdigit() else ord(ch) - 55
        total += value * _MRZ_W[i % 3]
    return total % 10


def parse_mrz(lines: list[str]) -> dict[str, Any]:
    """Analiza 3 líneas MRZ. `lineas_validas` solo indica estructura TD1; los dígitos verificadores
    se informan uno por uno (`verificadores`) y NO se interpretan como autenticidad."""
    result: dict[str, Any] = {"lineas": lines, "lineas_validas": False, "verificadores": []}
    if len(lines) != 3:
        return result
    l1, l2, l3 = (x.ljust(30, "<")[:30] for x in lines)
    if len(lines[0]) not in range(28, 32) or len(lines[1]) not in range(28, 32) or len(lines[2]) not in range(20, 32):
        result["motivo"] = "Longitud de líneas incompatible con TD1 (30 caracteres)."
        return result
    if not l1.startswith(("I", "A", "C")):
        result["motivo"] = "La línea 1 no inicia con código de documento de identidad."
        return result
    result["lineas_validas"] = True
    result["emisor"] = l1[2:5]
    result["numero_documento"] = l1[5:14].replace("<", "")
    result["fecha_nacimiento"] = l2[0:6]
    result["sexo"] = l2[7]
    result["fecha_vencimiento"] = l2[8:14]
    result["nacionalidad"] = l2[15:18]
    parts = l3.split("<<", 1)
    result["apellidos"] = parts[0].replace("<", " ").strip()
    result["nombres"] = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
    pairs = [("documento", l1[5:14], l1[14]), ("nacimiento", l2[0:6], l2[6]), ("vencimiento", l2[8:14], l2[14])]
    for name, data, digit in pairs:
        ok = digit.isdigit() and mrz_check_digit(data) == int(digit)
        result["verificadores"].append({"campo": name, "coincide": ok})
    return result
