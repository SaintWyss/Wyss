"""Certificados TLS locales para `wyss web --tls` (PR-10).

Sin mkcert obligatorio: si `data/tls/` no tiene certificado, se genera uno
self-signed con el `openssl` del sistema (SAN = localhost + 127.0.0.1 + IP LAN).
El browser del teléfono muestra el aviso de certificado desconocido UNA vez; la
huella SHA-256 impresa por la CLI permite verificarlo a mano antes de aceptar.

Quien quiera cero avisos puede instalar mkcert por su cuenta y dejar sus archivos
en `data/tls/cert.pem` + `data/tls/key.pem`: si existen y cubren los hosts
pedidos, se usan tal cual (no se pisan).

Si el certificado existente NO cubre algún host (típico: cambió la IP LAN por
DHCP), se regenera automáticamente — un cert que no matchea el host solo produce
errores crípticos en el teléfono.
"""

import ipaddress
import subprocess
from collections.abc import Sequence
from pathlib import Path

_VALIDITY_DAYS = 825  # tope que aceptan los browsers para certs de este tipo


def ensure_certificate(tls_dir: Path, hosts: Sequence[str]) -> tuple[Path, Path]:
    """Devuelve (cert.pem, key.pem) en `tls_dir`, generando si falta o no cubre hosts.

    Raises FileNotFoundError si openssl no está en PATH y
    subprocess.CalledProcessError si openssl falla.
    """
    cert = tls_dir / "cert.pem"
    key = tls_dir / "key.pem"
    if cert.exists() and key.exists() and _covers_hosts(cert, hosts):
        return cert, key

    tls_dir.mkdir(parents=True, exist_ok=True)
    san = ",".join(_san_entry(host) for host in dict.fromkeys(hosts))
    subprocess.run(
        [
            "openssl", "req", "-x509",
            "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-keyout", str(key),
            "-out", str(cert),
            "-days", str(_VALIDITY_DAYS),
            "-nodes",
            "-subj", "/CN=wyss-local",
            "-addext", f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )
    key.chmod(0o600)  # la clave privada es secreta como el token
    return cert, key


def fingerprint_sha256(cert: Path) -> str:
    """Huella SHA-256 del certificado, para verificación manual en el teléfono."""
    proc = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha256"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip().split("=", 1)[-1]


def _san_entry(host: str) -> str:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return f"DNS:{host}"
    return f"IP:{host}"


def _needle(host: str) -> str:
    """Cómo aparece el host en el texto de `openssl x509 -ext subjectAltName`."""
    entry = _san_entry(host)
    if entry.startswith("IP:"):
        return f"IP Address:{host}"
    return entry


def _covers_hosts(cert: Path, hosts: Sequence[str]) -> bool:
    proc = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False  # cert ilegible/corrupto → regenerar
    return all(_needle(host) in proc.stdout for host in hosts)
