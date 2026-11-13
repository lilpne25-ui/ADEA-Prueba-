"""Servidor local de Windows: un solo proceso con dos puertas.

- http://127.0.0.1:8000  → solo este equipo (navegador de escritorio).
- https://0.0.0.0:8443   → red local (celular), únicamente si existe certs/local.crt.
Sin certificado, la app sigue disponible en la LAN por http://IP:8000 como en versiones anteriores.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main() -> None:
    cert, key = ROOT / "certs" / "local.crt", ROOT / "certs" / "local.key"
    servers = []
    if cert.exists() and key.exists():
        servers.append(uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=8000)))
        servers.append(uvicorn.Server(uvicorn.Config("app.main:app", host="0.0.0.0", port=8443,
                                                     ssl_certfile=str(cert), ssl_keyfile=str(key))))
        print("Escritorio: http://localhost:8000   ·   Celular (HTTPS, misma Wi-Fi): https://IP-DE-ESTA-PC:8443")
    else:
        servers.append(uvicorn.Server(uvicorn.Config("app.main:app", host="0.0.0.0", port=8000)))
        print("Sin certificado HTTPS local: http://localhost:8000 (celular: http://IP-DE-ESTA-PC:8000)")
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
