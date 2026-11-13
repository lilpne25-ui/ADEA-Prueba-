# Despliegue V5

## Público

Vercel ejecuta `index.py` como FastAPI con RapidOCR/ONNX. `VERCEL=1` bloquea cargas reales, emparejamiento y bases locales. Validar siempre:

1. `/api/health` informa `rapidocr=true` y `ocr_disponible=true`.
2. `/api/process-stream` entrega eventos NDJSON antes del resultado final.
3. Frente, reverso, contrato y ruido producen los cuatro estados esperados.
4. Una carga no incluida devuelve 403.
5. Manifiesto y service worker responden 200.

La Git Integration no estaba conectada al auditar V4; los despliegues anteriores fueron por CLI. V5 debe crear Preview desde la rama/PR y promoverse solo después de CI y E2E.

Preview V5 validado: `https://adea-ine-control-mw5dchvyh-vlux-s-projects.vercel.app` (`dpl_5fZfYzXPcefyj8cS19e82hDZ5w1P`). Se comprobaron salud OCR, streaming, los cuatro estados esperados y el rechazo 403 de cargas reales.

## Privado

Ejecutar `INICIAR_WINDOWS.bat`. Para móvil, usar HTTPS confiable mediante Tailscale Serve o proxy corporativo; un certificado autofirmado no garantiza cámara en iPhone. Variables y credenciales permanecen en `.env.local`.

## Recuperación LocalDB

`scripts/setup_sqlserver_localdb.py` es idempotente. Si la instancia falta pero existen `ADEA_INE_DEV.mdf` y `_log.ldf`, los adjunta y remapea el usuario, preservando datos.

## Rollback

La rama V5 no altera el esquema de producción. El rollback web consiste en volver al deployment V4; la base no requiere downgrade. No eliminar MDF/LDF ni contenedores para revertir frontend/OCR.
