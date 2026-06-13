"""Política de error por paso del Plan (ORCH-07 / D-62)."""

from enum import StrEnum

from core.domain.plan import Action, ErrorPolicy, RetryParams


def test_action_on_error_default_abort() -> None:
    """ORCH-07: una Action sin on_error explícito aborta el Plan ante error (default seguro)."""
    action = Action("file.read", "~/x")

    assert action.on_error == ErrorPolicy.ABORT
    assert action.retry_params is None


def test_action_on_error_roundtrip() -> None:
    """D-62: on_error se serializa/deserializa preservando el valor declarado."""
    retry_params = RetryParams(max_attempts=5)
    action = Action(
        "file.write",
        "~/x",
        on_error=ErrorPolicy.RETRY,
        retry_params=retry_params,
    )

    assert action.on_error == ErrorPolicy.RETRY
    assert action.retry_params == retry_params


def test_action_positional_callsites_remain_compatible() -> None:
    """Regresión: los callsites posicionales existentes siguen construyendo Actions."""
    action = Action("file.delete", "~/Documents/tmp.md", {"recursive": False})

    assert action.parameters == {"recursive": False}
    assert action.on_error == ErrorPolicy.ABORT


def test_error_policy_is_str_enum() -> None:
    assert issubclass(ErrorPolicy, StrEnum)
    assert ErrorPolicy.RETRY.value == "retry"
    assert ErrorPolicy.ESCALATE.value == "escalate"
    assert ErrorPolicy.ABORT.value == "abort"
