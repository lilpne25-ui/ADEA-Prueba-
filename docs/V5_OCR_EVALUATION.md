# Evaluación OCR V5

## Arquitectura seleccionada

- **Local/privado:** Tesseract 5 (`spa+eng`). Es ligero, auditable y compatible con Windows; requiere binario del sistema.
- **Vercel:** RapidOCR con modelos PP-OCRv3 ONNX vendorizados. Evita binarios del sistema y GPU; el costo es mayor latencia y menor control de whitelist/PSM.
- **Visión/códigos:** OpenCV para documento/calidad/preprocesamiento y ZXing-cpp para QR/PDF417.

PaddleOCR puede mejorar detección multilingüe, pero aumenta sustancialmente dependencias, memoria, arranque y riesgo del bundle serverless. Sin un corpus real autorizado no hay evidencia para justificar el cambio.

## Correcciones verificadas

1. TD1 mexicano genérico ya no se acepta como INE.
2. Pasaporte con MRZ se descarta por evidencia negativa.
3. Datos opcionales MRZ se preservan.
4. RapidOCR y Tesseract conservan cajas/confianza por token.
5. Selección de variante considera señales documentales.
6. Se miden brillo, contraste, nitidez Laplaciana, reflejo y resolución.
7. La localización acepta tarjetas pequeñas/verticales y bordes parcialmente fragmentados.
8. La extracción combina recorte corregido con lecturas de contexto de la imagen completa.
9. Nombres y domicilio usan consenso entre preprocesamientos; un identificador válido prevalece sobre una lectura frecuente inválida.
10. La MRZ se localiza por sus tres renglones y prueba orientación con verificadores, sin depender de una banda fija.

## Benchmark reproducible

Comando: `.venv\Scripts\python.exe scripts\evaluate_v5.py`

Dataset: 10 casos ficticios, 2 de ajuste y 8 reservados para evaluación. Variaciones: rotación 180°, desenfoque, compresión JPEG, bajo contraste, reverso, contrato con CURP, pasaporte MRZ, ruido e imagen blanca.

Resultados locales con Tesseract, 2026-11-13:

| Métrica | Resultado |
|---|---:|
| Exactitud de clasificación, evaluación | 8/8 (1.00) |
| Recall INE/posible INE | 4/4 (1.00) |
| Falsos positivos INE | 0 |
| Falsos negativos INE | 0 |
| Exactitud CURP en frentes evaluados | 3/3 |
| Exactitud clave en frentes evaluados | 3/3 |
| Tiempo promedio | 3.811 s/caso |

Matriz: `ine→ine 4`, `no_ine→no_ine 2`, `insuficiente→insuficiente 2`.

## Interpretación honesta

Estos resultados demuestran regresión y robustez sobre datos sintéticos. Adicionalmente se realizó una calibración privada local con cuatro fotografías autorizadas; ninguna imagen, valor personal, ruta o salida OCR se incorporó al repositorio.

## Calibración privada agregada

Resultados sobre la misma fotografía frontal de mejor calidad, antes/después:

| Medición | V5 inicial | V5 calibrada |
|---|---:|---:|
| Campos inequívocos correctos | 6/14 (42.9 %) | 14/14 (100 %) |
| Fotografía frontal secundaria | 2/14 (14.3 %) | 8/14 (57.1 %) |
| MRZ exacta en mejor reverso | 0/3 líneas | 3/3 líneas; 3/3 verificadores |
| QR decodificados en reverso alterno | 3 | 3 |
| Tiempo Tesseract, mejor frente | 3.4 s | 4.8 s |
| Tiempo Tesseract, mejor reverso | 6.3 s | 5.8 s |

Dos campos quedaron fuera de la puntuación por requerir confirmación humana y uno no aplica al modelo fotografiado. La toma posterior con reflejo central produce tres líneas MRZ estructurales, pero cero verificadores; no se usa como verdad. ZXing identificó códigos QR, no PDF417. RapidOCR obtuvo 8/14 campos frontales y mayor latencia (6.2–10.1 s), por lo que Tesseract continúa como motor local principal.

La suite completa posterior quedó en 93 aprobadas y 6 omitidas sin bases reales. La precisión sobre otros modelos sigue requiriendo un conjunto privado más amplio y etiquetado de forma independiente.


## V6 — Continuación de la calibración (Claude Code, 2026-11-13)

### Metodología (privada, reproducible localmente)
- Conjunto autorizado por el usuario: **7 fotografías** locales (no versionadas). Contienen **5 anversos** y **5 reversos** de **4 credenciales distintas**: 2 fotos del frente y 2 del reverso de la credencial del usuario, y 3 capturas de terceros con frente y reverso en la misma imagen. Ninguna imagen, valor ni salida OCR se incorporó al repositorio.
- Verdad de referencia transcrita a mano y **verificada con los propios validadores**: las 4 CURP cumplen dígito verificador y las 5 MRZ cumplen sus 3 dígitos verificadores ICAO.
- 14 campos por anverso (CURP, clave, paterno, materno, nombres, calle, número exterior, colonia, CP, municipio, estado, sección, año de registro, vigencia). **Un campo correcto pero en `PENDIENTE_CONFIRMACION` no cuenta como correcto.**
- Las tres versiones se ejecutaron con el mismo arnés sobre las mismas fotos (`git worktree` de `cb42bc3` y `51c2143`). El arnés vive fuera del repositorio porque contiene la verdad de referencia.

### Resultados agregados (Tesseract como motor principal)

| Versión | Campos anverso correctos (70) | Correctos solo con revisión | Incorrectos | No detectados | MRZ líneas exactas (15) | Verificadores MRZ (15) | Tiempo total 7 fotos |
|---|---:|---:|---:|---:|---:|---:|---:|
| V5 inicial (`cb42bc3`) | 8 (11.4 %) | 0 | 4 | 58 | 5 | 6 | 40 s |
| V5 calibrada por Codex (`51c2143`) | 23 (32.9 %) | 3 | 15 | 29 | 8 | 9 | 50 s |
| **V6** | **46 (65.7 %)** | 0 | 19 | 5 | **10** | **12** | 89 s |

Por fotografía (V6): mejor anverso **14/14** confirmado (Codex: 13 + 1 pendiente con este arnés); segundo anverso del usuario **9/14** (Codex: 7/14); anversos de terceros 7, 9 y 7 de 14 (Codex: 0–3). El reverso con reflejo central sigue en 0/3: no hay MRZ legible y debe repetirse la captura.

Con este arnés el mejor anverso de Codex da 13/14 y no 14/14, porque su CURP queda pendiente de confirmación y aquí eso no cuenta como correcto. La cifra 8/14 de Codex para el segundo anverso equivale aquí a 7/14 (otra definición de campo).

### Comparación de motores (mismo arnés)

| Motor | Campos correctos | MRZ exactas | Tiempo 7 fotos | Observación |
|---|---:|---:|---:|---|
| Tesseract solo (V5 Codex) | 23/70 | 8/15 | 50 s | mejor en tomas nítidas |
| RapidOCR solo (V5 Codex) | 36/70 | 10/15 | 105 s | mejor en tomas pequeñas; omite espacios |
| RapidOCR solo (V6, lo que corre en Vercel) | 40/70 | 10/15 | 123 s | mejora por localización y separación |
| **Tesseract + RapidOCR por campo (V6 local)** | **46/70** | **10/15** | 89 s | se conserva Tesseract como motor principal |

Tesseract sigue siendo el motor local principal (14/14 en la mejor toma contra 9/14 de RapidOCR). RapidOCR solo se consulta cuando la lectura primaria deja campos sin leer o identificadores sin validar, y solo **rellena huecos**: nunca sobrescribe un valor de Tesseract. Si los dos motores discrepan, se agrega una alerta para revisión humana.

### Causas encontradas y correcciones (generales, no específicas de una foto)
1. **Localización (causa principal del segundo anverso).** Con la credencial sostenida en la mano, los dedos rompen los bordes y Canny no cierra el contorno; se leía la foto completa con texto de unos 10 px. Se agregó un respaldo por **segmentación de color**: la tarjeta es una región clara y poco saturada con proporción ID‑1.
2. **Varias tarjetas por foto.** Tres capturas traen frente y reverso juntos y antes se procesaban como una sola imagen. `card_regions` separa hasta dos credenciales usando contornos, diferencia contra el fondo o un corte por la franja de fondo cuando se tocan. Exige que ambas mitades sean superficies impresas, así que una hoja de contrato no se divide. Cada tarjeta se procesa aparte y se asocia como frente/reverso **tentativo**.
3. **Re‑localización destructiva.** Volver a buscar contornos dentro de una tarjeta ya enderezada encontraba la fotografía (≈200×130 px) y destruía el documento. Ahora se omite en los recortes ya separados.
4. **Interpretación del nombre.** El renglón de la etiqueta «NOMBRE» incluía «SEXO H/M», y a la derecha aparecían restos de la foto fantasma. Los renglones de nombre ahora solo aceptan palabras en MAYÚSCULAS de 2 o más letras, más partículas como DE, DEL o Y.
5. **Motor OCR.** Fusión campo a campo con RapidOCR en anversos y MRZ (con prueba de giro de 180°). La MRZ secundaria solo se adopta si mejora la estructura TD1 y los dígitos verificadores.
6. **Confirmación de la CURP.** Si RapidOCR lee exactamente la CURP que Tesseract obtuvo corrigiendo la posición 17 (O/0), la hipótesis queda confirmada por dos lecturas independientes.

Se descartó ampliar el reescalado: con 1600 px y 2000 px el resultado empeoró (38/70 y 30/70), porque amplifica los artefactos de compresión de WhatsApp.

### Lo que sigue fallando y por qué
- **Nombres (13 de 15 componentes sin acertar)** y **calle/número**: en las tomas pequeñas o comprimidas el error ya es de reconocimiento de caracteres, con una o dos letras cambiadas. No se corrigen por diccionario para no inventar datos; quedan visibles como «Detectado» para revisión humana.
- **19 valores incorrectos visibles.** Ninguno es CURP ni clave de elector en estado validado: los identificadores con formato y dígito verificador válidos coincidieron siempre con la referencia. Los incorrectos son texto libre (nombre y domicilio) y algunos datos electorales de terceros.
- **Reverso con reflejo:** no hay MRZ recuperable; el sistema lo informa y no inventa líneas.
- **Validez estadística:** son 4 credenciales del mismo modelo (diseño 2019+). No es una precisión general.
