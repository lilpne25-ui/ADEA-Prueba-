@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title INE Control - Prueba tecnica Python
echo.
echo ==============================================
echo   INE Control / Prueba tecnica Python (V2.0)
echo ==============================================
echo.

rem ---- 1. Python -------------------------------------------------------
set "PYCMD="
py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD ( py -3 --version >nul 2>&1 && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD (
  echo [ERROR] No se encontro Python 3.12 o superior.
  echo         Instalalo desde https://www.python.org/downloads/ y marca "Add Python to PATH".
  pause
  exit /b 1
)
echo [OK] Python: %PYCMD%

rem ---- 2. Tesseract ----------------------------------------------------
set "TESSERACT_CMD="
where tesseract >nul 2>&1 && for /f "delims=" %%i in ('where tesseract') do if not defined TESSERACT_CMD set "TESSERACT_CMD=%%i"
if not defined TESSERACT_CMD if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESSERACT_CMD=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESSERACT_CMD if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "TESSERACT_CMD=%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe"
if not defined TESSERACT_CMD (
  echo [ERROR] No se encontro Tesseract OCR.
  echo         Instala con:  winget install UB-Mannheim.TesseractOCR
  echo         o descarga:   https://github.com/UB-Mannheim/tesseract/wiki
  pause
  exit /b 1
)
echo [OK] Tesseract: %TESSERACT_CMD%
if not exist "tessdata\spa.traineddata" (
  echo [AVISO] Falta tessdata\spa.traineddata: se usara solo ingles para el OCR.
  echo         Descargalo de https://github.com/tesseract-ocr/tessdata_fast y copialo a la carpeta tessdata.
)

rem ---- 3. Evitar un segundo servidor en el puerto 8000 ----------------------
set "PORT=8000"
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [AVISO] El puerto %PORT% ya esta en uso: se asume que INE Control ya esta en ejecucion.
  echo         Abriendo el navegador en http://localhost:%PORT%
  start "" "http://localhost:%PORT%"
  pause
  exit /b 0
)

rem ---- 4. Entorno virtual y dependencias ---------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  %PYCMD% -m venv .venv
  if errorlevel 1 ( echo [ERROR] No se pudo crear el entorno virtual. & pause & exit /b 1 )
)
echo Verificando dependencias (la primera vez puede tardar unos minutos)...
".venv\Scripts\python.exe" -m pip install -q -r requirements-vision.txt
if errorlevel 1 ( echo [ERROR] Fallo la instalacion de dependencias. Revisa tu conexion. & pause & exit /b 1 )

rem ---- 4b. Bases locales de desarrollo (solo si existen credenciales en .env.local) ----
set "URLSUFFIX="
if exist ".env.local" (
  echo Modo con bases locales detectado: iniciando SQL Server LocalDB y Oracle...
  ".venv\Scripts\python.exe" -m pip install -q -r requirements-corporate.txt
  set "LOCALDB=%ProgramFiles%\Microsoft SQL Server\170\Tools\Binn\SqlLocalDB.exe"
  if exist "!LOCALDB!" ( "!LOCALDB!" start ADEA_INE >nul 2>&1 && echo [OK] SQL Server LocalDB ADEA_INE iniciado ) else ( echo [AVISO] No se encontro SqlLocalDB.exe )
  docker start adea-oracle-free >nul 2>&1 && echo [OK] Contenedor Oracle iniciado ^(puede tardar 1-2 min en aceptar conexiones^) || echo [AVISO] Docker Desktop no esta abierto: Oracle aparecera Desconectado.
  for /f "tokens=1,* delims==" %%a in ('findstr /B "APP_ACCESS_TOKEN=" ".env.local"') do set "URLSUFFIX=/#acceso=%%b"
)

rem ---- 5. Iniciar -------------------------------------------------------------
echo.
echo Servidor local:   http://localhost:%PORT%
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
  set "IP=%%a"
  set "IP=!IP: =!"
  echo Desde el celular: http://!IP!:%PORT%   (misma red Wi-Fi confiable)
)
echo Para detener: cierra esta ventana o pulsa Ctrl+C.
echo NUNCA expongas este puerto a Internet con documentos reales.
echo.
start "" "http://localhost:%PORT%%URLSUFFIX%"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
pause
