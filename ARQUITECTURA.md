# Arquitectura

```
Navegador (PC / móvil)                 Servidor FastAPI (app/main.py)
 ┌────────────────────┐   JSON/base64   ┌─────────────────────────────────────────────┐
 │ public/ HTML·CSS·JS │ ──────────────▶ │ validación de entrada · límites · token     │
 │ (solo presentación) │ ◀────────────── │            │                                 │
 └────────────────────┘                  │            ▼                                 │
                                         │ imaging ─▶ ocr ─▶ extraction ─▶ validation   │
                                         │  (OpenCV)  (Tesseract)  (regiones)  (reglas) │
                                         │            │                │                │
                                         │      classification   pairing (frente/rev.)  │
                                         │            ▼                                 │
                                         │        persistence  ──▶ Oracle (SP)          │
                                         │                     └─▶ SQL Server (audit)   │
                                         └─────────────────────────────────────────────┘
```

## Flujo por imagen
carga segura → rasgos visuales → localización de tarjeta (Canny/contornos/perspectiva) → 4 variantes de preprocesamiento → OCR + confianza → elección por puntuación medida → (giro solo si falta vocabulario) → MRZ + QR/PDF417 → extracción → validación → clasificación → asociación de caras → persistencia/auditoría.

## Comunicación y errores
- UI ↔ API: JSON sobre HTTP; la UI no decide nada de negocio.
- Fallo por archivo ⇒ elemento `estado:"error"`; el lote continúa. Tesseract ausente ⇒ `503` explícito.
- Persistencia aislada tras funciones inyectables (`oracle_factory`, `sqlserver_factory`): el OCR no conoce las bases de datos.
- Oracle OK + auditoría caída ⇒ `registrado_sin_auditoria` + bandeja local reenviable.

## Decisiones
| Decisión | Motivo |
|---|---|
| Clasificador híbrido por reglas | No existe banco autorizado para entrenar; evita afirmar un modelo inexistente |
| Elegir preprocesamiento por lectura medida | Evita filtros indiscriminados; evidencia visible en la UI |
| Correcciones OCR → `PENDIENTE_CONFIRMACION` | Una hipótesis no se vuelve dato confirmado |
| Asociación de caras tentativa | Evita unir por orden de carpeta; exige confirmación humana |
| Auditoría sin PII | Minimiza exposición; hash permite trazabilidad |
| HTML/CSS/JS sin framework | Sin lógica de negocio en la UI; menos dependencias; carga rápida |
| Modo público solo con muestras | Protege datos personales en demos |
