# INE Control · Prueba técnica Python (V3.0)

**Novedades V3.0:** Oracle AI Database Free (contenedor oficial) y SQL Server LocalDB **instalados, configurados y probados con integración real** (6/6), pestaña **Infraestructura** (estado, última verificación, expedientes, eventos de auditoría, errores recientes), **cámara con encuadre ID-1** e indicador de luz/nitidez en vivo con procesamiento al capturar, y credenciales locales protegidas en `.env.local`. Ver `DEPLOYMENT_GUIDE.md §1b` y `TEST_REPORT.md`.

Mesa de control de expedientes de onboarding: recibe un lote heterogéneo de imágenes, separa las credenciales INE/IFE, mejora la imagen, extrae datos estructurados, los valida y deja preparado el registro en **Oracle** (`SP_REGISTRAR_EXPEDIENTE`) y la auditoría en **SQL Server**.

> Demostración técnica **independiente** elaborada para el examen de desarrollador Python. No es software oficial ni autorizado por ADEA. El logotipo se extrajo del PDF del examen.

## Qué hace (y qué no)

| Etapa | Implementación | Verificado con |
|---|---|---|
| Clasificación `ine / no_ine / revision / error` | Híbrida: texto (emisor, leyenda, etiquetas, MRZ, QR) + visual (contorno ID-1, bloque de foto). **No** es un modelo entrenado. Una CURP sola nunca basta. | Pruebas automáticas con documentos sintéticos |
| Visión | OpenCV: Canny → contornos → cuadrilátero → perspectiva; 4 estrategias de preprocesamiento comparadas por calidad de lectura medida; rotación solo si aparece vocabulario de credencial | Pruebas con imágenes degradadas |
| OCR | Tesseract local (`spa+eng`), confianza por palabra | Pruebas reales con Tesseract 5.4 |
| Extracción | CURP, clave de elector, nombre (3 partes), domicilio, datos electorales, MRZ (3 líneas), QR y PDF417 (ZXing) | Muestras sintéticas |
| Validación | Estados `DETECTADO / VALIDADO_POR_FORMATO / PENDIENTE_CONFIRMACION / NO_DETECTADO / INVALIDO`; fecha, entidad y dígito verificador de la CURP; dígitos verificadores MRZ; consistencia frente-reverso | Pruebas unitarias |
| Persistencia | Adaptadores Oracle (python-oracledb) y SQL Server (pyodbc) separados del OCR | **Solo con adaptadores simulados**; sin credenciales reales no se simula ningún INSERT |

**Nunca** se afirma autenticidad: un formato correcto solo significa coherencia sintáctica.

## Inicio rápido en Windows

1. Instala Python 3.12+ y Tesseract: `winget install UB-Mannheim.TesseractOCR`.
2. Descomprime el ZIP y haz doble clic en **`INICIAR_WINDOWS.bat`**. Crea el entorno, instala dependencias, detecta Tesseract, evita servidores duplicados y abre `http://localhost:8000`.
3. Pulsa **Lote de muestra ficticio → Ejecutar procesamiento**.
4. Teléfono (misma Wi‑Fi confiable): abre `http://IP-DE-TU-PC:8000` (el BAT imprime la IP). No abras el puerto a Internet.

Manual: `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
Español para el OCR: `tessdata\spa.traineddata` (incluido en esta versión) o define `OCR_LANG=eng`.

## Procesar una carpeta (batch)

```powershell
.venv\Scripts\python.exe -m app.batch --input .\imagenes --output .\resumen_demo.json
```
El JSON por defecto **no** contiene datos de identidad ni imágenes (`--include-pii` solo en entorno autorizado).

## Pruebas

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```
Resultados y límites en [TEST_REPORT.md](TEST_REPORT.md).

## Documentación

[MANUAL_USUARIO.md](MANUAL_USUARIO.md) · [MANUAL_TECNICO.md](MANUAL_TECNICO.md) · [ARQUITECTURA.md](ARQUITECTURA.md) · [TEST_REPORT.md](TEST_REPORT.md) · [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) · API Swagger en `/api/docs`.

## Privacidad

- No se incluyen fotografías ni datos personales reales; todo demo/prueba es sintético y lleva leyenda de invalidez.
- Las imágenes se procesan en memoria; no hay OCR en la nube ni envío a terceros.
- La versión pública (`VERCEL=1` o `ENABLE_REAL_UPLOADS=false`) solo acepta las muestras integradas.
- Credenciales solo por variables de entorno (`.env.example`).

## QUÉ FUNCIONA REALMENTE / QUÉ QUEDA PENDIENTE

Ver la sección final de [TEST_REPORT.md](TEST_REPORT.md).
