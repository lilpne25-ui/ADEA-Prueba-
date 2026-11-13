# Reporte de pruebas

## V3.0 — Integración REAL con bases locales (2026-11-13)
Comando: `set ADEA_REAL_DB=1 && pytest tests/test_integration_real.py -v` contra Oracle AI Database Free (contenedor oficial, `127.0.0.1:1521/FREEPDB1`) y SQL Server 2025 LocalDB (`(localdb)\ADEA_INE`). Resultado: **6/6 exitosas, 0 fallidas** (82 s).

| Prueba | Qué se verificó realmente |
|---|---|
| 0 Conexiones | `SELECT` real en ambas bases ⇒ `CONECTADO_Y_VALIDADO` |
| 1 INE ficticia → Oracle | Estado `listo`; `SP_REGISTRAR_EXPEDIENTE` insertó 1 fila (consultada por hash); auditoría `oracle_ok`; reenvío del mismo archivo ⇒ `duplicado` (ORA-00001) sin segunda fila |
| 2 Documento no INE → SQL Server | `descartado`; fila de auditoría `no_ine/descartado/no_aplica`; 0 filas en Oracle |
| 3 Lote heterogéneo (5) | Frente `listo`, contrato y foto `descartado`, archivo corrupto `error` auditado; todas las filas de auditoría presentes; duración por archivo > 0; 5 archivos en ≈31 s |
| 4 Fallo controlado | Oracle en puerto cerrado ⇒ `error_oracle` informado y auditado; SQL Server inaccesible con Oracle OK ⇒ `registrado_sin_auditoria`, bandeja local y **reenvío real** a SQL Server |
| 5 Reinicio | Nueva instancia de la app (otro proceso/puerto) se reconecta: `/api/infra` muestra ambas conectadas con conteos |

Suite por defecto (sin bases reales): **78 exitosas, 6 omitidas (las de integración real), 0 fallidas**.
Cámara con encuadre: implementada (getUserMedia + marco ID-1 + indicador de luz/nitidez en vivo); **no probada con cámara física** en esta sesión. En el celular por HTTP de la LAN el navegador no permite getUserMedia y se usa la cámara nativa del sistema.

---
## V2.0

Entorno: Windows 11, Python 3.14.3, Tesseract 5.4.0 (`spa+eng`), OpenCV 4.14, zxing-cpp 3.1.1, FastAPI 0.162. Comando: `python -m pytest -q`.

| Métrica | Valor |
|---|---|
| TOTAL DE PRUEBAS | 78 |
| PRUEBAS EXITOSAS | 78 |
| PRUEBAS FALLIDAS | 0 |
| PRUEBAS BLOQUEADAS / OMITIDAS | 0 |
| Duración | ≈65 s |

## Por archivo y naturaleza
| Archivo | N.º | Naturaleza |
|---|---|---|
| `test_validation.py` | 11 | Unitarias reales (CURP, clave, MRZ, cruzadas) |
| `test_pipeline.py` | 20 | Extracción/clasificación reales sobre texto; 3 con **OCR simulado** (inyectado) |
| `test_pairing.py` | 5 | Unitarias reales |
| `test_ocr_real.py` | 14 | **Tesseract + OpenCV + ZXing reales** sobre imágenes sintéticas: texto claro, bajo contraste, ruido, 3 resoluciones, perspectiva, recorte parcial, giro 180°, negativos, imagen en blanco, reverso con QR/PDF417/MRZ, comparación de estrategias |
| `test_api.py` | 9 | API real (TestClient): muestra, lote mixto, entradas inválidas, archivos corruptos, límites de tamaño, token, bloqueo en nube |
| `test_persistence.py` | 14 | **SIMULADAS** (adaptadores falsos): éxito, conexión rechazada, duplicados, error de SP con rollback, fallo parcial Oracle/SQL Server con bandeja y reenvío, sin PII en auditoría, SQL parametrizado, errores de proceso auditados, firma del SP adaptable, no-configurado sin INSERT simulado |
| `test_security.py` | 5 | Sin secretos en repo, sin imágenes JPG/WEBP, `.gitignore`, escape de XSS en la UI (análisis estático), sin logs de PII |

Cobertura de los puntos de la misión: clasificación (INE ficticia, documento ajeno, foto, imagen vacía/corrupta, **CURP en documento no INE**), OCR (claro, bajo contraste, inclinada, ruido, recorte, resoluciones), extracción (CURP/clave válida e inválida, faltantes, nombres compuestos, domicilio multilínea, MRZ, QR, PDF417), API, bases de datos, seguridad.

## Verificación manual (no automatizada)
- Servidor y UI en el navegador integrado: lote de muestra procesado de extremo a extremo (1 LISTO, 1 REVISIÓN —el reverso, asociación tentativa—, 2 DESCARTADOS).
- Responsive **por emulación** (no dispositivo físico) a 390×844, 430×932, 768×1024 y 1440×900: sin desplazamiento horizontal (`scrollWidth ≤ ancho`).
- `INICIAR_WINDOWS.bat`: ejecutado desde una copia limpia (crea venv, instala, detecta Tesseract, abre navegador, `/api/health` OK) y rama de puerto ocupado (no duplica servidor).
- `python -m app.batch`: 4 imágenes; el JSON de salida no contiene datos de identidad.

## Limitaciones (no se oculta nada)
1. **Precisión real desconocida**: no hay banco de INE reales/autorizados; todas las pruebas usan imágenes sintéticas. No se midió exactitud en documentos reales.
2. El MRZ sintético se leyó con errores de OCR (ver `correcciones_ocr`); sus dígitos verificadores pueden no coincidir y entonces se reporta así (el reverso queda en REVISIÓN).
3. Oracle/SQL Server: **nunca se probó contra bases reales**; solo lógica con adaptadores simulados. `CONECTADO_Y_VALIDADO` requiere prueba real con credenciales.
4. La firma real de `SP_REGISTRAR_EXPEDIENTE` se desconoce; se usa un contrato de demostración configurable.
5. Perfiles de región solo genéricos; modelos de INE con otra distribución pueden requerir calibración.
6. Pruebas en teléfono físico (Android/iPhone, cámara) **no realizadas**.
7. Docker y Vercel no ejecutados.

# QUÉ FUNCIONA REALMENTE (verificado con evidencia arriba)
- Servidor FastAPI, UI de escritorio/móvil (emulada), muestra sintética y lote mixto de extremo a extremo.
- Clasificación híbrida con descarte de documentos ajenos (incluida una CURP en un contrato) sobre muestras sintéticas.
- Localización de tarjeta + corrección de perspectiva real con OpenCV; comparación de estrategias; rotación 180°.
- Tesseract extrae campos; regex del examen; validación CURP/clave/MRZ; estados honestos; correcciones OCR registradas.
- Lectura de QR y PDF417 (ZXing) en muestra generada.
- Asociación frente/reverso tentativa con confirmación humana.
- Lógica de persistencia/auditoría (simulada) y ausencia de escrituras sin configuración.
- `INICIAR_WINDOWS.bat` y CLI batch.

# QUÉ QUEDA PENDIENTE
- Probar con **INE reales autorizadas** (lo hará el usuario localmente) y medir precisión.
- Calibrar regiones por modelo de credencial.
- Integración real Oracle/SQL Server (credenciales, firma del SP, política de conservación).
- Prueba en dispositivo físico, Docker, y **despliegue Vercel Preview** (requiere autorización del conector y confirmar proyecto; el runtime Python de Vercel no instala Tesseract, ver `DEPLOYMENT_GUIDE.md`).
- Versiones PDF de los manuales (no generadas).
