"""Stubs de la política de error por paso del Plan (ORCH-07 / D-62) — Plan 05-02 implementa.

Scaffolding Wave 0. Verifica el default `abort` de `Action.on_error` y su roundtrip.
"""

import pytest


@pytest.mark.skip(reason="Wave 1: 05-02 extiende Action con on_error (ORCH-07/D-62)")
def test_action_on_error_default_abort() -> None:
    """ORCH-07: una Action sin on_error explícito aborta el Plan ante error (default seguro)."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1: 05-02 extiende Action con on_error (D-62 roundtrip)")
def test_action_on_error_roundtrip() -> None:
    """D-62: on_error se serializa/deserializa preservando el valor declarado."""
    raise NotImplementedError
