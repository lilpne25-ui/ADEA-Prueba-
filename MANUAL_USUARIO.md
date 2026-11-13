# Manual de usuario

## ¿Qué es?
Una mesa de control que lee fotografías de documentos, encuentra las credenciales INE/IFE, mejora la imagen y extrae sus datos. Es una prueba técnica independiente (no oficial de ADEA).

## Pasos
1. **Abrir** `INICIAR_WINDOWS.bat` (o `http://IP-DE-LA-PC:8000` desde el teléfono).
2. **Laboratorio → elegir imágenes**: arrastra, «Seleccionar archivos» o «Tomar fotografía» (móvil). Para probar sin documentos: **Lote de muestra ficticio**.
3. Si subes frente y reverso, indica en cada fila el **Expediente** y la **Cara**. La aplicación nunca une archivos solo por el orden.
4. **Ejecutar procesamiento**. Verás: Carga → Procesamiento → Resultado → Trazabilidad.
5. En **Resultados** revisa cada archivo.

## Qué significa cada resultado
| Resultado | Significado |
|---|---|
| LISTO | Parece INE y CURP y clave cumplen formato y no se contradicen entre sí ni con el reverso. **No prueba autenticidad.** |
| REVISIÓN | Evidencia parcial, campos pendientes o inconsistencias: una persona debe revisar. |
| DESCARTADO | Sin evidencia suficiente de INE/IFE (contratos, fotos, licencias, etc.). |
| ERROR | Archivo corrupto, no imagen, demasiado grande (>4 MB o >14 MP). |

## Estado de cada campo
- **Detectado**: leído por OCR, sin regla de formato (nombre, domicilio).
- **Validado por formato**: cumple la regla (CURP, clave); no es autenticidad.
- **Pendiente de confirmación**: hipótesis (corrección de caracteres OCR, dígito verificador discordante o inconsistencia). Se muestra la lectura original.
- **No detectado**: no hay evidencia; no se inventa nada.
- **Inválido**: se leyó algo que no cumple el formato.

## Imagen original vs. procesada
Se muestran ambas, la estrategia elegida y una tabla comparativa (confianza OCR, palabras, puntuación). Si no se localizó la tarjeta o no se corrigió la perspectiva, se dice explícitamente.

## Asociar frente y reverso
Las asociaciones nacen **tentativas**. Pulsa «Confirmar que ambas caras son del mismo documento» tras compararlas visualmente. Solo entonces el expediente puede quedar «completo».

## Si hay un error
Foto nítida, buena luz, sin reflejos, documento completo y sobre fondo contrastante; archivo <4 MB. Si dice que Tesseract no está instalado: `winget install UB-Mannheim.TesseractOCR`.

## Auditoría y modo demostración
En **demo** no se escribe en ninguna base de datos (la pantalla lo indica: ORACLE / SQL SERVER «NO CONFIGURADO»). En **corporativo** cada archivo deja un registro sin datos personales en SQL Server y los expedientes «Listo» van a Oracle. «CONECTADO Y VALIDADO» solo aparece tras una prueba real de conexión.

## Privacidad
Usa INE reales solo en tu equipo/red local confiable y cierra el servidor al terminar. Nunca en una demo pública.
