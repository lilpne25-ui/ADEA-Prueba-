"""Configura la auditoría de desarrollo en una instancia LocalDB AISLADA (no toca otras instancias).

- Instancia: (localdb)\\ADEA_INE  (crear antes con: SqlLocalDB create ADEA_INE -s)
- Base: ADEA_INE_DEV · login/usuario: adea_ine_app con permisos mínimos (INSERT/SELECT en la bitácora)
- Genera una contraseña aleatoria y la guarda SOLO en .env.local (ignorado por Git y excluido del ZIP).
  Nunca la imprime. Idempotente: si ya existe, no recrea objetos ni borra datos.
"""

from __future__ import annotations

import secrets
import string
import sys
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.envfile import read_env, write_env_values  # noqa: E402

INSTANCE = r"(localdb)\ADEA_INE"
DB = "ADEA_INE_DEV"
LOGIN = "adea_ine_app"
DRIVER = "ODBC Driver 18 for SQL Server"


def strong_password(n: int = 28) -> str:
    alphabet = string.ascii_letters + string.digits + "-_.~"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if any(c.isdigit() for c in pw) and any(c.islower() for c in pw) and any(c.isupper() for c in pw):
            return pw


def main() -> None:
    env = read_env()
    password = env.get("ADEA_SQL_PASSWORD") or strong_password()
    admin = pyodbc.connect(f"Driver={{{DRIVER}}};Server={INSTANCE};Trusted_Connection=yes;"
                           "Encrypt=yes;TrustServerCertificate=yes", autocommit=True, timeout=15)
    cur = admin.cursor()
    if not cur.execute("SELECT DB_ID(?)", DB).fetchone()[0]:
        # Si la instancia LocalDB fue eliminada pero sus archivos quedaron intactos,
        # se adjuntan para recuperar los datos en vez de sobrescribirlos.
        mdf = Path.home() / f"{DB}.mdf"
        ldf = Path.home() / f"{DB}_log.ldf"
        if mdf.exists() and ldf.exists():
            mdf_sql = str(mdf).replace("'", "''")
            ldf_sql = str(ldf).replace("'", "''")
            cur.execute(f"CREATE DATABASE [{DB}] ON (FILENAME=N'{mdf_sql}'), "
                        f"(FILENAME=N'{ldf_sql}') FOR ATTACH")
        else:
            cur.execute(f"CREATE DATABASE [{DB}]")
    # CREATE LOGIN no admite parámetros: la contraseña generada (alfabeto seguro) se escapa como literal.
    exists = cur.execute("SELECT 1 FROM sys.server_principals WHERE name = ?", LOGIN).fetchone()
    quoted = password.replace("'", "''")
    if not exists:
        cur.execute(f"CREATE LOGIN [{LOGIN}] WITH PASSWORD = N'{quoted}', CHECK_POLICY = ON, DEFAULT_DATABASE = [{DB}]")
    else:
        cur.execute(f"ALTER LOGIN [{LOGIN}] WITH PASSWORD = N'{quoted}'")
    cur.execute(f"USE [{DB}]")
    cur.execute("""
IF OBJECT_ID('dbo.IneAuditLog') IS NULL
CREATE TABLE dbo.IneAuditLog (
    Id BIGINT IDENTITY(1,1) PRIMARY KEY,
    ProcessingId UNIQUEIDENTIFIER NOT NULL,
    FileSha256 CHAR(64) NOT NULL,
    DocumentType VARCHAR(20) NOT NULL,
    Outcome VARCHAR(20) NOT NULL,
    DurationMs INT NOT NULL,
    PersistenceState VARCHAR(40) NOT NULL,
    ErrorCode VARCHAR(60) NULL,
    CreatedAtUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);""")
    cur.execute("IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_IneAuditLog_Sha') "
                "CREATE INDEX IX_IneAuditLog_Sha ON dbo.IneAuditLog (FileSha256)")
    if cur.execute("SELECT DATABASE_PRINCIPAL_ID(?)", LOGIN).fetchone()[0]:
        cur.execute(f"ALTER USER [{LOGIN}] WITH LOGIN = [{LOGIN}]")
    else:
        cur.execute(f"CREATE USER [{LOGIN}] FOR LOGIN [{LOGIN}]")
    cur.execute(f"GRANT INSERT, SELECT ON dbo.IneAuditLog TO [{LOGIN}]")
    admin.close()

    conn_str = (f"Driver={{{DRIVER}}};Server={INSTANCE};Database={DB};UID={LOGIN};PWD={password};"
                "Encrypt=yes;TrustServerCertificate=yes")
    test = pyodbc.connect(conn_str, timeout=15)
    test.cursor().execute("SELECT COUNT(*) FROM dbo.IneAuditLog").fetchone()
    test.close()
    write_env_values({"ADEA_SQL_PASSWORD": password, "SQLSERVER_CONNECTION_STRING": conn_str})
    print("SQL Server LocalDB listo: base ADEA_INE_DEV, usuario adea_ine_app (permisos INSERT/SELECT). "
          "Credenciales guardadas en .env.local (no se muestran).")


if __name__ == "__main__":
    main()
