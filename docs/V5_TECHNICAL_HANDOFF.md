# Entrega técnica V5

## Qué cambió

- Clasificación conservadora para TD1/pasaporte y estado de captura insuficiente.
- MRZ sin destrucción de datos opcionales.
- Calidad visual ampliada y confianza/cajas por campo.
- Progreso NDJSON real por archivo/etapa.
- Escáner con vista previa, repetir y confirmar.
- Workbench responsive, navegación accesible y detalles técnicos progresivos.
- PWA V5 y salud OCR semánticamente correcta.
- Recuperación segura de LocalDB y outbox atómica dentro del proceso.
- Benchmark reproducible y documentación coherente.

## Verificación rápida

```powershell
.venv\Scripts\python.exe -m pytest -q
$env:ADEA_REAL_DB='1'; .venv\Scripts\python.exe -m pytest -q tests\test_integration_real.py
.venv\Scripts\python.exe scripts\evaluate_v5.py
node --check public\app.js
```

## Estado de entrega

- Código y pruebas locales: listo.
- Oracle/SQL Server: verificados.
- Preview Vercel y E2E: aprobados.
- CI/PR/Production: pendientes de integración controlada.
- Cámara/PWA física: pendiente del usuario; no debe marcarse aprobada por emulación.
- Precisión real: pendiente de dataset autorizado local.

## Privacidad

No se añadieron INE reales, secretos, respuestas OCR privadas ni archivos de base. Las capturas versionadas muestran solo muestras ficticias.
