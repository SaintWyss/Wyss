"""Tests de CLI Daily Assistant."""

import grp
import pwd
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from typer.testing import CliRunner

import bootstrap.cli as cli
from bootstrap.cli import app
from bootstrap.config import load_settings
from core.domain.errors import ConfigError
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import Outcome, RiskLevel
from core.policy import CognitivePolicyEngine
from orchestrator.pending_store import PendingStore

runner = CliRunner()


class _Closable:
    instances: ClassVar[list[Any]]

    def __init__(self, path: Path) -> None:
        self.path = path
        self.closed = False
        self.__class__.instances.append(self)

    def close(self) -> None:
        self.closed = True


class _FakeAudit(_Closable):
    instances: ClassVar[list["_FakeAudit"]] = []

    def log(self, event: object) -> None:
        del event


class _FakePendingStore(_Closable):
    instances: ClassVar[list["_FakePendingStore"]] = []


class _FakeRoutineStore(_Closable):
    instances: ClassVar[list["_FakeRoutineStore"]] = []


class _FakeMemoryStore(_Closable):
    instances: ClassVar[list["_FakeMemoryStore"]] = []


class _FakeLedgerStore(_Closable):
    instances: ClassVar[list["_FakeLedgerStore"]] = []


class _FakeScheduler:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeJournal:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeRunner:
    pass


def test_start_constructs_and_closes_ledger_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_config(tmp_path)
    _patch_start_dependencies(monkeypatch)

    async def fake_run_start_daemon(*args: object) -> None:
        del args

    monkeypatch.setattr(cli, "_run_start_daemon", fake_run_start_daemon)

    result = runner.invoke(app, ["start", "--config", str(cfg)])

    assert result.exit_code == 0
    assert len(_FakeLedgerStore.instances) == 1
    assert _FakeLedgerStore.instances[0].path == tmp_path / "data" / "ledger.db"
    assert _FakeLedgerStore.instances[0].closed is True


async def test_run_start_daemon_passes_ledger_and_digest_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WYSS_HOME_EDGE_USER", raising=False)
    monkeypatch.delenv("WYSS_HOME_EDGE_GROUP", raising=False)
    monkeypatch.delenv("WYSS_HOME_SOCKET_PATH", raising=False)
    cfg = _write_config(tmp_path, digest_enabled=True)
    settings = load_settings(cfg)
    audit = _FakeAudit(settings.audit_db)
    pending = _FakePendingStore(settings.data_dir / "pending.db")
    routine = _FakeRoutineStore(settings.data_dir / "routines.db")
    memory = _FakeMemoryStore(settings.data_dir / "memory.db")
    ledger = _FakeLedgerStore(settings.data_dir / "ledger.db")
    scheduler = _FakeScheduler()
    journal = _FakeJournal()
    captured: dict[str, object] = {}

    def fake_build_plan_runner(*args: object) -> tuple[_FakeRunner, _FakeJournal]:
        del args
        return _FakeRunner(), journal

    async def fake_run_daemon(socket_path: Path, **kwargs: object) -> None:
        captured["socket_path"] = socket_path
        captured.update(kwargs)

    monkeypatch.setattr(cli, "_build_plan_runner", fake_build_plan_runner)
    monkeypatch.setattr(cli, "run_daemon", fake_run_daemon)

    await cli._run_start_daemon(
        settings,
        CognitivePolicyEngine(settings.policy),
        cast(Any, pending),
        cast(Any, audit),
        cast(Any, routine),
        cast(Any, memory),
        cast(Any, ledger),
        cast(Any, scheduler),
    )

    assert captured["ledger"] is ledger
    assert captured["digest_enabled"] is True
    assert captured["home_socket_path"] is None
    assert captured["digest_hour"] == 7
    assert captured["digest_minute"] == 30
    assert captured["digest_dir"] == settings.data_dir / "digests"
    assert journal.closed is True


def test_home_edge_identity_resolves_distinct_system_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WYSS_HOME_EDGE_USER", "wyss-edge")
    monkeypatch.setenv("WYSS_HOME_EDGE_GROUP", "wyss-home")
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda account: SimpleNamespace(pw_uid=4242, pw_gid=4243),
    )
    monkeypatch.setattr(
        grp,
        "getgrnam",
        lambda group: SimpleNamespace(gr_gid=4343, gr_mem=["wyss-edge"]),
    )

    assert cli._home_edge_identity() == (4242, 4343)


def test_home_edge_identity_rejects_missing_group_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WYSS_HOME_EDGE_USER", "wyss-edge")
    monkeypatch.setenv("WYSS_HOME_EDGE_GROUP", "wyss-home")
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda account: SimpleNamespace(pw_uid=4242, pw_gid=4243),
    )
    monkeypatch.setattr(
        grp,
        "getgrnam",
        lambda group: SimpleNamespace(gr_gid=4343, gr_mem=[]),
    )

    with pytest.raises(ConfigError, match="no pertenece"):
        cli._home_edge_identity()


def test_confirm_reprompts_when_policy_escalates_b_to_c(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _write_config(tmp_path)
    store = PendingStore(tmp_path / "data" / "pending.db")
    try:
        pending_id = store.save(
            Plan(
                task_id="cli-escalation",
                summary="escalada",
                steps=(Action("file.write", str(tmp_path / "note.txt"), {"content": "x"}),),
                rationale="test",
            ),
            PolicyDecision("cli-escalation", RiskLevel.B, Outcome.CONFIRM_SIMPLE),
            ttl_seconds=600,
        )
    finally:
        store.close()

    prompts: list[RiskLevel] = []
    calls: list[dict[str, object]] = []

    def accept(decision: PolicyDecision, console: object) -> bool:
        del console
        prompts.append(decision.risk_level)
        return True

    async def fake_rpc(path: Path, method: str, params: dict[str, object]) -> dict[str, Any]:
        del path, method
        calls.append(params)
        if len(calls) == 1:
            return {
                "accepted": False,
                "required_risk": "C",
                "reason": "el riesgo re-evaluado subió a C",
            }
        return {"accepted": True, "execution_id": "exec-test", "success": True}

    monkeypatch.setattr(cli, "prompt_confirmation", accept)
    monkeypatch.setattr(cli, "_json_rpc_call", fake_rpc)

    result = runner.invoke(app, ["confirm", pending_id, "--config", str(cfg)])

    assert result.exit_code == 0
    assert prompts == [RiskLevel.B, RiskLevel.C]
    assert [call["response"] for call in calls] == ["s", "CONFIRMAR"]


def test_digest_command_calls_rpc_and_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_config(tmp_path)
    calls: list[tuple[Path, str, dict[str, object]]] = []

    async def fake_rpc(socket_path: Path, method: str, params: dict[str, object]) -> dict[str, Any]:
        calls.append((socket_path, method, params))
        return {
            "markdown": "# Digest diario\n\n## Finanzas Pellegrini\nIngresos: $1.00\n",
            "generated_at": "2026-07-11T08:00:00-03:00",
        }

    monkeypatch.setattr(cli, "_json_rpc_call", fake_rpc)

    result = runner.invoke(app, ["digest", "--config", str(cfg)])

    assert result.exit_code == 0
    assert calls == [(tmp_path / "data" / "wyss.sock", "digest.today", {})]
    assert "Digest diario" in result.stdout
    assert "2026-07-11T08:00:00-03:00" in result.stdout


def test_digest_command_daemon_down_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_config(tmp_path)

    async def fake_rpc(socket_path: Path, method: str, params: dict[str, object]) -> dict[str, Any]:
        del socket_path, method, params
        raise FileNotFoundError

    monkeypatch.setattr(cli, "_json_rpc_call", fake_rpc)

    result = runner.invoke(app, ["digest", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "daemon no está corriendo" in result.stderr
    assert "wyss start" in result.stderr
    assert "Traceback" not in result.stderr


def _write_config(tmp_path: Path, *, digest_enabled: bool = False) -> Path:
    cfg = tmp_path / "config.toml"
    digest = "[digest]\nenabled = true\nhour = 7\nminute = 30\n" if digest_enabled else ""
    cfg.write_text(
        f"""\
data_dir = "{tmp_path / "data"}"
audit_db = "{tmp_path / "audit" / "audit.db"}"

{digest}
""",
        encoding="utf-8",
    )
    return cfg


def _patch_start_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    for klass in (
        _FakeAudit,
        _FakePendingStore,
        _FakeRoutineStore,
        _FakeMemoryStore,
        _FakeLedgerStore,
    ):
        klass.instances.clear()

    monkeypatch.setattr(cli, "SqliteAuditLogger", _FakeAudit)
    monkeypatch.setattr(cli, "PendingStore", _FakePendingStore)
    monkeypatch.setattr(cli, "RoutineStore", _FakeRoutineStore)
    monkeypatch.setattr(cli, "MemoryStore", _FakeMemoryStore)
    monkeypatch.setattr(cli, "SqliteLedgerStore", _FakeLedgerStore)
    monkeypatch.setattr(cli, "RoutineScheduler", _FakeScheduler)
