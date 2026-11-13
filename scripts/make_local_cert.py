"""Certificado autofirmado para HTTPS en la red local (necesario para usar la cámara en vivo en el celular).

Genera certs/local.crt y certs/local.key (ignorados por Git) válidos para localhost, 127.0.0.1 y las IPv4
privadas actuales del equipo. El celular mostrará una advertencia la primera vez: es esperado en un
certificado autofirmado de red privada; acéptala solo en tu propia red.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "certs"


def private_ips() -> list[str]:
    ips = set()
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        if ipaddress.ip_address(ip).is_private:
            ips.add(ip)
    return sorted(ips)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    ips = ["127.0.0.1", *private_ips()]
    san = x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                       *[x509.IPAddress(ipaddress.ip_address(i)) for i in ips]])
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "INE Control (red local)")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=365)).add_extension(san, critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    (OUT / "local.key").write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                      serialization.PrivateFormat.PKCS8,
                                                      serialization.NoEncryption()))
    (OUT / "local.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Certificado HTTPS local creado para: localhost, {', '.join(ips)} (vigencia 365 días).")


if __name__ == "__main__":
    main()
