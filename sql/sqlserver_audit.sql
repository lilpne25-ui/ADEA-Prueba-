-- Auditoría SIN datos personales. Ejecutar solo en un entorno de PRUEBAS autorizado.
-- Coincide con el INSERT parametrizado de app/persistence.py (7 parámetros).
CREATE TABLE dbo.IneAuditLog (
    Id               BIGINT IDENTITY(1,1) PRIMARY KEY,
    ProcessingId     UNIQUEIDENTIFIER NOT NULL,
    FileSha256       CHAR(64)         NOT NULL,
    DocumentType     VARCHAR(20)      NOT NULL,   -- ine | no_ine | revision | posible_reverso | error
    Outcome          VARCHAR(20)      NOT NULL,   -- listo | revision | descartado | error
    DurationMs       INT              NOT NULL,
    PersistenceState VARCHAR(40)      NOT NULL,   -- oracle_ok | duplicado | error_oracle | no_aplica | NO_CONFIGURADO
    ErrorCode        VARCHAR(60)      NULL,
    CreatedAtUtc     DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_IneAuditLog_Sha ON dbo.IneAuditLog (FileSha256);
-- Nunca almacenar imágenes, CURP, nombres ni domicilios en esta tabla.
