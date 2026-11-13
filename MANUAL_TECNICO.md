# Manual técnico

## A. Descripción
**Problema** (PDF del examen): procesar en lote imágenes heterogéneas, separar autónomamente las credenciales INE, limpiarlas visualmente, extraer datos y persistirlos en Oracle y SQL Server.
**Alcance**: pipeline Python, API FastAPI, UI web responsive, adaptadores de persistencia, pruebas, empaquetado.
**Restricciones**: sin banco de INE reales autorizado (precisión real **no medida**); firma real de `SP_REGISTRAR_EXPEDIENTE` desconocida; sin credenciales Oracle/SQL Server; sin servicios cloud de OCR.

## B. Módulos (`app/`)
| Módulo | Responsabilidad |
|---|---|
| `config.py` | Límites, ubicación de Tesseract/tessdata, idioma, política de cargas reales |
| `imaging.py` | Carga segura, localización de tarjeta (Canny+contornos), perspectiva, variantes de preprocesamiento, rasgos visuales |
| `ocr.py` | Envoltorio de Tesseract (TSV → texto + confianza media medida) |
| `extraction.py` | Extracción explicable por etiquetas/líneas, corrección contextual de caracteres (registrada), MRZ, perfiles de región configurables (`REGION_PROFILES`) |
| `validation.py` | Estados de campo, CURP (regex+fecha+entidad+dígito verificador), clave de elector, MRZ TD1 (ICAO 9303), validación cruzada |
| `classification.py` | Clasificador híbrido por reglas con señales fuertes/estructurales/negativas |
| `pipeline.py` | Orquestación (`Processor`, OCR inyectable) y muestra sintética |
| `pairing.py` | Asociación frente/reverso explícita o por nombre, siempre tentativa hasta confirmar |
| `persistence.py` | Oracle + SQL Server + bandeja de auditoría; estados honestos |
| `samples.py` | Muestras 100 % sintéticas (frente, reverso con MRZ/QR/PDF417, contrato con CURP, foto ruidosa) |
| `main.py` | API, cabeceras de seguridad, autenticación por token |
| `batch.py` | CLI por carpeta (sin PII por defecto) |

La UI (`public/`) no contiene lógica empresarial: solo presenta lo que devuelve la API y escapa todo valor dinámico (`esc()`).

## C. Procesamiento
1. **Carga**: PNG/JPG/WEBP/BMP/TIFF, ≤4 MB, ≤14 MP, EXIF aplicado.
2. **Localización**: Canny (3 umbrales) → contornos → casco convexo → cuadrilátero con proporción 1.35–1.85 y ≥20 % del área → `warpPerspective`. Si no hay candidato (o es el marco completo) → `tarjeta_localizada=false` y se trabaja con la imagen completa. Nunca se simula un warp.
3. **Preprocesamiento comparado**: `original`, `gris_contraste` (CLAHE), `denoise_contraste` (NLM+CLAHE), `binarizacion_adaptativa`. Cada una se lee con Tesseract; **puntuación = confianza media × min(palabras,60)/60**. Se elige la mejor y se reporta toda la tabla.
4. **Orientación**: solo si la mejor lectura tiene <2 términos de vocabulario de credencial se prueban 180/90/270°, adoptando un giro que haga aparecer ≥2 términos.
5. **Extracción**: los identificadores se buscan en las 4 lecturas (consenso); candidatos exactos > corregidos. Correcciones posicionales (O→0, I→1, S→5…) se registran en `correcciones_ocr`/`lectura_original` y el campo queda `PENDIENTE_CONFIRMACION`. La posición 17 de la CURP admite letra o dígito: solo se adopta una variante si cuadra con el dígito verificador y la regla de siglo (dígito si nació <2000).
6. **MRZ**: banda inferior 40 %, alfabeto restringido `A-Z0-9<`, dos preprocesamientos; se elige el de más dígitos verificadores coincidentes. Ajuste posicional de rellenos `<` (registrado como hipótesis).
7. **Códigos**: ZXing-cpp (QR y PDF417), imagen y versión ampliada ×2.
8. **Clasificación** (`classification.py`): `ine` si ≥1 señal fuerte (emisor INE/IFE, leyenda «CREDENCIAL PARA VOTAR», MRZ con emisor MEX, código que referencia ine.mx) y ≥2 estructurales (≥3 etiquetas electorales, clave/CURP con formato, MRZ con verificadores, código decodificado, contorno ID-1, bloque de foto) y sin leyendas de documento ajeno. Evidencia parcial → `revision`. Documentos con CURP pero sin señales → `no_ine`.
   *Alternativas evaluadas*: A heurísticas de texto; B rasgos visuales; C clasificador entrenado (descartado: no hay banco autorizado, no se afirma que exista un modelo); **D híbrida (implementada)**.
9. **Estado final**: `listo` solo si `ine` + CURP y clave `VALIDADO_POR_FORMATO` + ninguna consistencia en `False`. Si no, `revision`/`descartado`.

**Puntuaciones**: solo se exponen magnitudes medibles (confianza Tesseract, palabras, conteo de señales). No hay porcentajes inventados.

## D. Persistencia
- **Oracle** (`oracle_register`): `callproc(SP_REGISTRAR_EXPEDIENTE, 17 parámetros)` en una transacción (commit/rollback). Contrato **de demostración** en `sql/oracle_demo.sql`; nombre (`ORACLE_SP_NAME`) y orden/selección de parámetros (`ORACLE_SP_PARAMS`) configurables por entorno para adaptar la firma real. Duplicados: hash ya visto en la sesión o ORA-00001 ⇒ `duplicado`.
- **SQL Server** (`sqlserver_audit`): INSERT parametrizado (7 `?`) en `dbo.IneAuditLog` (`sql/sqlserver_audit.sql`): ProcessingId, SHA-256, tipo, resultado, duración, estado de persistencia, código de error, fecha UTC. **Sin CURP, nombre, domicilio ni imágenes.** Se audita todo: aceptados, revisión, descartes y errores de procesamiento.
- **Consistencia Oracle/SQL Server**: si Oracle confirma y la auditoría falla ⇒ `registrado_sin_auditoria`; el registro de auditoría (sin PII) se encola en `AUDIT_OUTBOX_DIR/audit_outbox.jsonl` y `replay_outbox()` lo reenvía. Si Oracle falla, se audita `error_oracle`. No hay transacción distribuida: es consistencia eventual documentada.
- **Estados mostrados**: `NO_CONFIGURADO`, `CONFIGURADO_SIN_PROBAR`, `CONECTADO_Y_VALIDADO` (solo tras `POST /api/persistence/test`, que ejecuta un `SELECT` real), `FALLO_DE_CONEXION`. En demo, siempre `NO_CONFIGURADO`.
- Credenciales solo por variables de entorno; los errores devuelven el tipo de excepción, nunca la cadena de conexión.

## E. API
| Método y ruta | Descripción |
|---|---|
| `GET /api/health` | Motores (Tesseract, OpenCV, ZXing), modo, estado Oracle/SQL Server |
| `GET /api/samples` · `GET /api/sample` | Muestras ficticias en base64 (generadas en memoria) |
| `POST /api/process` | `{archivos:[{archivo, imagen(base64/dataURI), grupo?, cara?(front/back)}], solo_muestra?}` → `{total, conteo, resultados[]}` |
| `POST /api/link` | Confirma asociación: `{resultados, confirmar:[archivos]}` |
| `POST /api/persistence/test` | Prueba real de conexión (requiere `X-Access-Token`) |
| `GET /api/docs` | Swagger |

Errores: `400` JSON inválido · `401` token · `403` carga real deshabilitada / muestra no permitida · `413` >4.3 MB · `422` lote vacío o >8 · `503` Tesseract ausente o modo corporativo sin token. Errores por archivo (corrupto, no imagen, >14 MP) devuelven `200` con `estado:"error"` en ese elemento.

Ejemplo:
```bash
curl -s localhost:8000/api/process -H "Content-Type: application/json" \
  -d '{"archivos":[{"archivo":"INE_FICTICIA_FRENTE.png"}],"solo_muestra":true}'
```

## F. Instalación
Windows: Python 3.12+, `winget install UB-Mannheim.TesseractOCR`, `INICIAR_WINDOWS.bat`. Manual: `python -m venv .venv`, `pip install -r requirements-vision.txt`, `uvicorn app.main:app`. Modo corporativo: `pip install -r requirements-corporate.txt` + Microsoft ODBC Driver 18. Docker: `docker build -t ine-control . && docker run -p 8000:8000 ine-control` (**no verificado en esta entrega**). Variables: ver `.env.example`.

## G. Seguridad
Límites de tamaño/píxeles/lote; cabeceras CSP (`default-src 'self'`), `nosniff`, `no-store`, `X-Frame-Options`; comparación de token en tiempo constante; sin logs de PII (`print` solo en CLI con conteos); SQL parametrizado; escape HTML de todo valor OCR; `.gitignore` bloquea `.env`, imágenes JPG y `fotos_reales/`; el modo público rechaza cargas reales.

## H. Pruebas y limitaciones
Ver `TEST_REPORT.md`. Limitaciones principales: precisión sobre INE reales no medida; regiones de nombre/domicilio dependen de etiquetas legibles y de líneas separadas; `REGION_PROFILES` solo cubre una distribución genérica (calibración por modelo de credencial pendiente); OCR del MRZ (fuente OCR-B) frágil con fotos reales; los dígitos verificadores del MRZ pueden no coincidir por errores OCR.
