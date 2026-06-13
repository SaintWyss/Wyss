"""Tests para ShellAdapter (Task 1, plan 06-03).

TDD — fase RED: los tests se escriben antes de la implementación.

Cubre:
  - Binarios fuera de allowlist: bloqueados, auditados, sin proceso
  - Binarios permitidos: ejecutan vía argv (create_subprocess_exec)
  - Timeout: proceso matado, sin zombie
  - verify(): pasa solo con returncode == 0
  - Invariante shell=False: grep en el fuente
"""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.domain.audit import AuditEventType
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from tests.execution.conftest import FakeAudit

if TYPE_CHECKING:
    from execution.shell import ShellAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_action(binary: str, *args: str) -> Action:
    """Construye una Action con target=binary y args en parameters."""
    return Action(
        type="shell.run",
        target=binary,
        parameters={"args": list(args)},
    )


def _make_adapter(audit: FakeAudit, allowed: set[str] | None = None) -> "ShellAdapter":
    """Crea ShellAdapter con FakeAudit y allowlist explícita (sin TOML)."""
    from execution.shell import ShellAdapter

    if allowed is None:
        allowed = {"echo", "true", "false"}
    return ShellAdapter(audit=audit, allowed_binaries=allowed, timeout_s=5.0)


# ---------------------------------------------------------------------------
# Test 1: binario fuera del allowlist — bloqueado sin proceso, auditado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_binary_not_in_allowlist() -> None:
    """Un binario fuera del allowlist debe fallar sin spawnar ningún proceso."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, allowed={"echo"})
    action = _make_action("rm", "-rf", "/tmp/anything")

    result = await adapter.execute(action)

    # Retorno correcto
    assert result.success is False
    assert "allowlist" in result.detail.lower() or "blocked" in result.detail.lower()

    # Exactamente un evento de auditoría
    assert len(audit.events) == 1
    ev = audit.events[0]
    assert ev.event_type == AuditEventType.ACTION_COMPLETED
    assert ev.payload.get("blocked") == "allowlist"
    assert ev.payload.get("binary") == "rm"

    # Ningún returncode en payload (no hubo proceso)
    assert "returncode" not in result.payload


# ---------------------------------------------------------------------------
# Test 2: binario permitido ejecuta vía argv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_binary_executes() -> None:
    """Un binario en el allowlist se ejecuta y devuelve stdout/stderr/returncode."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, allowed={"echo"})
    action = _make_action("echo", "hello wyss")

    result = await adapter.execute(action)

    assert result.success is True
    assert result.payload["returncode"] == 0
    assert "hello wyss" in str(result.payload["stdout"])


# ---------------------------------------------------------------------------
# Test 3: verify() pasa con returncode == 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_passes_on_zero_exit() -> None:
    """verify() debe retornar passed=True cuando success=True y returncode=0."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, allowed={"true"})
    action = _make_action("true")

    result = await adapter.execute(action)
    verification = await adapter.verify(action, result)

    assert result.success is True
    assert result.payload["returncode"] == 0
    assert verification.passed is True


# ---------------------------------------------------------------------------
# Test 4: verify() falla con returncode != 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_fails_on_nonzero_exit() -> None:
    """verify() debe retornar passed=False cuando returncode != 0."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, allowed={"false"})
    action = _make_action("false")

    result = await adapter.execute(action)
    # 'false' siempre retorna 1
    verification = await adapter.verify(action, result)

    assert result.payload["returncode"] != 0
    assert verification.passed is False


# ---------------------------------------------------------------------------
# Test 5: verify() falla cuando success=False (blockeado)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_fails_when_blocked() -> None:
    """verify() debe retornar passed=False para resultados de binarios bloqueados."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, allowed={"echo"})
    action = _make_action("wget", "http://evil.example.com")

    result = await adapter.execute(action)
    verification = await adapter.verify(action, result)

    assert result.success is False
    assert verification.passed is False


# ---------------------------------------------------------------------------
# Test 6: invariante shell=False — grep en el código fuente
# ---------------------------------------------------------------------------


def test_shell_adapter_never_uses_shell_equals_true() -> None:
    """Ningún argumento de keyword `shell=True` debe aparecer en código ejecutable de shell.py.

    El grep excluye líneas que son solo comentarios (`#`) o docstrings/strings (`\"\"\"`, `#`).
    La invariante D-66 se verifica a nivel AST: `shell=True` como keyword argument en una
    llamada es la firma del riesgo de injection. Las menciones en strings/docstrings son
    documentación, no código ejecutable.
    """
    import ast

    src = Path("src/execution/shell.py")
    if not src.exists():
        pytest.skip("shell.py aún no existe (fase RED)")

    tree = ast.parse(src.read_text())
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    violations.append(f"línea {kw.value.lineno}: shell=True en llamada")

    assert violations == [], f"shell=True como keyword argument encontrado en: {violations}"


# ---------------------------------------------------------------------------
# Test 7: propiedades del protocolo Tool
# ---------------------------------------------------------------------------


def test_shell_adapter_protocol_properties() -> None:
    """ShellAdapter debe exponer name='shell' y max_risk=RiskLevel.B."""
    audit = FakeAudit()
    adapter = _make_adapter(audit)

    assert adapter.name == "shell"
    assert adapter.max_risk == RiskLevel.B


# ---------------------------------------------------------------------------
# Test 8: describe() retorna string no vacío
# ---------------------------------------------------------------------------


def test_shell_adapter_describe() -> None:
    audit = FakeAudit()
    adapter = _make_adapter(audit)
    action = _make_action("echo", "hola")

    description = adapter.describe(action)

    assert isinstance(description, str)
    assert len(description) > 0
