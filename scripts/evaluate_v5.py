"""Evaluación reproducible V5 con documentos 100 % ficticios.

No escribe imágenes ni resultados en disco. Imprime JSON para que CI o una
revisión técnica pueda conservar la evidencia explícitamente.
"""

from __future__ import annotations

import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import Processor, SYNTH, synthetic_ine
from app.samples import SAMPLE_NAMES, sample_bytes


def png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def jpeg(image: Image.Image, quality: int = 38) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality)
    return out.getvalue()


def passport() -> bytes:
    image = Image.new("RGB", (1100, 700), "#eef3f7")
    draw = ImageDraw.Draw(image)
    draw.rectangle((25, 25, 1075, 675), outline="#254c75", width=6)
    draw.text((75, 80), "ESTADOS UNIDOS MEXICANOS", fill="#102b4a")
    draw.text((75, 130), "PASAPORTE FICTICIO", fill="#102b4a")
    draw.text((75, 560), "P<MEXDEMO<PERSONA<<<<<<<<<<<<<<<<<<<<", fill="black")
    draw.text((75, 600), "L898902C36MEX9912315F3101012<<<<<<<<<<<<06", fill="black")
    return png(image)


def cases() -> list[dict]:
    front = Image.open(io.BytesIO(synthetic_ine())).convert("RGB")
    return [
        {"id": "ine_frente_clara", "esperado": "ine", "data": png(front), "ajuste": True},
        {"id": "ine_bajo_contraste", "esperado": "ine", "data": png(ImageEnhance.Contrast(front).enhance(.38)), "ajuste": True},
        {"id": "ine_rotada_180", "esperado": "ine", "data": png(front.rotate(180)), "ajuste": False},
        {"id": "ine_desenfoque", "esperado": "ine", "data": png(front.filter(ImageFilter.GaussianBlur(1.1))), "ajuste": False},
        {"id": "ine_jpeg_compresion", "esperado": "ine", "data": jpeg(front), "ajuste": False},
        {"id": "ine_reverso", "esperado": "ine", "data": sample_bytes(SAMPLE_NAMES[1]), "ajuste": False},
        {"id": "contrato_curp", "esperado": "no_ine", "data": sample_bytes(SAMPLE_NAMES[2]), "ajuste": False},
        {"id": "pasaporte_mrz", "esperado": "no_ine", "data": passport(), "ajuste": False},
        {"id": "foto_ruido", "esperado": "insuficiente", "data": sample_bytes(SAMPLE_NAMES[3]), "ajuste": False},
        {"id": "imagen_blanca", "esperado": "insuficiente", "data": png(Image.new("RGB", (900, 560), "white")), "ajuste": False},
    ]


def group(result: dict) -> str:
    if result["clasificacion"] in ("ine", "revision", "posible_reverso"):
        return "ine"
    if result["clasificacion"] == "imagen_insuficiente":
        return "insuficiente"
    return "no_ine"


def main() -> None:
    worker = Processor()
    rows = []
    for case in cases():
        started = time.monotonic()
        result = worker.process(case["data"], case["id"] + ".png")
        rows.append({"id": case["id"], "particion": "ajuste" if case["ajuste"] else "evaluacion",
                     "esperado": case["esperado"], "predicho": group(result),
                     "clasificacion": result["clasificacion"], "estado": result["estado"],
                     "duracion_ms": round((time.monotonic() - started) * 1000),
                     "curp_correcta": result.get("campos", {}).get("curp", {}).get("valor") == SYNTH["curp"],
                     "elector_correcto": result.get("campos", {}).get("clave_elector", {}).get("valor") == SYNTH["elector"]})
    evaluation = [r for r in rows if r["particion"] == "evaluacion"]
    positives = [r for r in evaluation if r["esperado"] == "ine"]
    negatives = [r for r in evaluation if r["esperado"] == "no_ine"]
    fields = [r for r in positives if r["id"].startswith("ine_") and r["id"] != "ine_reverso"]
    confusion = Counter((r["esperado"], r["predicho"]) for r in evaluation)
    report = {
        "dataset": {"total": len(rows), "ajuste": 2, "evaluacion": len(evaluation), "datos_reales": False},
        "metricas": {
            "exactitud_clasificacion": round(sum(r["esperado"] == r["predicho"] for r in evaluation) / len(evaluation), 4),
            "recall_ine": round(sum(r["predicho"] == "ine" for r in positives) / len(positives), 4),
            "falsos_positivos_ine": sum(r["predicho"] == "ine" for r in negatives),
            "falsos_negativos_ine": sum(r["predicho"] != "ine" for r in positives),
            "exactitud_curp": round(sum(r["curp_correcta"] for r in fields) / len(fields), 4),
            "exactitud_clave_elector": round(sum(r["elector_correcto"] for r in fields) / len(fields), 4),
            "tiempo_promedio_ms": round(sum(r["duracion_ms"] for r in evaluation) / len(evaluation)),
        },
        "matriz_confusion": {f"{a}->{p}": n for (a, p), n in sorted(confusion.items())},
        "casos": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
