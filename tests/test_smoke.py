"""Smoke test del layout flat multi-paquete.

Importa los 8 paquetes top-level (más los subpaquetes de core) para verificar que
``uv sync`` los instaló como importables sin prefijo ``src.*`` y que el esqueleto
hexagonal existe. También evita el exit code 5 de pytest (sin tests recolectados).
"""

import importlib

PACKAGES = [
    "core",
    "core.domain",
    "core.ports",
    "core.policy",
    "orchestrator",
    "agents",
    "knowledge",
    "gateway",
    "execution",
    "audit",
    "bootstrap",
]


def test_top_level_packages_importan() -> None:
    for name in PACKAGES:
        module = importlib.import_module(name)
        assert module is not None, f"no se pudo importar el paquete {name!r}"
