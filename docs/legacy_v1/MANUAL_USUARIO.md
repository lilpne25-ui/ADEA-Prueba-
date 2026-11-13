# Manual de usuario — ADEA INE Control

**Versión:** 1.0 · **Fecha:** 13/11/2026 · **Propósito:** prueba técnica de desarrollador Python.

## 1. Qué resuelve

Una institución recibe una carpeta con INE, identificaciones ajenas, contratos, fotos y otros documentos. El proceso diferencia las credenciales, busca mejorar su legibilidad, extrae datos y determina si debe registrar o enviar a revisión. El estado de cada imagen queda visible y, cuando se configura modo corporativo, se emiten eventos de auditoría.

## 2. Primeros pasos

1. Ejecutar el servidor local, según `README.md`.
2. Abrir `http://localhost:8000` en el navegador.
3. Verificar la esquina superior derecha: **Motor Python operativo**.
4. Seleccionar **Explorar muestra ficticia** para ejecutar una prueba sin información personal.
5. Entrar a **Laboratorio** para elegir hasta 8 imágenes. En un teléfono, el selector del navegador podrá permitir tomar fotos.
6. Seleccionar **Ejecutar procesamiento** y esperar resultados.

## 3. Interpretación de resultados

| Estado | Qué significa | Acción |
| --- | --- | --- |
| Listo | Se reconocieron evidencias de INE/IFE y **ambos** campos de identificación pasaron su regex. | Comprobar el contenido visualmente; en corporativo se intenta registrar en Oracle. |
| Revisión | Existe evidencia de credencial, pero faltan validaciones o la clasificación es ambigua. | Revisar fotografía y transcribir/confirmar manualmente. |
| Descartado | No se encontraron evidencias suficientes de INE/IFE. | En corporativo, generar auditoría SQL Server. |
| Error | Imagen corrupta, demasiado grande o motor OCR no disponible. | Usar fotografía legible de otra resolución y comprobar Tesseract. |

El resultado incluye comparativa visual, información por región y causas de la decisión. `No detectado` significa que **no hay evidencia suficiente**; no se inventa un dato.

## 4. Cómo fotografiar el documento

- Colocar sobre superficie plana, con luz suave y sin destellos ni sombras grandes.
- Evitar cortar esquinas; fotografiar en horizontal y de frente.
- Si se requiere MRZ y código 2D, tomar también una foto clara del **reverso**. Para asociar imágenes, nombrar `expediente01_frente.jpg` y `expediente01_reverso.jpg`. La vinculación es **tentativa por nombre**, no certifica identidad ni sustituye comparación humana.
- Comprimir fotografías demasiado grandes; el navegador hace una reducción previa hasta 1600 píxeles. Para análisis exhaustivo, emplear el batch de línea de comandos.

## 5. Acceso desde teléfono

1. Conectar PC y teléfono a la misma red Wi‑Fi privada.
2. En la PC, ejecutar `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
3. Ejecutar `ipconfig` (Windows) o `hostname -I` (Linux) para consultar la IP local.
4. Abrir `http://IP_LOCAL:8000` en el navegador móvil.
5. Si el firewall pregunta, autorizar solo la red privada.

**Privacidad:** la imagen se envía a la PC que aloja el backend. Una red HTTP local **no cifra** la transmisión; utilizar una red de confianza. Para un sistema real, activar HTTPS y autenticación robusta.

## 6. Limitaciones conocidas

- Sin fotos reales autorizadas, no hay exactitud medida ni garantía de lectura de todos los diseños de INE.
- La clasificación es heurística, no un modelo entrenado; se requiere revisión humana.
- El formato estructurado de domicilios puede ser ambiguo. Se conserva el texto OCR aunque algunas subpartes queden vacías.
- QR/PDF417 exigen el paquete `zxing-cpp`; la interfaz muestra si está activo.
- Oracle/SQL Server reales no funcionan hasta suministrar credenciales y aprobar el esquema de ejemplo.
