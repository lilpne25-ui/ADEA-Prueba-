"""Lógica de extracción, clasificación y pipeline con OCR simulado (marcadas como SIMULADAS en el reporte)."""

import pytest
from PIL import Image, ImageOps

from app import extraction, classification, validation as v
from app.imaging import InvalidImage, adaptive_binarize, load
from app.pipeline import CURP_RE, ELECTOR_RE, SYNTH, Processor, decode_codes, synthetic_ine
from app.persistence import persist
from app.samples import mrz_lines, synthetic_back

TEXT = f"""INSTITUTO NACIONAL ELECTORAL
CREDENCIAL PARA VOTAR
NOMBRE
DE LA CRUZ
MARTINEZ
MARIA DEL CARMEN
DOMICILIO
C ROBLE 123 INT 4
COL ALAMOS 03400
BENITO JUAREZ, CDMX.
CURP {SYNTH['curp']}
CLAVE DE ELECTOR {SYNTH['elector']}
ESTADO 15 SECCION 1234 MUNICIPIO 001 LOCALIDAD 0001
AÑO DE REGISTRO 2020 EMISION 2021 VIGENCIA 2031
"""


def info(text=TEXT, mrz=None):
    return extraction.extract([text], mrz, [])


def test_regex_from_exam():
    assert CURP_RE.fullmatch(SYNTH["curp"]) and not CURP_RE.fullmatch(SYNTH["curp"][:-1])
    assert ELECTOR_RE.fullmatch(SYNTH["elector"]) and not ELECTOR_RE.fullmatch("PRDEAN00120101X123")


def test_compound_names_split_by_lines():
    c = info()["campos"]
    assert (c["apellido_paterno"]["valor"], c["apellido_materno"]["valor"], c["nombres"]["valor"]) == \
           ("DE LA CRUZ", "MARTINEZ", "MARIA DEL CARMEN")


def test_multiline_address():
    c = info()["campos"]
    assert c["calle"]["valor"] == "C ROBLE" and c["numero_exterior"]["valor"] == "123"
    assert c["numero_interior"]["valor"] == "4" and c["colonia"]["valor"] == "ALAMOS"
    assert c["codigo_postal"]["valor"] == "03400"
    assert c["municipio_domicilio"]["valor"] == "BENITO JUAREZ" and c["estado_domicilio"]["valor"] == "CDMX"


def test_electoral_data():
    c = info()["campos"]
    assert (c["seccion"]["valor"], c["anio_registro"]["valor"], c["emision"]["valor"], c["vigencia"]["valor"]) == \
           ("1234", "2020", "2021", "2031")


def test_missing_fields_are_not_invented():
    c = info("INSTITUTO NACIONAL ELECTORAL\nCREDENCIAL PARA VOTAR")["campos"]
    assert all(f["estado"] == v.NO_DETECTADO and f["valor"] is None for f in c.values())


def test_single_name_line_is_not_split():
    c = info("NOMBRE\nJUAN PEREZ LOPEZ\nDOMICILIO\nX")["campos"]
    assert c["apellido_paterno"]["valor"] is None and c["apellido_paterno"]["estado"] == v.PENDIENTE


def test_ocr_confusion_corrected_but_pending():
    garbled = TEXT.replace(SYNTH["elector"], SYNTH["elector"][:6] + "9912311S" + SYNTH["elector"][14:])
    # 'S' en posición numérica ⇒ corrección contextual S→5, que debe registrarse y quedar PENDIENTE.
    c = info(garbled)["campos"]["clave_elector"]
    assert c["valor"] == SYNTH["elector"]
    assert c["estado"] == v.PENDIENTE and c["lectura_original"] != c["valor"] and c["correcciones_ocr"]


def test_xss_payload_stays_inert_text():
    c = info("NOMBRE\n<SCRIPT>ALERT(1)</SCRIPT>\nAB\nCD\nDOMICILIO\nZZ")["campos"]
    assert "<SCRIPT>" in c["apellido_paterno"]["valor"]  # el backend no ejecuta; la UI escapa (ver test_security)


def test_mrz_normalization_trims_and_logs():
    l1, l2, l3 = mrz_lines()
    notes = []
    lines = extraction.normalize_mrz_lines("\n".join(["T" + l1, l2, l3]), notes)
    assert lines[0].startswith("IDMEX") and len(lines) == 3


def test_no_false_mrz_from_electoral_labels():
    assert extraction.normalize_mrz_lines("REGISTRO 2020 EMISION 2021 VIGENCIA 2031\nESTADO 15 SECCION 1234") == []


def visual(**kw):
    return {"relacion_aspecto": 1.58, "imagen_vacia": False, **kw}


def test_classification_ine():
    cat, ev, _ = classification.classify(TEXT, info(), visual(), True)
    assert cat == classification.INE and ev


def test_curp_alone_is_not_ine():
    text = f"CONTRATO DE SERVICIOS\nEl cliente declara su CURP {SYNTH['curp']}"
    cat, _, _ = classification.classify(text, info(text), visual(), False)
    assert cat == classification.NO_INE


def test_curp_and_elector_without_issuer_goes_to_review_or_discard_never_ine():
    text = f"CURP {SYNTH['curp']}\nCLAVE DE ELECTOR {SYNTH['elector']}"
    cat, _, _ = classification.classify(text, info(text), visual(relacion_aspecto=0.7), False)
    assert cat != classification.INE


def test_empty_image_discarded():
    cat, _, _ = classification.classify("", info(""), {"imagen_vacia": True}, False)
    assert cat == classification.NO_INE


def test_binarization_and_invalid_file():
    im = load(synthetic_ine())
    clean = adaptive_binarize(im)
    assert clean.size == im.size and clean.mode == "L"
    for bad in (b"", b"no soy imagen", b"\x89PNG\r\n\x1a\ncorrupto"):
        with pytest.raises(InvalidImage):
            load(bad)


def test_oversized_file_rejected():
    with pytest.raises(InvalidImage):
        load(b"0" * (4 * 1024 * 1024 + 1))


def test_barcodes_from_generated_back():
    codes = decode_codes(Image.open(__import__("io").BytesIO(synthetic_back())).convert("RGB"))
    kinds = {c["tipo"] for c in codes}
    if not kinds:
        pytest.skip("zxing-cpp no instalado")
    assert "QR Code" in kinds and "PDF417" in kinds


def test_pipeline_with_simulated_ocr_ready():
    worker = Processor(ocr_fn=lambda image, **kw: TEXT)
    r = worker.process(synthetic_ine(), "muestra.png")
    assert r["clasificacion"] == "ine"
    assert r["campos"]["curp"]["estado"] == v.VALIDADO
    assert r["preview_limpieza"].startswith("data:image/jpeg;base64,")
    assert r["tecnicas"]["estrategias_comparadas"]


def test_pipeline_with_simulated_ocr_non_ine():
    r = Processor(ocr_fn=lambda image, **kw: "CONTRATO DE COMPRAVENTA").process(synthetic_ine(), "c.png")
    assert r["estado"] == "descartado" and r["ocr"] == ""


def test_demo_never_writes():
    assert persist({"estado": "listo"})["estado"] == "demo_sin_persistencia"
