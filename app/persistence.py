"""Persistencia: Oracle (SP_REGISTRAR_EXPEDIENTE) y auditoría SQL Server, separadas del OCR.

Reglas de honestidad:
- Sin credenciales NO se simula ningún INSERT: el estado es NO_CONFIGURADO.
- "CONECTADO_Y_VALIDADO" solo existe tras una prueba de conexión real (`test_connections`).
- La auditoría en SQL Server no contiene CURP, nombre, domicilio ni imágenes: solo hash, tipo, resultado.
- Oracle OK + auditoría fallida ⇒ `registrado_sin_auditoria`; el registro de auditoría (sin PII) se guarda
  en una bandeja local (`AUDIT_OUTBOX_DIR`) para reenviarse con `replay_outbox`.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

NO_CONFIGURADO = "NO_CONFIGURADO"
CONFIGURADO = "CONFIGURADO_SIN_PROBAR"
CONECTADO = "CONECTADO_Y_VALIDADO"
FALLO = "FALLO_DE_CONEXION"

# Contrato DE DEMOSTRACIÓN (la firma empresarial real se desconoce). Orden de parámetros configurable
# con ORACLE_SP_PARAMS (lista separada por comas) para adaptarlo sin tocar el código.
DEFAULT_SP_PARAMS = ["curp", "clave_elector", "apellido_paterno", "apellido_materno", "nombres",
                     "domicilio", "estado_electoral", "seccion", "municipio_electoral", "localidad",
                     "anio_registro", "emision", "vigencia", "mrz", "qr", "pdf417", "sha256"]

_last_test: dict[str, dict[str, Any]] = {}


def mode() -> str:
    value = os.getenv("APP_MODE", "demo").lower()
    if value not in ("demo", "corporate"):
        raise RuntimeError("APP_MODE debe ser demo o corporate")
    return value


def oracle_configured() -> bool:
    return bool(os.getenv("ORACLE_USER") and os.getenv("ORACLE_PASSWORD") and os.getenv("ORACLE_DSN"))


def sqlserver_configured() -> bool:
    return bool(os.getenv("SQLSERVER_CONNECTION_STRING"))


def configured() -> bool:
    return oracle_configured() and sqlserver_configured() and bool(os.getenv("APP_ACCESS_TOKEN"))


def backend_status() -> dict[str, str]:
    """Estado para la UI. Nunca afirma conexión sin prueba real previa."""
    out = {}
    for name, ok in (("oracle", oracle_configured()), ("sqlserver", sqlserver_configured())):
        if mode() == "demo" or not ok:
            out[name] = NO_CONFIGURADO
        elif _last_test.get(name, {}).get("ok"):
            out[name] = CONECTADO
        elif name in _last_test:
            out[name] = FALLO
        else:
            out[name] = CONFIGURADO
    return out


# ---- fábricas de conexión (inyectables en pruebas) --------------------------------------------
def _oracle_connect():
    import oracledb  # dependencia opcional (requirements-corporate.txt)
    return oracledb.connect(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"],
                            dsn=os.environ["ORACLE_DSN"], tcp_connect_timeout=8)


def _sqlserver_connect():
    import pyodbc  # dependencia opcional
    return pyodbc.connect(os.environ["SQLSERVER_CONNECTION_STRING"], timeout=8)


oracle_factory: Callable[[], Any] = _oracle_connect
sqlserver_factory: Callable[[], Any] = _sqlserver_connect


def test_connections() -> dict[str, dict[str, Any]]:
    """Prueba real de conectividad (SELECT trivial). Solo así se puede mostrar CONECTADO_Y_VALIDADO."""
    results: dict[str, dict[str, Any]] = {}
    checks = (("oracle", oracle_configured(), lambda: oracle_factory(), "SELECT 1 FROM DUAL"),
              ("sqlserver", sqlserver_configured(), lambda: sqlserver_factory(), "SELECT 1"))
    for name, ok, factory, query in checks:
        if mode() == "demo" or not ok:
            results[name] = {"ok": False, "estado": NO_CONFIGURADO}
            continue
        try:
            conn = factory()
            try:
                cur = conn.cursor()
                cur.execute(query)
                cur.fetchone()
            finally:
                conn.close()
            results[name] = {"ok": True, "estado": CONECTADO}
        except Exception as exc:  # noqa: BLE001 - no exponer cadena de conexión ni credenciales
            results[name] = {"ok": False, "estado": FALLO, "tipo_error": type(exc).__name__}
        results[name]["verificado_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _last_test[name] = results[name]
    return results


_recent_errors: list[dict[str, Any]] = []


def _note_error(component: str, code: str | None) -> None:
    """Errores operativos recientes en memoria (sin PII, sin mensajes con credenciales)."""
    _recent_errors.append({"componente": component, "codigo": code,
                           "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    del _recent_errors[:-10]


def infrastructure() -> dict[str, Any]:
    """Resumen administrativo: estados verificados ahora mismo, conteos y errores recientes (sin PII)."""
    test_connections()
    out: dict[str, Any] = {"modo": mode(), "oracle": dict(_last_test.get("oracle", {"estado": NO_CONFIGURADO})),
                           "sqlserver": dict(_last_test.get("sqlserver", {"estado": NO_CONFIGURADO})),
                           "errores_recientes_proceso": list(reversed(_recent_errors))}
    if out["oracle"].get("ok"):
        try:
            conn = oracle_factory()
            try:
                cur = conn.cursor()
                cur.execute(os.getenv("ORACLE_COUNT_QUERY",
                                      "SELECT COUNT(*), MAX(CREADO_EN) FROM INE_EXPEDIENTES_DEMO"))
                count, last = cur.fetchone()
                out["oracle"].update({"expedientes": int(count), "ultimo_registro": str(last) if last else None})
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            out["oracle"]["error_consulta"] = type(exc).__name__
    if out["sqlserver"].get("ok"):
        try:
            conn = sqlserver_factory()
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*), MAX(CreatedAtUtc) FROM dbo.IneAuditLog")
                count, last = cur.fetchone()
                cur.execute("SELECT TOP 5 CONVERT(varchar(36), ProcessingId), DocumentType, PersistenceState, "
                            "ErrorCode, CONVERT(varchar(23), CreatedAtUtc, 126) FROM dbo.IneAuditLog "
                            "WHERE ErrorCode IS NOT NULL ORDER BY Id DESC")
                errors = [{"processing_id": r[0], "tipo": r[1], "persistencia": r[2], "codigo": r[3], "utc": r[4]}
                          for r in cur.fetchall()]
                cur.execute("SELECT DocumentType, COUNT(*) FROM dbo.IneAuditLog GROUP BY DocumentType")
                by_type = {r[0]: int(r[1]) for r in cur.fetchall()}
                out["sqlserver"].update({"eventos_auditoria": int(count), "por_tipo": by_type,
                                         "ultimo_procesamiento": str(last) if last else None,
                                         "errores_recientes": errors})
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            out["sqlserver"]["error_consulta"] = type(exc).__name__
    return out


def _sp_args(result: dict[str, Any]) -> list[Any]:
    f = result["campos"]
    codes = result.get("codigos", [])
    values = {
        **{k: f[k]["valor"] for k in ("curp", "clave_elector", "apellido_paterno", "apellido_materno",
                                      "nombres", "estado_electoral", "seccion", "municipio_electoral",
                                      "localidad", "anio_registro", "emision", "vigencia")},
        "domicilio": result.get("domicilio_texto"),
        "mrz": "\n".join(result.get("mrz", {}).get("lineas", [])) or None,
        "qr": " | ".join(c["valor"] for c in codes if "QR" in c["tipo"].upper()) or None,
        "pdf417": " | ".join(c["valor"] for c in codes if "PDF417" in c["tipo"].upper()) or None,
        "sha256": result["sha256"],
    }
    order = [x.strip() for x in os.getenv("ORACLE_SP_PARAMS", ",".join(DEFAULT_SP_PARAMS)).split(",") if x.strip()]
    return [values[name] for name in order]


def oracle_register(result: dict[str, Any]) -> dict[str, Any]:
    """Una transacción: callproc + commit; rollback ante error. Duplicado (ORA-00001) ⇒ 'duplicado'."""
    try:
        conn = oracle_factory()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "estado": "error_oracle", "codigo_error": type(exc).__name__}
    try:
        cur = conn.cursor()
        cur.callproc(os.getenv("ORACLE_SP_NAME", "SP_REGISTRAR_EXPEDIENTE"), _sp_args(result))
        conn.commit()
        return {"ok": True, "estado": "registrado"}
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        code = getattr(getattr(exc, "args", [None])[0], "code", None)
        if code == 1 or "ORA-00001" in str(exc):
            return {"ok": False, "estado": "duplicado", "codigo_error": "ORA-00001"}
        return {"ok": False, "estado": "error_oracle", "codigo_error": type(exc).__name__}
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def audit_record(result: dict[str, Any], processing_id: str, persistence_state: str,
                 error_code: str | None) -> dict[str, Any]:
    """Registro de auditoría SIN datos personales."""
    return {"processing_id": processing_id, "sha256": result["sha256"],
            "document_type": result["clasificacion"], "outcome": result["estado"],
            "duration_ms": result.get("duracion_ms", 0), "persistence_state": persistence_state,
            "error_code": error_code}


_AUDIT_KEYS = ("processing_id", "sha256", "document_type", "outcome", "duration_ms",
               "persistence_state", "error_code")


def sqlserver_audit(record: dict[str, Any]) -> None:
    conn = sqlserver_factory()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.IneAuditLog (ProcessingId, FileSha256, DocumentType, Outcome, DurationMs, "
            "PersistenceState, ErrorCode) VALUES (?, ?, ?, ?, ?, ?, ?)",
            *[record[k] for k in _AUDIT_KEYS])
        conn.commit()
    finally:
        conn.close()


def _outbox() -> Path:
    return Path(os.getenv("AUDIT_OUTBOX_DIR", "data")) / "audit_outbox.jsonl"


_outbox_lock = threading.Lock()


def _queue_outbox(record: dict[str, Any]) -> bool:
    try:
        path = _outbox()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _outbox_lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: record[k] for k in _AUDIT_KEYS} | {"queued_at": time.time()}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except OSError:
        return False


def replay_outbox() -> dict[str, int]:
    path = _outbox()
    if not path.exists():
        return {"reenviados": 0, "pendientes": 0}
    pending, sent = [], 0
    with _outbox_lock:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                sqlserver_audit(json.loads(line))
                sent += 1
            except Exception:  # noqa: BLE001
                pending.append(line)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text("\n".join(pending) + ("\n" if pending else ""), encoding="utf-8")
        os.replace(temp, path)
    return {"reenviados": sent, "pendientes": len(pending)}


_seen_hashes: set[str] = set()


def persist(result: dict[str, Any]) -> dict[str, Any]:
    """Demo: nada se escribe. Corporativo: Oracle solo si estado 'listo'; auditoría de TODO resultado."""
    if mode() == "demo":
        return {"estado": "demo_sin_persistencia", "oracle": NO_CONFIGURADO, "sqlserver": NO_CONFIGURADO,
                "detalle": "Modo demostración: no se realizó ninguna escritura."}
    if not oracle_configured() and not sqlserver_configured():
        return {"estado": "no_configurado", "oracle": NO_CONFIGURADO, "sqlserver": NO_CONFIGURADO,
                "detalle": "Faltan credenciales corporativas; no se escribió nada."}
    if "campos" not in result:  # error de procesamiento: solo se audita, nunca va a Oracle
        result = {**result, "sha256": result.get("sha256") or "0" * 64, "clasificacion": "error",
                  "estado": "error", "duracion_ms": result.get("duracion_ms", 0)}
    processing_id = str(uuid.uuid4())
    oracle_state, error_code, oracle_ok = "no_aplica", None, False
    if result["estado"] == "listo":
        if not oracle_configured():
            oracle_state = NO_CONFIGURADO
        elif result["sha256"] in _seen_hashes:
            oracle_state = "duplicado"
        else:
            outcome = oracle_register(result)
            oracle_state, oracle_ok = outcome["estado"], outcome["ok"]
            error_code = outcome.get("codigo_error")
            if oracle_state == "error_oracle":
                _note_error("oracle", error_code)
            if oracle_ok or oracle_state == "duplicado":
                _seen_hashes.add(result["sha256"])
    persisted = "oracle_ok" if oracle_ok else oracle_state
    record = audit_record(result, processing_id, persisted, error_code)
    audit_state = NO_CONFIGURADO
    if sqlserver_configured():
        try:
            sqlserver_audit(record)
            audit_state = "auditado"
        except Exception as exc:  # noqa: BLE001
            record["error_code"] = record["error_code"] or type(exc).__name__
            _note_error("sqlserver", type(exc).__name__)
            audit_state = "fallo_auditoria" if _queue_outbox(record) else "fallo_auditoria_sin_bandeja"
    final = oracle_state
    if oracle_ok:
        # Inconsistencia controlada cuando Oracle escribió y la auditoría falló (ver MANUAL_TECNICO).
        final = "registrado_sin_auditoria" if audit_state.startswith("fallo") else "registrado"
    return {"estado": final, "oracle": oracle_state, "sqlserver": audit_state,
            "processing_id": processing_id, "codigo_error": error_code}
