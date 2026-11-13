# Reporte de pruebas V5

## V6 (rama `feature/adea-v6-ocr-calibration`, 2026-11-13)

- Suite local completa: **99 aprobadas, 6 omitidas** (las 6 requieren `ADEA_REAL_DB=1`).
- Integración real con `ADEA_REAL_DB=1`: **6/6** contra Oracle AI Database Free y SQL Server LocalDB. Antes de esta corrida el usuario de LocalDB estaba huérfano (su SID no coincidía con el login), y se revinculó con `ALTER USER … WITH LOGIN` sin borrar registros.
- Benchmark sintético `scripts/evaluate_v5.py`: clasificación 100 %, CURP 100 %, clave 100 %, 0 falsos positivos y 0 falsos negativos (sin regresión). El tiempo medio pasó de 3.8 s a ≈5.0 s por la segunda lectura condicional.
- Nuevas pruebas: separación de frente y reverso en una sola foto (con espacio y con contacto), no división de documentos individuales ni del contrato, localización por color sobre fondo saturado, fusión de motores que rellena sin sobrescribir y limpieza de renglones de nombre.
- La prueba XSS se actualizó: el marcado ya no llega a los campos de nombre porque estos solo aceptan palabras en mayúsculas, y se sigue comprobando que el texto libre del domicilio se conserva como cadena inerte.
- Evaluación con fotografías reales: ver `V5_OCR_EVALUATION.md` § V6 (métricas agregadas, sin datos personales).
- Cámara física: sigue pendiente; solo hay emulación.


Fecha: 2026-11-13. Rama: `feature/adea-v5-rescue`.

## Resultados

- Suite local: 93 pruebas aprobadas, 6 omitidas sin `ADEA_REAL_DB=1`.
- Integración real: 6/6 contra Oracle y SQL Server.
- Benchmark: 8/8 casos reservados correctamente agrupados.
- Navegador: Chrome limpio a 390, 430, 768, 1024 y 1440 px.
- Consola durante lote completo: 0 errores, 0 advertencias.
- PWA: manifiesto/worker, caché V5 y exclusión `/api/` verificadas por pruebas.

## Casos de aceptación

| Caso | Estado | Evidencia |
|---|---|---|
| Frente ficticio | Aprobado | INE/listo, OCR real, campos y confianza |
| Reverso ficticio | Aprobado local | MRZ TD1, QR y PDF417; revisión, no autenticidad |
| Pasaporte ficticio | Aprobado | `no_ine` |
| Contrato con CURP | Aprobado | `no_ine/descartado` |
| Imagen ilegible | Aprobado | `imagen_insuficiente/repetir` |
| Lote heterogéneo | Aprobado | avance real por archivo, resultado consistente |
| Producción V4 limpia | Reproducido | OCR real, pero sin streaming; MRZ en revisión |
| V5 Preview | Aprobado | 38 eventos NDJSON, 32 etapas y cuatro estados esperados |
| V5 Production | Aprobado | RapidOCR operativo; 38 eventos, 32 etapas y recorrido móvil limpio |
| Cámara física | Pendiente | emulación no sustituye iPhone/Android real |

## Bases reales

Oracle `FREEPDB1`: conectado; SP de 17 argumentos verificado; commit, duplicado y rollback cubiertos. SQL LocalDB fue recuperado adjuntando los MDF/LDF existentes, sin borrarlos; auditoría e integración aprobadas.

## Limitaciones

No hay exactitud medida con INE reales. La instalación PWA y cámara requieren dispositivo físico. Los rangos de dependencias y advertencias deprecadas existentes deben vigilarse, pero no bloquearon el recorrido principal.

Preview verificado: `https://adea-ine-control-mw5dchvyh-vlux-s-projects.vercel.app`. El bundle de servidor quedó en 347.04 MB; Vercel aplicó optimización, pero el tamaño debe seguirse como riesgo operativo.

Producción verificada: `https://adea-ine-control.vercel.app` (`dpl_6ZiFGyNfNiDcs2Kb8GicSF3eafUN`). Salud, lote ficticio completo, bloqueo 403 y consola móvil sin errores aprobados después de integrar la PR #2.
