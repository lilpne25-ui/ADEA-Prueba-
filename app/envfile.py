"""Carga de `.env.local` (credenciales de DESARROLLO locales). El archivo:
- está en .gitignore y se excluye del ZIP;
- se restringe con ACL al usuario actual de Windows (icacls);
- nunca se imprime ni se registra en logs.
Las variables ya definidas en el entorno tienen prioridad sobre el archivo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env.local"


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_into_environ(path: Path = ENV_PATH) -> None:
    for key, value in read_env(path).items():
        os.environ.setdefault(key, value)


def _restrict(path: Path) -> None:
    if os.name != "nt":
        os.chmod(path, 0o600)
        return
    who = subprocess.run(["whoami"], capture_output=True, text=True, check=False)
    user = who.stdout.strip()  # DOMINIO\usuario exacto del proceso actual
    if user:
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                       capture_output=True, check=False)


def write_env_values(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    current = read_env(path)
    current.update(updates)
    body = "# Credenciales de DESARROLLO local. No compartir, no subir a Git, no incluir en el ZIP.\n"
    body += "\n".join(f"{k}={v}" for k, v in current.items()) + "\n"
    path.write_text(body, encoding="utf-8")
    _restrict(path)
