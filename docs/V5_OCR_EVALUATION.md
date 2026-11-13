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
