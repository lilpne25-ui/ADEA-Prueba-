# Sistema de diseño V5

## Direcciones evaluadas

1. **Precision Workbench — seleccionada:** estación de visión documental, cola y proceso lado a lado, progreso técnico visible.
2. **Quiet Confidence:** una acción dominante y detalles bajo demanda; excelente móvil, menos eficiente para lotes.
3. **Vision Ops Darkroom:** muy distintiva, pero de mayor fatiga y menor afinidad administrativa.

V5 combina Precision Workbench en escritorio con divulgación progresiva de Quiet Confidence.

## Principios

- Acción principal inmediata: `Escanear INE` aparece antes de la carga en ≤800 px.
- Un estado por archivo y mensajes provenientes del backend.
- Resultado operativo primero; imagen, estrategias y persistencia en `Ver detalles técnicos`.
- Azul ADEA como referencia, sin presentarse como producto oficial.
- Blanco para trabajo documental, panel azul profundo para el motor de visión.
- Objetivos táctiles ≥44 px, foco visible y respeto a movimiento reducido.

## Componentes

- Workbench de carga/lote.
- Panel oscuro de etapas reales.
- Escáner modal ID-1 con brillo, nitidez, vista previa, repetir y confirmar.
- Banners `listo`, `revisión`, `repetir`, `descartado`, `error` con texto además de color.
- Campos con valor, estado, confianza y evidencia.
- Navegación de pestañas con `aria-controls`, paneles y teclado de flechas.

## Evidencia visual

- `docs/screenshots/v5/mobile-390.png`
- `docs/screenshots/v5/mobile-430.png`
- `docs/screenshots/v5/streaming-1440.png`
- `docs/screenshots/v5/results-1440.png`

No se afirma cumplimiento WCAG completo: faltan lector de pantalla y pruebas físicas de zoom/teclado móvil.
