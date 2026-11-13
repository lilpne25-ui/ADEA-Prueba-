"""Oracle AI Database Free (imagen OFICIAL container-registry.oracle.com/database/free) para DESARROLLO.

- Contenedor `adea-oracle-free`, puerto publicado SOLO en 127.0.0.1:1521, volumen `adea-oracle-data`.
- Esquema propietario ADEA_INE_OWNER (tabla + SP de demostración de sql/oracle_demo.sql).
- Usuario de aplicación ADEA_INE_APP con permisos mínimos: CREATE SESSION, EXECUTE del SP, SELECT de la tabla.
- Contraseñas aleatorias guardadas solo en .env.local (ACL al usuario); nunca se imprimen.
Idempotente: si el contenedor/usuarios existen, no se borran datos.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.envfile import read_env, write_env_values  # noqa: E402
from setup_sqlserver_localdb import strong_password  # noqa: E402

import oracledb  # noqa: E402

IMAGE = "container-registry.oracle.com/database/free:latest-lite"
NAME = "adea-oracle-free"
DSN = "127.0.0.1:1521/FREEPDB1"
OWNER, APP = "ADEA_INE_OWNER", "ADEA_INE_APP"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def ensure_container(sys_pwd: str) -> None:
    exists = docker("ps", "-a", "--filter", f"name=^{NAME}$", "--format", "{{.Names}}").stdout.strip()
    if exists:
        docker("start", NAME, check=False)
        return
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env") as fh:
        fh.write(f"ORACLE_PWD={sys_pwd}\n")  # archivo temporal: evita la contraseña en la línea de comandos
        env_file = fh.name
    try:
        docker("run", "-d", "--name", NAME, "-p", "127.0.0.1:1521:1521", "--env-file", env_file,
               "-v", "adea-oracle-data:/opt/oracle/oradata", "--restart", "unless-stopped", IMAGE)
    finally:
        os.remove(env_file)


def wait_ready(timeout_s: int = 900) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        logs = docker("logs", NAME, check=False)
        if "DATABASE IS READY TO USE" in (logs.stdout + logs.stderr):
            return
        time.sleep(10)
    raise TimeoutError("Oracle no terminó de iniciar a tiempo")


def run_sql_file(cur, path: Path) -> None:
    blocks = [b.strip() for b in path.read_text(encoding="utf-8").split("\n/") if b.strip()]
    for block in blocks:
        body = "\n".join(l for l in block.splitlines() if not l.strip().startswith("--")).strip()
        if not body:
            continue
        if not body.upper().startswith(("CREATE OR REPLACE PROCEDURE", "BEGIN", "DECLARE")):
            body = body.rstrip(";")
        try:
            cur.execute(body)
        except oracledb.DatabaseError as exc:
            if "ORA-00955" not in str(exc):  # objeto ya existe → idempotente
                raise


def main() -> None:
    env = read_env()
    sys_pwd = env.get("ADEA_ORACLE_SYS_PASSWORD") or strong_password()
    owner_pwd = env.get("ADEA_ORACLE_OWNER_PASSWORD") or strong_password()
    app_pwd = env.get("ORACLE_PASSWORD") or strong_password()
    write_env_values({"ADEA_ORACLE_SYS_PASSWORD": sys_pwd, "ADEA_ORACLE_OWNER_PASSWORD": owner_pwd})
    ensure_container(sys_pwd)
    wait_ready()

    with oracledb.connect(user="system", password=sys_pwd, dsn=DSN) as conn:
        cur = conn.cursor()
        for user, pwd in ((OWNER, owner_pwd), (APP, app_pwd)):
            cur.execute("SELECT COUNT(*) FROM dba_users WHERE username = :u", u=user)
            verb = "ALTER" if cur.fetchone()[0] else "CREATE"
            cur.execute(f'{verb} USER {user} IDENTIFIED BY "{pwd}"')
        cur.execute(f"GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE PROCEDURE TO {OWNER}")
        # La imagen "lite" no trae el tablespace USERS: se crea uno propio dentro del volumen persistente.
        cur.execute("SELECT COUNT(*) FROM dba_tablespaces WHERE tablespace_name = 'ADEA_DATA'")
        if not cur.fetchone()[0]:
            cur.execute("SELECT file_name FROM dba_data_files WHERE ROWNUM = 1")
            folder = cur.fetchone()[0].rsplit("/", 1)[0]
            cur.execute(f"CREATE TABLESPACE ADEA_DATA DATAFILE '{folder}/adea_data01.dbf' "
                        "SIZE 50M AUTOEXTEND ON NEXT 10M MAXSIZE 500M")
        cur.execute(f"ALTER USER {OWNER} DEFAULT TABLESPACE ADEA_DATA QUOTA 200M ON ADEA_DATA")
        cur.execute(f"GRANT CREATE SESSION TO {APP}")

    with oracledb.connect(user=OWNER, password=owner_pwd, dsn=DSN) as conn:
        cur = conn.cursor()
        run_sql_file(cur, ROOT / "sql" / "oracle_demo.sql")
        cur.execute(f"GRANT EXECUTE ON SP_REGISTRAR_EXPEDIENTE TO {APP}")
        cur.execute(f"GRANT SELECT ON INE_EXPEDIENTES_DEMO TO {APP}")

    with oracledb.connect(user=APP, password=app_pwd, dsn=DSN) as conn:
        conn.cursor().execute(f"SELECT COUNT(*) FROM {OWNER}.INE_EXPEDIENTES_DEMO")

    write_env_values({
        "ORACLE_USER": APP, "ORACLE_PASSWORD": app_pwd, "ORACLE_DSN": DSN,
        "ORACLE_SP_NAME": f"{OWNER}.SP_REGISTRAR_EXPEDIENTE",
        "ORACLE_COUNT_QUERY": f"SELECT COUNT(*), MAX(CREADO_EN) FROM {OWNER}.INE_EXPEDIENTES_DEMO",
    })
    print("Oracle listo: contenedor adea-oracle-free (127.0.0.1:1521/FREEPDB1), esquema ADEA_INE_OWNER, "
          "usuario ADEA_INE_APP con permisos mínimos. Credenciales en .env.local (no se muestran).")


if __name__ == "__main__":
    main()
