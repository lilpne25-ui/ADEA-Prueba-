# Entrega ADEA — INE Control v1.0

Fecha de corte: **13 de noviembre de 2026**.

## Verificado

- 17 pruebas automatizadas aprobadas (`unittest`).
- Ejecución real de Tesseract sobre la INE ficticia: `clasificacion=ine`, `estado=listo`, detección de CURP y clave de elector sintéticas.
- OpenCV presente: la muestra ejecuta corrección de perspectiva y binarización adaptativa.
- ZXing presente: lectura de un código QR generado para prueba, con cadena recuperada íntegramente.
- API FastAPI: inicio, estado, muestra ficticia y procesamiento en lote.
- La configuración de nube bloquea cargas reales (HTTP 403), pero permite la muestra sintética.
- Sintaxis JavaScript comprobada mediante `node --check`.

## Falta validar antes de producción

- Precisión, recall y cobertura por versión de INE en un banco autorizado de imágenes reales.
- Decodificación de PDF417 real y los distintos esquemas MRZ de INE.
- Drivers y conectividad reales Oracle / SQL Server; firma empresarial del SP desconocida.
- Transacciones compensatorias y reintentos entre bases heterogéneas.
- Auditoría de seguridad, accesos, cifrado end-to-end, retención legal y autorización empresarial.
- Visualización responsive en navegadores móviles reales: implementación responsive lista, prueba de dispositivo físico pendiente.
- Despliegue efectivo en Vercel: configuración incluida, aún sin build publicado.

**Este proyecto es una demostración técnica**, no un servicio de verificación de identidad oficial ni una plataforma KYC certificada.
