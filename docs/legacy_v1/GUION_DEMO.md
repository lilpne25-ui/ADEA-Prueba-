# Guion de demostración para la entrevista (90–120 segundos)

**Antes de empezar:** abrir el laboratorio en PC y tener a mano el teléfono en la misma Wi‑Fi. Evitar enseñar datos completos de una INE real en videollamada o pantalla compartida.

## Minuto 0:00–0:20 — El problema

> "La idea del ejercicio era procesar expedientes heterogéneos: no solamente hacer OCR, sino separar identificaciones, limpiarlas, extraer datos y garantizar trazabilidad para los descartes. Por eso lo resolví como un pequeño flujo de procesamiento documental, con una interfaz que también permite revisar la evidencia."

## Minuto 0:20–0:45 — Proceso real

1. Pulsar **Explorar muestra ficticia**.
2. Enseñar el resultado **Listo** y la comparativa **Original / Limpieza adaptativa**.
3. Señalar CURP/clave extraídas con validación de formato. No confundir esto con autenticidad.

> "El núcleo corre en Python con OpenCV, Tesseract y ZXing. Muestra qué encontró el motor, qué pudo validar y qué queda para revisión; no fabrica campos que el OCR no alcanzó a leer."

## Minuto 0:45–1:10 — Arquitectura y bases

1. Abrir **Arquitectura y alcance**.
2. Mostrar los cuatro bloques y el estado de conectores.

> "Separé el OCR del almacenamiento. Oracle se integra con un procedimiento almacenado `SP_REGISTRAR_EXPEDIENTE`; SQL Server conserva la auditoría, incluidos descartes. Sin credenciales corporativas corro en modo demo: no simulo una escritura exitosa ni toco bases de datos ajenas. Incluí contratos SQL de prueba para una integración controlada."

## Minuto 1:10–1:30 — Diferenciadores

> "Pensé también en la experiencia de operación: es responsive, admite fotografía desde teléfono en la red local, tiene manual de uso, documentación técnica y pruebas automatizadas. Además, los archivos reales no se admiten en la configuración pública de demostración para proteger datos personales."

**Cierre sugerido:** "Si tuviera acceso a una muestra representativa y a un entorno Oracle/SQL Server de pruebas, el siguiente paso sería medir precisión por tipo de INE, revisar casos ambiguos e integrar los contratos reales antes de producción."
