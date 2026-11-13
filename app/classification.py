"""Clasificación híbrida (heurística + señales visuales). NO es un modelo entrenado.

Alternativas evaluadas (ver docs/ARQUITECTURA.md): A heurísticas de texto, B características visuales,
C clasificador entrenado, D híbrida. Se implementa D con reglas explícitas porque no existe un banco
autorizado de ejemplos para entrenar C. Una CURP o una clave con formato válido, por sí solas, NUNCA
bastan: otros documentos (actas, constancias) también las contienen.
"""

from __future__ import annotations

import re
from typing import Any

from app.extraction import plain
from app import validation as v

INE = "ine"
NO_INE = "no_ine"
REVISION = "revision"
ERROR = "error"

_LABELS = ("CLAVE DE ELECTOR", "SECCION", "MUNICIPIO", "LOCALIDAD", "EMISION", "VIGENCIA", "DOMICILIO", "ANO DE REGISTRO")


def classify(text: str, extraction: dict[str, Any], visual: dict[str, Any],
             card_found: bool) -> tuple[str, list[str], dict[str, Any]]:
    t = plain(text)
    tn = t.replace(" ", "")  # algunos motores OCR (RapidOCR) omiten espacios: se compara también sin ellos

    def has(phrase: str) -> bool:
        return phrase in t or phrase.replace(" ", "") in tn

    campos = extraction["campos"]
    strong: list[str] = []
    structure: list[str] = []
    negative: list[str] = []

    if has("INSTITUTO NACIONAL ELECTORAL") or has("INSTITUTO FEDERAL ELECTORAL"):
        strong.append("Emisor INE/IFE en encabezado")
    if has("CREDENCIAL PARA VOTAR"):
        strong.append("Leyenda «CREDENCIAL PARA VOTAR»")
    mrz = extraction["mrz"]
    if mrz.get("lineas_validas") and mrz.get("emisor") == "MEX":
        strong.append("MRZ de 3 líneas con emisor MEX")
    for code in extraction["codigos"]:
        if re.search(r"ine\.mx|ine\.org", code.get("valor", ""), re.I):
            strong.append("Código QR/PDF417 que referencia al INE")
            break

    labels = [lab for lab in _LABELS if has(lab)]
    if len(labels) >= 3:
        structure.append(f"{len(labels)} etiquetas electorales ({', '.join(labels[:4])}…)")
    if campos["clave_elector"]["estado"] in (v.VALIDADO, v.PENDIENTE):
        structure.append("Clave de elector con formato válido")
    if campos["curp"]["estado"] in (v.VALIDADO, v.PENDIENTE):
        structure.append("CURP con formato válido")
    if mrz.get("verificadores") and all(c["coincide"] for c in mrz["verificadores"]):
        structure.append("Dígitos verificadores MRZ coinciden")
    if extraction["codigos"]:
        structure.append("Código QR/PDF417 decodificado")
    if card_found and 1.4 <= float(visual.get("relacion_aspecto", 0)) <= 1.8:
        structure.append("Contorno con proporción de tarjeta ID-1")
    if card_found and visual.get("bloque_foto_izquierda"):
        structure.append("Bloque de fotografía a la izquierda")

    # Documentos que contienen CURP pero son claramente otra cosa.
    if re.search(r"(ACTA ?DE ?NACIMIENTO|CONSTANCIA ?DE ?SITUACION|CONTRATO|ESCRITURA|LICENCIA)", t):
        negative.append("Leyendas de documento ajeno (acta, constancia, contrato, escritura o licencia)")

    signals = {"fuertes": len(strong), "estructurales": len(structure), "negativas": len(negative),
               "criterio": "≥1 señal fuerte y ≥2 estructurales ⇒ INE; evidencia parcial ⇒ revisión"}
    evidence = strong + structure

    if visual.get("imagen_vacia"):
        return NO_INE, ["Imagen sin contenido (contraste casi nulo)"], signals
    if negative and not strong:
        return NO_INE, evidence + negative, signals
    if strong and len(structure) >= 2 and not negative:
        return INE, evidence, signals
    if strong or len(structure) >= 2 and len(labels) >= 2:
        return REVISION, evidence, signals
    return NO_INE, evidence, signals
