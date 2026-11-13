# Despliegue local, móvil y Vercel

## A. Entrega funcional recomendada: demo local

En un PC Windows con Tesseract y Python, iniciar `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Una vez escuchando, abrir `http://localhost:8000` y desde el celular `http://IP_PC:8000` en la misma Wi‑Fi privada. Esta modalidad permite fotografiar un documento propio sin pasar por infraestructura pública; **el tráfico HTTP en LAN no está cifrado**.

## B. Contenedor Docker

```bash
docker build -t adea-ine-control .
docker run --rm -p 8000:8000 -e APP_MODE=demo -e OCR_LANG=spa+eng adea-ine-control
```

El Dockerfile instala Tesseract con idioma español, OpenCV y ZXing. Comprobar `/api/health` para ver el motor disponible.

## C. Demo en Vercel (preparada, no publicada)

Vercel admite contenedores con `Dockerfile.vercel` usando su runtime Container. El proyecto incluye `vercel.json` para solicitar ese runtime, con Python, OpenCV, ZXing y Tesseract en una imagen. Su disponibilidad debe comprobarse en la cuenta del desarrollador (Container runtime en beta en noviembre de 2026).

1. Crear un repositorio **privado** para esta prueba, sin fotos de INE ni `.env`.
2. Importar repositorio a Vercel, seleccionar framework `Container` y comprobar que detecte `Dockerfile.vercel`.
3. Configurar `APP_MODE=demo`, `ENABLE_REAL_UPLOADS=false`, `OCR_LANG=spa+eng`.
4. Desplegar una **URL de vista previa** (no producción corporativa) y comprobar `/api/health`.
5. Ejecutar exclusivamente la muestra ficticia integrada. Validar que la carga de imágenes reales responde `403`.

**No desplegado automáticamente:** requiere cuenta y vinculación de repositorio; publicar una demo accesible públicamente con posibilidad de subir INE reales presenta riesgos de privacidad.

La petición JSON tiene límite de 4.3 MB para quedar debajo del máximo de carga que Vercel documenta para Functions (4.5 MB). Un banco grande se procesa mejor como trabajo asíncrono con almacenamiento temporal cifrado y eliminación segura; esta solución técnica incluye procesamiento batch local, no un sistema de colas público.

## D. Integración corporativa (pendiente de requisitos de ADEA)

- Solicitar host/puerto Oracle, credenciales de prueba, firma real del SP y política de conservación.
- Solicitar instancia SQL Server y autorización para ejecutar `sql/sqlserver_audit.sql` en un entorno de evaluación aislado.
- Instalar `requirements-corporate.txt` y Microsoft ODBC Driver 18 para SQL Server.
- Crear token para `APP_ACCESS_TOKEN` y configurar firewall, TLS y acceso por VPN/Zero Trust.
- Establecer `APP_MODE=corporate`, verificar pruebas de lectura/escritura y procedimientos de recuperación.

**Nunca ejecutar SQL de demostración en bases de producción.**
