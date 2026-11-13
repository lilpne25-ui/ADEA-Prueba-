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
| Tiempo promedio | 3.150 s/caso |

Matriz: `ine→ine 4`, `no_ine→no_ine 2`, `insuficiente→insuficiente 2`.

## Interpretación honesta

Estos resultados demuestran regresión y robustez sobre datos sintéticos, no precisión en credenciales reales. Para medirla, el usuario debe ejecutar localmente muestras autorizadas, mantener etiquetas fuera del repositorio y reportar por campo sin conservar imágenes.
