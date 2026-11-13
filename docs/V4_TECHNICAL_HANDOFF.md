# V4 Technical Handoff

Documento para auditoría externa del repositorio. Proyecto independiente desarrollado como prueba técnica; no constituye software oficial de ADEA.

## 1. Arquitectura final
Un solo servicio FastAPI (`app/main.py`) con módulos de dominio planos en `app/`. Se conservó la estructura plana de V3 en lugar de la jerarquía sugerida (`app/api`, `app/core`…) porque los módulos ya están separados por responsabilidad, tienen pruebas propias y moverlos solo cambiaría rutas de importación sin beneficio funcional.

| Capa | Archivo | Responsabilidad |
|---|---|---|
| API | `app/main.py` | Rutas, límites, CSP, token, PWA, emparejamiento |
| Configuración | `app/config.py`, `app/envfile.py` | Límites, Tesseract/tessdata, `.env.local` |
| Visión | `app/imaging.py` | Carga segura, localización, perspectiva, variantes |
| OCR | `app/ocr.py` | Tesseract (TSV + confianza) o RapidOCR (ONNX) |
| Extracción | `app/extraction.py` | Campos, correcciones registradas, MRZ |
| Validación | `app/validation.py` | Estados, CURP/clave/MRZ, validación cruzada |
| Clasificación | `app/classification.py` | Reglas híbridas |
| Asociación | `app/pairing.py` | Frente/reverso tentativo → confirmado |
| Persistencia / auditoría | `app/persistence.py` | Oracle SP, SQL Server, bandeja, infraestructura |
| Orquestación | `app/pipeline.py`, `app/batch.py` | Proceso por imagen y por carpeta |
| Muestras | `app/samples.py` | Documentos 100 % sintéticos |
| UI | `public/` | HTML/CSS/JS, PWA, cámara, emparejamiento |
| Scripts | `scripts/` | Bases locales, certificado HTTPS, servidor dual |

## 2. Dependencias
`requirements.txt` (también lo instala Vercel): FastAPI, Uvicorn, Pillow, NumPy, opencv-python-headless, zxing-cpp, onnxruntime y dependencias de RapidOCR. `requirements-corporate.txt`: pyodbc, oracledb. `requirements-local.txt`: todo lo anterior + cryptography. `requirements-dev.txt`: pytest, httpx. `vendor/rapidocr_onnxruntime` (Apache-2.0, ver `vendor/NOTICE.md`) se vendoriza porque su paquete PyPI exige opencv-python con libGL.

## 3. Ejecución
- Windows: `INICIAR_WINDOWS.bat` (crea venv, instala, detecta Tesseract, arranca LocalDB y el contenedor Oracle si hay `.env.local`, servidor HTTP 8000 + HTTPS 8443).
- Manual: `python -m uvicorn app.main:app` o `python scripts/serve_local.py`.
- Batch: `python -m app.batch --input carpeta`.

## 4. Configuración de Vercel
Proyecto `adea-ine-control` (equipo vlux-s-projects), dominio de producción `https://adea-ine-control.vercel.app`. Entrada `index.py` → `app.main:app` (Python Runtime, FastAPI). `vercel.json`: `maxDuration` 120 s e `includeFiles` para `public/` y `vendor/`. `.vercelignore` excluye `.env.local`, `.venv`, `tests`, `tessdata`, `certs`, `data`. Variables: ninguna secreta; `VERCEL=1` activa automáticamente el modo público (solo muestras, `403` a cargas reales, sin emparejamiento, sin bases).

## 5. Configuración local
`.env.local` (no versionado, ACL al usuario) contiene `APP_MODE=corporate`, `APP_ACCESS_TOKEN`, credenciales de `ADEA_INE_APP` (Oracle) y `adea_ine_app` (SQL Server). Se genera con `scripts/setup_sqlserver_localdb.py` y `scripts/setup_oracle_docker.py`; `.env.example` documenta las variables sin valores reales.

## 6. Seguridad
- Auditoría previa a cada push: ningún valor de `.env.local` aparece en los blobs versionados; sin `.jpg/.heic`, sin certificados ni llaves (`.gitignore`).
- Datos personales: la auditoría SQL Server guarda hash, tipo, resultado, duración, estado y código de error; nunca CURP, nombre, domicilio ni imágenes.
- Público: sin cargas reales, sin acceso a bases locales, sin retención; el service worker no cachea `/api`.
- Local: token en fragmento de URL (`#acceso=`) que no viaja al servidor; comparación en tiempo constante.

## 7. Integraciones
| Integración | Estado |
|---|---|
| Oracle AI Database Free (Docker, 127.0.0.1:1521/FREEPDB1) | Real, verificada localmente |
| SQL Server 2025 LocalDB `(localdb)\ADEA_INE` | Real, verificada localmente |
| Vercel (producción) | Desplegado y verificado con muestras ficticias |
| Oracle/SQL Server desde Vercel | No existe por diseño (no se exponen bases locales) |

## 8. Pruebas ejecutadas y evidencias
- `pytest -q`: 81 exitosas, 6 omitidas (las de BD real) — local, Windows, Tesseract 5.4.
- `ADEA_REAL_DB=1 pytest tests/test_integration_real.py`: 6/6 contra Oracle y SQL Server locales.
- CI: `.github/workflows/ci.yml` (Ubuntu, Tesseract + verificación del motor RapidOCR) con reporte JUnit como artefacto.
- Producción tras el merge (commit 9f8939b, deployment adea-ine-control-m9pg70s6r): lote de 4 muestras ⇒ frente `ine/listo` (9.4 s), contrato y foto `descartado`; el reverso queda `descartado` porque su MRZ sintético no se lee en Linux (ver §9).
- Vercel (primer despliegue): `GET /api/health` 200; `POST /api/process` con frente ficticio ⇒ `ine/listo`, contrato con CURP ⇒ `no_ine/descartado` (≈17 s para 2 imágenes); carga real ⇒ 403; `/api/pairing` ⇒ 404; manifiesto 200; service worker registrado; sin errores de consola; sin desplazamiento horizontal a 390 px.

## 9. Problemas conocidos
- Precisión real no medida; las regiones dependen de etiquetas legibles y del modelo de credencial.
- El MRZ sintético depende de la fuente del sistema: en Windows se reconoce (revisión); en Linux/CI/Vercel no se reconoce y el reverso ficticio queda descartado. La prueba correspondiente es XFAIL documentado fuera de Windows.
- RapidOCR omite espacios: se compensa en la extracción, pero puede afectar documentos con otras tipografías.
- El proyecto Vercel no está conectado a GitHub por Git Integration (la sesión no tuvo permiso para ese cambio de configuración); los despliegues se hicieron por CLI desde `main`. Para despliegues automáticos: Vercel → adea-ine-control → Settings → Git → conectar `lilpne25-ui/ADEA-Prueba-`.
- El primer despliegue por CLI de un proyecto nuevo quedó directamente en producción (comportamiento de Vercel para proyectos sin producción previa); se verificó antes de anunciarlo.

## 10. Decisiones técnicas
Clasificador de reglas (no hay datos autorizados para entrenar); preprocesamiento elegido por lectura medida; correcciones OCR como hipótesis; LocalDB y contenedor Oracle para no tocar instancias existentes ni requerir UAC; RapidOCR solo donde no hay Tesseract; sin frameworks de frontend.

## 11. Trabajo pendiente
Calibración por modelo de INE con documentos autorizados; prueba de cámara en teléfono físico; firma real del SP; medir precisión; persistencia en la nube con una base independiente si se requiere.
