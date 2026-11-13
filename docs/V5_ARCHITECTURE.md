# Arquitectura V5

Fecha de verificación: 2026-11-13.

## Modos y frontera de seguridad

- **Demostración pública:** FastAPI en Vercel, RapidOCR/ONNX, OpenCV y ZXing; solo procesa las cuatro muestras ficticias integradas. No acepta identificaciones reales, no retiene imágenes y no accede a Oracle/SQL Server.
- **Operación privada:** servidor Python autorizado, Tesseract, cámara integrada, Oracle `FREEPDB1` y SQL Server LocalDB `(localdb)\ADEA_INE`. Requiere token y transporte HTTPS confiable.

## Flujo

`imagen → validación → detección ID-1 → perspectiva → calidad → variantes → OCR → campos/MRZ/códigos → validación → clasificación → asociación → Oracle/auditoría`

`Processor.process` emite eventos reales en cada transición. `POST /api/process-stream` los entrega como NDJSON; cada línea incluye tipo, archivo, índice, etapa y mensaje. El resultado final conserva el contrato JSON de `/api/process`.

## Decisiones V5

- MRZ TD1 con emisor MEX es evidencia estructural, no prueba de que el emisor sea INE.
- Los campos opcionales MRZ nunca se convierten a relleno para forzar una forma sintética.
- Cada campo expone valor, estado, confianza OCR y cajas de evidencia cuando el motor las entrega.
- La variante OCR se elige por confianza, vocabulario e identificadores recuperados.
- Imagen vacía, oscura, borrosa o pequeña queda `imagen_insuficiente/repetir`, no `no_ine`.
- NDJSON se eligió sobre SSE porque el lote requiere `POST` con cuerpo y sobre WebSocket porque no necesita canal bidireccional.
- La outbox SQL se protege en el proceso, hace `fsync` y reemplazo atómico al reproducir.

## Persistencia

Solo `estado=listo` invoca `SP_REGISTRAR_EXPEDIENTE`. Todo resultado genera auditoría sin PII. Oracle hace commit/rollback explícito; duplicados se controlan por constraint y hash. Un fallo de SQL tras Oracle deja `registrado_sin_auditoria` y encola un registro mínimo.

## Límites

No existe dataset autorizado de INE reales, entrenamiento supervisado ni afirmación de autenticidad. La prueba física de cámara/PWA en iPhone y Android permanece pendiente.
