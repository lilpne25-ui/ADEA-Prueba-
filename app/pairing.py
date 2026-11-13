"""Asociación de anverso y reverso. Nunca por simple orden de carpeta.

Fuentes de asociación, de mayor a menor confianza:
  1. `grupo` + `cara` declarados explícitamente por la persona usuaria en la interfaz ⇒ "explicita".
  2. Sufijos de nombre de archivo (_frente / _reverso …) ⇒ "nombre_de_archivo" (tentativa).
Toda asociación nace TENTATIVA; solo la confirmación humana (`confirmada=True`) la vuelve definitiva.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from app import validation as v

SIDE_SUFFIX = re.compile(r"^(.*?)[_\-\s](FRENTE|ANVERSO|FRONT|REVERSO|ATRAS|BACK)$", re.I)
FRONT_WORDS = ("FRENTE", "ANVERSO", "FRONT")


def match_side(filename: str) -> tuple[str, str] | None:
    path = PurePosixPath(filename.replace("\\", "/"))
    match = SIDE_SUFFIX.fullmatch(path.stem)
    if not match or not match.group(1):
        return None
    side = "front" if match.group(2).upper() in FRONT_WORDS else "back"
    return str(path.parent / match.group(1)).upper(), side


def _key(item: dict[str, Any]) -> tuple[str, str, str] | None:
    group, side = item.get("grupo"), item.get("cara")
    if group and side in ("front", "back"):
        return f"G:{group}", side, "explicita"
    guessed = match_side(item.get("archivo", ""))
    return (f"N:{guessed[0]}", guessed[1], "nombre_de_archivo") if guessed else None


def link_sides(items: list[dict[str, Any]]) -> None:
    buckets: dict[str, dict[str, tuple[dict[str, Any], str]]] = {}
    for item in items:
        k = _key(item)
        if k and "campos" in item:
            buckets.setdefault(k[0], {})[k[1]] = (item, k[2])
    for group in buckets.values():
        if "front" not in group or "back" not in group:
            continue
        (front, origin_f), (back, origin_b) = group["front"], group["back"]
        origin = "explicita" if origin_f == origin_b == "explicita" else "nombre_de_archivo"
        confirmed = bool(front.get("confirmada") and back.get("confirmada"))
        front["reverso"] = {"archivo": back["archivo"], "mrz": back["mrz"], "codigos": back["codigos"]}
        front["consistencia"] = v.cross_checks(front["campos"], back["mrz"])
        front["vinculacion"] = {
            "origen": origin, "reverso": back["archivo"],
            "estado": "confirmada" if confirmed else "tentativa",
            "mensaje": ("Asociación confirmada por la persona usuaria." if confirmed else
                        "Asociación TENTATIVA: revisa visualmente que ambas caras pertenecen al mismo documento."),
        }
        back["vinculacion"] = {"origen": origin, "anverso": front["archivo"],
                               "estado": front["vinculacion"]["estado"], "mensaje": front["vinculacion"]["mensaje"]}
        if back["estado"] == "descartado" and back["senales"].get("fuertes", 0) == 0:
            back["estado"] = "revision"
            back["clasificacion"] = "posible_reverso"
            back["evidencias"].append("Posible reverso asociado por la persona usuaria/nombre; sin evidencia autónoma")
        failed = [c for c in front["consistencia"] if c["resultado"] is False]
        front["alertas"] = [a for a in front["alertas"] if not a.startswith("Inconsistencia:")] + \
                           [f"Inconsistencia: {c['prueba']}" for c in failed]
        if failed and front["estado"] == "listo":
            front["estado"] = "revision"
        front["expediente"] = {
            "estado": "completo" if (confirmed and front["estado"] == "listo" and back["mrz"].get("lineas_validas"))
            else "pendiente_de_revision",
            "faltante": [] if back["mrz"].get("lineas_validas") else ["MRZ legible del reverso"],
        }
