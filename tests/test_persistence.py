"""Persistencia con adaptadores SIMULADOS (no hay infraestructura Oracle/SQL Server real disponible).
Estas pruebas verifican la lógica de control, no la conectividad real; el reporte las marca como simuladas."""

import json
from pathlib import Path

import pytest

from app import persistence as p
from app import validation as v


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def callproc(self, name, args):
        if self.conn.fail_sp:
            raise self.conn.fail_sp
        self.conn.calls.append((name, args))

    def execute(self, sql, *params):
        if self.conn.fail_sql:
            raise self.conn.fail_sql
        self.conn.calls.append((sql, params))

    def fetchone(self):
        return (1,)


class FakeConn:
    def __init__(self, fail_sp=None, fail_sql=None):
        self.fail_sp, self.fail_sql, self.calls = fail_sp, fail_sql, []
        self.committed = self.rolled_back = self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def corporate(monkeypatch):
    monkeypatch.setenv("APP_MODE", "corporate")
    monkeypatch.setenv("ORACLE_USER", "u")
    monkeypatch.setenv("ORACLE_PASSWORD", "no-es-secreto-real")
    monkeypatch.setenv("ORACLE_DSN", "host/svc")
    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", "Driver=x;Server=y")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "t")


def result(estado="listo", sha="a" * 64):
    from app.pipeline import SYNTH
    names = ("curp", "clave_elector", "apellido_paterno", "apellido_materno", "nombres", "estado_electoral",
             "seccion", "municipio_electoral", "localidad", "anio_registro", "emision", "vigencia")
    campos = {n: v.field("X", v.DETECTADO) for n in names}
    campos["curp"] = v.validate_curp(SYNTH["curp"])
    return {"estado": estado, "clasificacion": "ine", "sha256": sha, "duracion_ms": 5, "campos": campos,
            "domicilio_texto": "CALLE 1", "mrz": {"lineas": ["A", "B", "C"]}, "codigos": []}


def install(monkeypatch, oracle, sql):
    monkeypatch.setattr(p, "oracle_factory", lambda: oracle)
    monkeypatch.setattr(p, "sqlserver_factory", lambda: sql)


def test_demo_mode_never_writes_nor_claims_connection():
    out = p.persist(result())
    assert out["estado"] == "demo_sin_persistencia"
    assert p.backend_status() == {"oracle": p.NO_CONFIGURADO, "sqlserver": p.NO_CONFIGURADO}


def test_corporate_without_credentials_is_not_configured_and_does_not_simulate_insert(monkeypatch):
    monkeypatch.setenv("APP_MODE", "corporate")
    out = p.persist(result())
    assert out["estado"] == "no_configurado"


def test_status_connected_only_after_real_test(monkeypatch):
    corporate(monkeypatch)
    install(monkeypatch, FakeConn(), FakeConn())
    assert p.backend_status()["oracle"] == p.CONFIGURADO       # configurado ≠ conectado
    p.test_connections()
    assert p.backend_status() == {"oracle": p.CONECTADO, "sqlserver": p.CONECTADO}


def test_connection_refused_is_reported(monkeypatch):
    corporate(monkeypatch)

    def refuse():
        raise ConnectionRefusedError("secreto-no-debe-salir")
    monkeypatch.setattr(p, "oracle_factory", refuse)
    monkeypatch.setattr(p, "sqlserver_factory", lambda: FakeConn())
    res = p.test_connections()
    assert res["oracle"]["estado"] == p.FALLO and "secreto" not in json.dumps(res)


def test_successful_registration_and_audit_without_pii(monkeypatch):
    corporate(monkeypatch)
    ora, sql = FakeConn(), FakeConn()
    install(monkeypatch, ora, sql)
    out = p.persist(result())
    assert out["estado"] == "registrado" and ora.committed and sql.committed
    assert ora.calls[0][0] == "SP_REGISTRAR_EXPEDIENTE" and len(ora.calls[0][1]) == 17
    sql_text, params = sql.calls[0]
    assert sql_text.count("?") == 7 and "CURP" not in sql_text.upper().replace("PROCESSINGID", "")
    assert all("PUDA" not in str(x) for x in params)  # sin CURP en la bitácora


def test_sql_injection_is_parametrized(monkeypatch):
    corporate(monkeypatch)
    ora, sql = FakeConn(), FakeConn()
    install(monkeypatch, ora, sql)
    evil = "x'); DROP TABLE dbo.IneAuditLog;--"
    r = result(estado="descartado", sha=evil)
    p.persist(r)
    sql_text, params = sql.calls[0]
    assert "DROP" not in sql_text and evil in params


def test_procedure_error_rolls_back_and_is_audited(monkeypatch):
    corporate(monkeypatch)
    ora, sql = FakeConn(fail_sp=RuntimeError("ORA-06550")), FakeConn()
    install(monkeypatch, ora, sql)
    out = p.persist(result())
    assert out["estado"] == "error_oracle" and ora.rolled_back and not ora.committed
    assert sql.calls and sql.calls[0][1][5] == "error_oracle"


def test_duplicate_detected_by_oracle_and_by_hash(monkeypatch):
    corporate(monkeypatch)
    ora, sql = FakeConn(fail_sp=RuntimeError("ORA-00001: unique constraint")), FakeConn()
    install(monkeypatch, ora, sql)
    assert p.persist(result())["estado"] == "duplicado"
    ora2 = FakeConn()
    install(monkeypatch, ora2, sql)
    assert p.persist(result())["estado"] == "duplicado" and not ora2.calls  # no reintenta el mismo hash


def test_only_ready_documents_go_to_oracle_but_everything_is_audited(monkeypatch):
    corporate(monkeypatch)
    ora, sql = FakeConn(), FakeConn()
    install(monkeypatch, ora, sql)
    out = p.persist(result(estado="descartado"))
    assert not ora.calls and sql.calls and out["sqlserver"] == "auditado"


def test_processing_errors_are_audited_but_never_sent_to_oracle(monkeypatch):
    corporate(monkeypatch)
    ora, sql = FakeConn(), FakeConn()
    install(monkeypatch, ora, sql)
    out = p.persist({"archivo": "x.png", "estado": "error", "clasificacion": "error", "mensaje": "corrupto"})
    assert not ora.calls and out["sqlserver"] == "auditado"
    assert sql.calls[0][1][2] == "error" and sql.calls[0][1][3] == "error"


def test_partial_failure_oracle_ok_audit_fails_goes_to_outbox_and_replays(monkeypatch, tmp_path):
    corporate(monkeypatch)
    ora, sql = FakeConn(), FakeConn(fail_sql=TimeoutError("timeout"))
    install(monkeypatch, ora, sql)
    out = p.persist(result())
    assert out["estado"] == "registrado_sin_auditoria" and out["sqlserver"] == "fallo_auditoria"
    outbox = Path(tmp_path / "outbox" / "audit_outbox.jsonl")
    assert outbox.exists() and "PUDA" not in outbox.read_text()
    healthy = FakeConn()
    monkeypatch.setattr(p, "sqlserver_factory", lambda: healthy)
    assert p.replay_outbox() == {"reenviados": 1, "pendientes": 0} and healthy.calls


def test_oracle_connection_failure_is_controlled(monkeypatch):
    corporate(monkeypatch)

    def down():
        raise TimeoutError("sin ruta")
    monkeypatch.setattr(p, "oracle_factory", down)
    monkeypatch.setattr(p, "sqlserver_factory", lambda: FakeConn())
    assert p.persist(result())["estado"] == "error_oracle"


def test_sp_signature_is_adaptable_by_env(monkeypatch):
    corporate(monkeypatch)
    monkeypatch.setenv("ORACLE_SP_PARAMS", "curp,sha256")
    ora = FakeConn()
    install(monkeypatch, ora, FakeConn())
    p.persist(result())
    assert len(ora.calls[0][1]) == 2


def test_invalid_mode_rejected(monkeypatch):
    monkeypatch.setenv("APP_MODE", "produccion")
    with pytest.raises(RuntimeError):
        p.mode()
