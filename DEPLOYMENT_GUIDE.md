# Guía de despliegue

## 1. Local en Windows (verificado en la máquina de desarrollo)
`INICIAR_WINDOWS.bat` (ver README). Acceso desde el teléfono: misma Wi‑Fi, `http://IP-PC:8000`. El tráfico LAN es HTTP sin cifrar: úsalo solo en red confiable y permite el firewall únicamente en red **privada**. Para detener: cerrar la ventana.

## 1b. Bases locales de desarrollo (V3.0, instaladas y verificadas en la PC de desarrollo)
| Base | Implementación | Acceso |
|---|---|---|
| SQL Server | Instancia **LocalDB `ADEA_INE`** (SQL Server 2025 LocalDB, ya instalado), base `ADEA_INE_DEV`, login `adea_ine_app` con INSERT/SELECT solo sobre `dbo.IneAuditLog` | Solo local (canalización con nombre); no toca las instancias MSSQLSERVER, MSSQLSERVER01 ni TEW_SQLEXPRESS existentes |
| Oracle | **Oracle AI Database Free** con la imagen oficial `container-registry.oracle.com/database/free:latest-lite` en Docker Desktop, contenedor `adea-oracle-free`, volumen `adea-oracle-data`, PDB `FREEPDB1`. Esquema `ADEA_INE_OWNER` (tabla + `SP_REGISTRAR_EXPEDIENTE`), usuario de app `ADEA_INE_APP` con CREATE SESSION + EXECUTE del SP + SELECT de la tabla | Puerto publicado solo en `127.0.0.1:1521` |

Reproducir desde cero (idempotente, no borra datos):
```powershell
& "C:\Program Files\Microsoft SQL Server\170\Tools\Binn\SqlLocalDB.exe" create ADEA_INE -s
.venv\Scripts\python.exe -m pip install -r requirements-corporate.txt
.venv\Scripts\python.exe scripts\setup_sqlserver_localdb.py
docker pull container-registry.oracle.com/database/free:latest-lite
.venv\Scripts\python.exe scripts\setup_oracle_docker.py
```
Las contraseñas se generan al azar y se guardan **solo** en `.env.local` (ACL restringida al usuario de Windows, en `.gitignore`, excluido del ZIP). `INICIAR_WINDOWS.bat` arranca LocalDB y el contenedor y abre la app con el token en el fragmento de la URL (`#acceso=…`, que no viaja al servidor). Pruebas reales: `set ADEA_REAL_DB=1` y `pytest tests\test_integration_real.py`.

Por qué no SQL Server Developer ni el instalador Windows de Oracle: SQL Server 2025/2022, ODBC 18 y SSMS 22 ya estaban instalados; LocalDB da un motor real aislado sin tocar otras instancias ni requerir UAC. Oracle por contenedor oficial evita UAC, queda aislado y se elimina sin dejar rastros en el sistema. SQL Developer (GUI) no se instaló: se puede conectar a `127.0.0.1:1521/FREEPDB1` si se desea.

## 2. Red privada / corporativo
Detrás de un reverse proxy con TLS y autenticación (VPN/Zero Trust). Variables: `APP_MODE=corporate`, `APP_ACCESS_TOKEN`, `ORACLE_USER/PASSWORD/DSN`, `SQLSERVER_CONNECTION_STRING`, opcional `ORACLE_SP_NAME`, `ORACLE_SP_PARAMS`, `AUDIT_OUTBOX_DIR`. `pip install -r requirements-corporate.txt` y Microsoft ODBC Driver 18. Ejecutar `sql/*.sql` **solo** en entornos de prueba autorizados. Tras configurar, usar «Probar conexiones reales» (Arquitectura) o `POST /api/persistence/test`. Pendiente: credenciales, firma real del SP, política de conservación.

## 3. Docker (preparado, NO verificado en esta entrega)
```bash
docker build -t ine-control .
docker run --rm -p 8000:8000 ine-control
```
La imagen instala Tesseract (`spa`), OpenCV y ZXing; arranca en `APP_MODE=demo`.

## 4. Vercel (demo pública) — ESTADO: PENDIENTE
Modalidad pública: **solo muestras ficticias** (`VERCEL=1` ⇒ `ENABLE_REAL_UPLOADS=false`, sin bases de datos, sin credenciales, sin retención). Las pruebas `test_cloud_blocks_real_uploads` verifican el bloqueo.

Hallazgos de la documentación oficial de Vercel consultada: Python se ejecuta como Vercel Function (FastAPI soportado sin Dockerfile, 3.12 por defecto, bundle máx. 500 MB). Ese runtime **no permite instalar el binario de Tesseract** con `apt-get`; por eso el OCR funcional en Vercel requeriría un runtime de contenedor (el `Dockerfile.vercel`/`vercel.json` incluidos son un **intento preparado y NO validado**: no se encontró confirmación documental de su disponibilidad/limites). Alternativas: (a) contenedor en otro proveedor para el motor y Vercel solo para la UI, (b) vendorizar un binario estático de Tesseract dentro del bundle.

No se desplegó nada: la conexión de Vercel no está autorizada en esta sesión y publicar requiere cuenta/proyecto del usuario. Para continuar se necesita: autorización del conector Vercel, confirmar equipo/proyecto **nuevo** (no sobrescribir ninguno existente) y aprobar costos. Se haría primero un **Preview Deployment**, se verificaría `/api/health`, la muestra ficticia y el `403` de cargas reales, y solo después se solicitaría promoción.

## 5. Privacidad al desplegar
Nunca incluir fotografías reales ni `.env` en el repositorio (`.gitignore` lo evita; `test_security` lo comprueba).
