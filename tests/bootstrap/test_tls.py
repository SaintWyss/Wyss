"""Tests de bootstrap/tls.py (PR-10): generación self-signed con openssl del sistema."""

from pathlib import Path

from bootstrap.tls import ensure_certificate, fingerprint_sha256


def test_generates_cert_and_key(tmp_path: Path) -> None:
    cert, key = ensure_certificate(tmp_path / "tls", ["localhost", "127.0.0.1"])

    assert cert.exists()
    assert key.exists()
    assert (key.stat().st_mode & 0o777) == 0o600  # clave privada = secreta
    assert b"BEGIN CERTIFICATE" in cert.read_bytes()


def test_existing_cert_reused_when_covers_hosts(tmp_path: Path) -> None:
    tls_dir = tmp_path / "tls"
    cert, _ = ensure_certificate(tls_dir, ["localhost", "127.0.0.1"])
    original = cert.read_bytes()

    cert2, _ = ensure_certificate(tls_dir, ["localhost", "127.0.0.1"])

    assert cert2.read_bytes() == original  # no se regeneró


def test_regenerates_when_host_missing(tmp_path: Path) -> None:
    """Cambió la IP LAN (DHCP): el cert viejo no cubre el host nuevo → se regenera."""
    tls_dir = tmp_path / "tls"
    cert, _ = ensure_certificate(tls_dir, ["localhost", "127.0.0.1"])
    original = cert.read_bytes()

    cert2, _ = ensure_certificate(tls_dir, ["localhost", "127.0.0.1", "192.168.100.5"])

    assert cert2.read_bytes() != original  # regenerado con el SAN nuevo
    # y ahora sí cubre: una tercera llamada no regenera
    cert3, _ = ensure_certificate(tls_dir, ["192.168.100.5"])
    assert cert3.read_bytes() == cert2.read_bytes()


def test_fingerprint_format(tmp_path: Path) -> None:
    cert, _ = ensure_certificate(tmp_path / "tls", ["localhost"])

    fp = fingerprint_sha256(cert)

    # SHA-256 en hex con separador de dos puntos: 32 pares
    assert len(fp.split(":")) == 32
