"""Pruebas unitarias del motor de validación (sin OCR)."""

from app import validation as v
from app.samples import mrz_lines
from app.pipeline import SYNTH


def test_curp_valid_with_check_digit():
    r = v.validate_curp(SYNTH["curp"])
    assert r["estado"] == v.VALIDADO and not r["alertas"]


def test_curp_regex_ok_but_check_digit_wrong_is_pending_not_validated():
    bad = SYNTH["curp"][:17] + str((int(SYNTH["curp"][17]) + 1) % 10)
    r = v.validate_curp(bad)
    assert r["estado"] == v.PENDIENTE
    assert any("verificador" in a for a in r["alertas"])


def test_curp_invalid_format():
    assert v.validate_curp("PUDA991231MMCBNN")["estado"] == v.INVALIDO


def test_curp_impossible_date_and_state():
    r = v.validate_curp("PUDA991331MXXBNN03")
    assert r["estado"] == v.PENDIENTE
    assert any("fecha" in a for a in r["alertas"]) and any("entidad" in a for a in r["alertas"])


def test_curp_missing():
    assert v.validate_curp(None)["estado"] == v.NO_DETECTADO


def test_elector_valid_invalid_and_state_range():
    assert v.validate_elector(SYNTH["elector"])["estado"] == v.VALIDADO
    assert v.validate_elector("PRDEAN00120101X123")["estado"] == v.INVALIDO
    assert v.validate_elector("PRDEAN99123145M678")["estado"] == v.PENDIENTE  # entidad 45 fuera de rango


def test_ocr_correction_is_logged_and_never_confirmed():
    r = v.validate_curp(SYNTH["curp"], raw="PUDA99I231MMCBNN03", corrections=["pos 7: 'I'→'1'"])
    assert r["estado"] == v.PENDIENTE
    assert r["lectura_original"] == "PUDA99I231MMCBNN03" and r["correcciones_ocr"]


def test_mrz_check_digits_and_parse():
    parsed = v.parse_mrz(mrz_lines())
    assert parsed["lineas_validas"] and parsed["emisor"] == "MEX"
    assert all(c["coincide"] for c in parsed["verificadores"])
    assert parsed["apellidos"] == "DEMO PRUEBA" and parsed["nombres"] == "ANA"


def test_mrz_wrong_digit_detected():
    l1, l2, l3 = mrz_lines()
    broken = [l1, l2[:6] + "0" + l2[7:], l3]
    parsed = v.parse_mrz(broken)
    assert not all(c["coincide"] for c in parsed["verificadores"])


def test_mrz_needs_three_lines():
    assert v.parse_mrz(["IDMEX"])["lineas_validas"] is False


def test_cross_checks_consistent_and_inconsistent():
    fields = {"curp": v.validate_curp(SYNTH["curp"]), "clave_elector": v.validate_elector(SYNTH["elector"]),
              "apellido_paterno": v.field("DEMO", v.DETECTADO)}
    ok = v.cross_checks(fields, v.parse_mrz(mrz_lines()))
    assert all(c["resultado"] is True for c in ok)
    other = dict(fields, clave_elector=v.validate_elector("PRDEAN98010115H678"))
    assert any(c["resultado"] is False for c in v.cross_checks(other, None))
