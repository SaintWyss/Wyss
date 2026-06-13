"""Stubs del daemon asyncio (ORCH-01/02) — Plan 05-04 implementa.

Scaffolding Wave 0: los archivos existen y se recolectan; los tests reales se activan
cuando 05-04 cablea el daemon sobre Unix socket JSON-RPC.
"""

import pytest


@pytest.mark.skip(reason="Wave 2: 05-04 implementa daemon (ORCH-01 stale socket cleanup)")
def test_stale_socket_cleanup() -> None:
    """ORCH-01: el daemon limpia un socket stale al arrancar y rebindea."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 2: 05-04 implementa daemon (ORCH-02 JSON-RPC round-trip)")
def test_ask_round_trip() -> None:
    """ORCH-02: `ask` por JSON-RPC sobre el socket devuelve respuesta del dispatcher."""
    raise NotImplementedError
