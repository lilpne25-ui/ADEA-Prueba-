from app.pairing import link_sides, match_side
from app.samples import mrz_lines
from app import validation as v
from app.pipeline import SYNTH


def test_side_names():
    assert match_side("carpeta/EXP01_frente.jpg") == ("CARPETA/EXP01", "front")
    assert match_side("carpeta\\EXP01_reverso.jpg") == ("CARPETA/EXP01", "back")
    assert match_side("carpeta/imagen_sin_par.jpg") is None


def pair(**extra):
    front = {"archivo": "a_frente.png", "estado": "listo", "clasificacion": "ine", "alertas": [],
             "senales": {"fuertes": 2}, "mrz": {}, "codigos": [],
             "campos": {"curp": v.validate_curp(SYNTH["curp"]), "clave_elector": v.validate_elector(SYNTH["elector"]),
                        "apellido_paterno": v.field("DEMO", v.DETECTADO)}}
    back = {"archivo": "a_reverso.png", "estado": "descartado", "clasificacion": "no_ine", "evidencias": [],
            "alertas": [], "senales": {"fuertes": 0}, "campos": {}, "codigos": [{"tipo": "QR Code", "valor": "X"}],
            "mrz": v.parse_mrz(mrz_lines())}
    front.update(extra.get("front", {}))
    back.update(extra.get("back", {}))
    return front, back


def test_name_pairing_is_tentative_and_not_complete():
    front, back = pair()
    link_sides([front, back])
    assert front["vinculacion"]["estado"] == "tentativa" and front["vinculacion"]["origen"] == "nombre_de_archivo"
    assert back["estado"] == "revision"
    assert front["expediente"]["estado"] == "pendiente_de_revision"


def test_explicit_group_and_confirmation_completes():
    front, back = pair(front={"archivo": "x.png", "grupo": "g1", "cara": "front", "confirmada": True},
                       back={"archivo": "y.png", "grupo": "g1", "cara": "back", "confirmada": True})
    link_sides([front, back])
    assert front["vinculacion"]["origen"] == "explicita" and front["vinculacion"]["estado"] == "confirmada"
    assert front["expediente"]["estado"] == "completo"


def test_no_pairing_by_order_only():
    front, back = pair(front={"archivo": "uno.png"}, back={"archivo": "dos.png"})
    link_sides([front, back])
    assert "vinculacion" not in front and "vinculacion" not in back


def test_inconsistent_sides_block_ready_state():
    front, back = pair()
    front["campos"]["curp"] = v.validate_curp(SYNTH["curp"].replace("991231", "980101"))
    link_sides([front, back])
    assert front["estado"] == "revision" and any("Inconsistencia" in a for a in front["alertas"])
