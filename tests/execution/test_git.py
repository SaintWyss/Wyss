"""Tests para GitAdapter (Task 2, plan 06-03).

TDD — fase RED: los tests se escriben antes de la implementación.

Cubre:
  - Subcomandos fuera del allowlist: bloqueados, auditados, sin proceso
  - Subcomandos permitidos: ejecutan `git <sub> <args>` vía argv en repo cwd
  - verify(): pasa solo con returncode == 0
  - Invariante shell=False (AST check)
"""

import ast
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.domain.audit import AuditEventType
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from tests.execution.conftest import FakeAudit

if TYPE_CHECKING:
    from execution.git import GitAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_action(subcommand: str, *args: str, cwd: str = "") -> Action:
    """Construye una Action git con target=subcommand y args en parameters."""
    params: dict[str, object] = {"args": list(args)}
    if cwd:
        params["cwd"] = cwd
    return Action(
        type="git.run",
        target=subcommand,
        parameters=params,
    )


def _make_adapter(
    audit: FakeAudit,
    repo_path: Path,
    allowed: set[str] | None = None,
) -> "GitAdapter":
    """Crea GitAdapter con FakeAudit, repo_path y allowlist explícita."""
    from execution.git import GitAdapter

    if allowed is None:
        allowed = {"status", "diff", "add", "commit", "log"}
    return GitAdapter(
        audit=audit,
        repo_path=repo_path,
        allowed_subcommands=allowed,
        timeout_s=10.0,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Repositorio git vacío inicializado en tmp_path para los tests."""
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@wyss.local"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.name", "Wyss Test"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Test 1: subcomando fuera del allowlist — bloqueado sin proceso, auditado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_subcommand(git_repo: Path) -> None:
    """Un subcomando git fuera del allowlist debe fallar sin spawnar ningún proceso."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, git_repo, allowed={"status", "diff"})
    # "push" no está en el allowlist
    action = _make_action("push", "origin", "main")

    result = await adapter.execute(action)

    assert result.success is False
    assert "allowlist" in result.detail.lower() or "blocked" in result.detail.lower()

    # Exactamente un evento de auditoría
    assert len(audit.events) == 1
    ev = audit.events[0]
    assert ev.event_type == AuditEventType.ACTION_COMPLETED
    assert ev.payload.get("blocked") == "allowlist"
    assert ev.payload.get("binary") == "push"

    # Sin returncode en payload (no hubo proceso)
    assert "returncode" not in result.payload


# ---------------------------------------------------------------------------
# Test 2: subcomando permitido ejecuta git status en repo real
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_status_runs(git_repo: Path) -> None:
    """'git status' en un repo real debe retornar success=True y returncode=0."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, git_repo)
    action = _make_action("status")

    result = await adapter.execute(action)

    assert result.success is True
    assert result.payload["returncode"] == 0
    # git status siempre produce algo en stdout
    assert isinstance(result.payload.get("stdout"), str)


# ---------------------------------------------------------------------------
# PR-11: flags con capacidad de escritura bloqueados en subcomandos de lectura
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_subcommand_write_flag_blocked(git_repo: Path) -> None:
    """git log/diff/status son nivel A (lectura): --output/-o escribe a disco y se
    bloquea sin spawnar proceso, auditado."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, git_repo)

    for args in (("--output=/tmp/exfil",), ("-o", "/tmp/exfil")):
        result = await adapter.execute(_make_action("log", *args))
        assert result.success is False
        assert "no permitido" in result.detail
        assert result.payload.get("blocked") == "write_flag"
        assert "returncode" not in result.payload  # no hubo proceso

    blocked_events = [e for e in audit.events if e.payload.get("blocked") == "write_flag"]
    assert len(blocked_events) == 2


@pytest.mark.asyncio
async def test_read_subcommand_normal_args_still_run(git_repo: Path) -> None:
    """Args normales de lectura (p.ej. --oneline) siguen pasando."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, git_repo)

    result = await adapter.execute(_make_action("status", "--short"))

    assert result.success is True
    assert result.payload["returncode"] == 0


# ---------------------------------------------------------------------------
# Test 3: verify() pasa con returncode == 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_passes_on_zero_returncode(git_repo: Path) -> None:
    """verify() retorna passed=True cuando success=True y returncode=0."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, git_repo)
    action = _make_action("status")

    result = await adapter.execute(action)
    verification = await adapter.verify(action, result)

    assert result.success is True
    assert result.payload["returncode"] == 0
    assert verification.passed is True


# ---------------------------------------------------------------------------
# Test 4: verify() falla cuando bloqueado (success=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_fails_when_blocked(git_repo: Path) -> None:
    """verify() retorna passed=False cuando el subcomando fue bloqueado."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, git_repo, allowed={"status"})
    action = _make_action("clone", "http://evil.example.com")

    result = await adapter.execute(action)
    verification = await adapter.verify(action, result)

    assert result.success is False
    assert verification.passed is False


# ---------------------------------------------------------------------------
# Test 5: invariante shell=False — verificación AST en git.py
# ---------------------------------------------------------------------------


def test_git_adapter_never_uses_shell_equals_true() -> None:
    """Ningún keyword argument `shell=True` en git.py (verificación AST)."""
    src = Path("src/execution/git.py")
    if not src.exists():
        pytest.skip("git.py aún no existe (fase RED)")

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

    assert violations == [], f"shell=True como keyword argument en git.py: {violations}"


# ---------------------------------------------------------------------------
# Test 6: propiedades del protocolo Tool
# ---------------------------------------------------------------------------


def test_git_adapter_protocol_properties(tmp_path: Path) -> None:
    """GitAdapter debe exponer name='git' y max_risk=RiskLevel.B."""
    audit = FakeAudit()
    adapter = _make_adapter(audit, tmp_path)

    assert adapter.name == "git"
    assert adapter.max_risk == RiskLevel.B


# ---------------------------------------------------------------------------
# Test 7: describe() retorna string no vacío
# ---------------------------------------------------------------------------


def test_git_adapter_describe(tmp_path: Path) -> None:
    audit = FakeAudit()
    adapter = _make_adapter(audit, tmp_path)
    action = _make_action("status")

    description = adapter.describe(action)

    assert isinstance(description, str)
    assert "git" in description.lower() or "status" in description.lower()
