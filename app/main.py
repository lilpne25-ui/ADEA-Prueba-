"""API de ADEA · INE Control (FastAPI). La interfaz no contiene lógica empresarial: todo ocurre aquí."""

from __future__ import annotations

import base64
import asyncio
import binascii
import hashlib
import hmac
import json
import os
from collections import Counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import envfile

envfile.load_into_environ()  # .env.local (credenciales locales de desarrollo); el entorno real tiene prioridad

from app import config, ocr as ocr_engine, persistence  # noqa: E402
from app.imaging import InvalidImage, cv2
from app.pairing import link_sides
from app.persistence import configured, mode, persist
from app.pipeline import Processor, zxingcpp
from app.samples import SAMPLE_NAMES, sample_bytes

PUBLIC = config.ROOT / "public"
app = FastAPI(title="ADEA · INE Control", version="5.0.0", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=PUBLIC), name="static")


@app.middleware("http")
async def safe_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'"
    )
    return response


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(PUBLIC / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(PUBLIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # Servido en la raíz para que su alcance cubra toda la app.
    return FileResponse(PUBLIC / "sw.js", media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/"})


@app.get("/api/pairing")
def pairing(request: Request):
    """Emparejamiento del celular: QR con la URL de red local (HTTPS si hay certificado) y el token en el
    fragmento (#acceso=…, que el navegador no envía al servidor). Requiere estar autenticado."""
    if os.getenv("VERCEL"):
        raise HTTPException(404, "El emparejamiento solo existe en la instalación local")
    authorize(request, force=mode() == "corporate")
    import socket
    from app.pipeline import zxingcpp as zx
    ip = "127.0.0.1"
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.168.0.1", 9))  # no envía paquetes; solo elige la interfaz de la LAN
        ip = probe.getsockname()[0]
        probe.close()
    except OSError:
        pass
    https = (config.ROOT / "certs" / "local.crt").exists()
    url = f"{'https' if https else 'http'}://{ip}:{8443 if https else 8000}/"
    token = os.getenv("APP_ACCESS_TOKEN")
    if token:
        url += f"#acceso={token}"
    qr = None
    if zx is not None:
        import io
        import numpy as np
        from PIL import Image
        arr = np.asarray(zx.write_barcode(zx.BarcodeFormat.QRCode, url))
        img = Image.fromarray(arr, "L").resize((arr.shape[1] * 8, arr.shape[0] * 8), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"url_visible": url.split("#")[0], "https": https, "qr": qr,
            "aviso": None if https else "Sin HTTPS local la cámara en vivo no está disponible en el celular; "
                                         "ejecuta scripts/make_local_cert.py para habilitarla."}


def upload_enabled() -> bool:
    return config.upload_enabled()


@app.get("/api/health")
def health():
    cloud = bool(os.getenv("VERCEL"))
    status = persistence.backend_status()
    return {
        "servicio": "operativo", "modo": mode(), "corporativo_configurado": configured(),
        "carga_real_habilitada": upload_enabled(), "entorno": "nube" if cloud else "local",
        "persistencia": {"oracle": status["oracle"], "sqlserver": status["sqlserver"]},
        "motores": {"ocr": ocr_engine.engine(), "ocr_disponible": ocr_engine.available(),
                    "tesseract": ocr_engine.engine() == "tesseract",
                    "rapidocr": ocr_engine.engine() == "rapidocr",
                    "idioma_ocr": config.ocr_lang() if ocr_engine.engine() == "tesseract" else
                    ("es/en (PP-OCR)" if ocr_engine.engine() else None),
                    "opencv": cv2 is not None, "zxing_qr_pdf417": zxingcpp is not None},
    }


def authorize(request: Request, *, force: bool = False):
    token = os.getenv("APP_ACCESS_TOKEN")
    if mode() == "corporate" and not token:
        raise HTTPException(503, "El modo corporativo requiere APP_ACCESS_TOKEN")
    required = force or mode() == "corporate"
    if required and not (token and hmac.compare_digest(request.headers.get("X-Access-Token", ""), token)):
        raise HTTPException(401, "Token de acceso inválido")


@app.get("/api/samples")
def samples():
    """Muestras ficticias integradas (se generan en memoria, no se almacenan)."""
    return {"muestras": [{"archivo": n, "imagen": "data:image/png;base64," +
                          base64.b64encode(sample_bytes(n)).decode("ascii")} for n in SAMPLE_NAMES]}


@app.get("/api/sample")
def sample():
    """Compatibilidad: primera muestra."""
    return {"archivo": SAMPLE_NAMES[0], "imagen": "data:image/png;base64," +
            base64.b64encode(sample_bytes(SAMPLE_NAMES[0])).decode("ascii")}


@app.post("/api/persistence/test")
def persistence_test(request: Request):
    """Prueba real de conexión a Oracle y SQL Server. Exige token; sin credenciales devuelve NO_CONFIGURADO."""
    authorize(request, force=True)
    return persistence.test_connections()


@app.get("/api/infra")
def infrastructure(request: Request):
    """Sección INFRAESTRUCTURA: verifica conexiones reales en este momento; sin contraseñas ni PII."""
    authorize(request, force=mode() == "corporate")
    return persistence.infrastructure()


@app.post("/api/link")
async def relink(request: Request):
    """Confirma explícitamente una asociación frente/reverso y recalcula consistencia (sin reprocesar OCR)."""
    authorize(request)
    try:
        payload = await request.json()
        items = payload["resultados"]
        confirm = set(payload.get("confirmar", []))
        if not isinstance(items, list) or len(items) > config.MAX_FILES_PER_BATCH:
            raise ValueError
        for item in items:
            item["confirmada"] = item.get("archivo") in confirm
        link_sides(items)
    except Exception:
        raise HTTPException(422, "Solicitud de asociación inválida")
    return {"resultados": items}


def _name(file, index: int) -> str:
    return str(file.get("archivo", f"archivo_{index + 1}") if isinstance(file, dict) else f"archivo_{index + 1}")[:128]


async def _process_request(request: Request) -> tuple[list, bool]:
    """Valida el sobre del lote antes de iniciar cualquier trabajo OCR."""
    authorize(request)
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > config.MAX_REQUEST_BYTES:
        raise HTTPException(413, "El lote excede 4.3 MB. Reduce el tamaño de las fotografías.")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "El cuerpo debe ser JSON")
    files = payload.get("archivos") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not (1 <= len(files) <= config.MAX_FILES_PER_BATCH):
        raise HTTPException(422, f"Carga entre 1 y {config.MAX_FILES_PER_BATCH} imágenes por lote")
    if len(str(payload)) > config.MAX_REQUEST_BYTES:
        raise HTTPException(413, "El lote excede 4.3 MB")
    is_sample = payload.get("solo_muestra") is True
    if not upload_enabled() and not is_sample:
        raise HTTPException(403, "Carga de INE reales deshabilitada en esta demo pública")
    if is_sample and any(not isinstance(f, dict) or f.get("archivo") not in SAMPLE_NAMES for f in files):
        raise HTTPException(403, "La ruta de muestra solo acepta los ejemplos integrados")
    if not ocr_engine.available():
        raise HTTPException(503, "No hay un motor OCR disponible en el servidor")
    return files, is_sample


def _decode_entry(file, index: int, is_sample: bool) -> tuple[str, bytes]:
    if not isinstance(file, dict):
        raise InvalidImage("Cada entrada debe contener nombre e imagen")
    name, content = file["archivo"], file.get("imagen", "")
    if not isinstance(name, str) or not isinstance(content, str):
        raise InvalidImage("Archivo inválido")
    data = sample_bytes(name) if is_sample else base64.b64decode(content.split(",", 1)[-1], validate=True)
    return name, data


def _attach_metadata(item: dict, file: dict, is_sample: bool) -> None:
    for key in ("grupo", "cara"):
        if isinstance(file.get(key), str):
            item[key] = file[key][:64]
    item["confirmada"] = file.get("confirmada") is True
    item["muestra_ficticia"] = is_sample


def _response(results: list[dict]) -> dict:
    link_sides(results)
    for item in results:
        item["persistencia"] = persist(item)
    return {"total": len(results), "conteo": dict(Counter(i["estado"] for i in results)),
            "resultados": results, "modo": mode()}


@app.post("/api/process")
async def process(request: Request):
    files, is_sample = await _process_request(request)

    results = []
    worker = Processor()
    for index, file in enumerate(files):
        digest = None
        try:
            name, data = _decode_entry(file, index, is_sample)
            digest = hashlib.sha256(data).hexdigest()
            item = worker.process(data, name)
            _attach_metadata(item, file, is_sample)
            results.append(item)
        except (InvalidImage, ValueError, KeyError, binascii.Error, RuntimeError) as exc:
            results.append({"archivo": _name(file, index), "estado": "error", "clasificacion": "error",
                            "mensaje": str(exc), "sha256": digest,
                            "persistencia": {"estado": "no_ejecutada"}})
    return _response(results)


@app.post("/api/process-stream")
async def process_stream(request: Request):
    """Procesa el lote y transmite eventos NDJSON reales por archivo y etapa."""
    files, is_sample = await _process_request(request)

    async def events():
        results: list[dict] = []
        worker = Processor()
        loop = asyncio.get_running_loop()

        def line(event: dict) -> bytes:
            return (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

        yield line({"tipo": "lote_iniciado", "total": len(files)})
        for index, file in enumerate(files):
            digest = None
            try:
                name, data = _decode_entry(file, index, is_sample)
                digest = hashlib.sha256(data).hexdigest()
                event_queue: asyncio.Queue = asyncio.Queue()

                def notify(event: dict) -> None:
                    event["indice"] = index
                    loop.call_soon_threadsafe(event_queue.put_nowait, event)

                task = asyncio.create_task(asyncio.to_thread(worker.process, data, name, notify))
                while not task.done() or not event_queue.empty():
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=.15)
                        yield line({"tipo": "etapa", **event})
                    except asyncio.TimeoutError:
                        continue
                item = await task
                _attach_metadata(item, file, is_sample)
                results.append(item)
                yield line({"tipo": "archivo_completado", "indice": index, "archivo": name,
                            "estado": item["estado"], "clasificacion": item["clasificacion"],
                            "duracion_ms": item["duracion_ms"]})
            except (InvalidImage, ValueError, KeyError, binascii.Error, RuntimeError) as exc:
                item = {"archivo": _name(file, index), "estado": "error", "clasificacion": "error",
                        "mensaje": str(exc), "sha256": digest, "persistencia": {"estado": "no_ejecutada"}}
                results.append(item)
                yield line({"tipo": "archivo_error", "indice": index, "archivo": item["archivo"],
                            "mensaje": str(exc)})

        response = _response(results)
        yield line({"tipo": "resultado", **response})

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})
