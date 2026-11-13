"""Entrada batch para carpetas heterogéneas: python -m app.batch --input ./imagenes

Por defecto el JSON NO incluye datos de identidad ni imágenes; solo estado, hash y conteos.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.imaging import InvalidImage
from app.pairing import link_sides
from app.persistence import persist
from app.pipeline import Processor

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SAFE_KEYS = ("archivo", "sha256", "clasificacion", "estado", "evidencias", "alertas", "duracion_ms", "persistencia",
             "vinculacion", "mensaje")


def run_batch(folder: Path, include_pii: bool = False) -> dict:
    if not folder.is_dir():
        raise ValueError("La carpeta de entrada no existe")
    paths = sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()
                   and p.suffix.lower() in EXTENSIONS)
    process = Processor()
    output = []
    for p in paths:
        name = p.relative_to(folder).as_posix()
        try:
            item = process.process(p.read_bytes(), name)
            item.pop("preview_original", None)
            item.pop("preview_limpieza", None)
            output.append(item)
        except (InvalidImage, ValueError, RuntimeError, OSError) as exc:
            output.append({"archivo": name, "estado": "error", "clasificacion": "error", "mensaje": str(exc),
                           "persistencia": {"estado": "no_ejecutada"}})
    link_sides(output)
    for item in output:
        if "campos" in item:
            item["persistencia"] = persist(item)
    if not include_pii:
        output = [{k: item[k] for k in SAFE_KEYS if k in item} for item in output]
    return {"total": len(output), "conteo": dict(Counter(x["estado"] for x in output)), "documentos": output}


def main() -> None:
    parser = argparse.ArgumentParser(description="Procesar carpeta heterogénea de imágenes")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None, help="Ruta JSON opcional (no debe existir).")
    parser.add_argument("--include-pii", action="store_true",
                        help="Incluye datos de identidad en el JSON; solo en entorno seguro y autorizado.")
    args = parser.parse_args()
    report = run_batch(args.input, args.include_pii)
    if args.output:
        if args.output.exists():
            parser.error("La ruta de salida ya existe; elige un nombre nuevo")
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
    print(json.dumps({"total": report["total"], "conteo": report["conteo"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
