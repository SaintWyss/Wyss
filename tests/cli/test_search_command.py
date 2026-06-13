"""Scaffolds de los comandos `wyss search` y `wyss status`."""

from pathlib import Path

import pytest


def _write_config(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    audit_db = tmp_path / "audit" / "audit.db"
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""\
data_dir = "{data_dir}"
audit_db = "{audit_db}"

[ingest]
chunk_size_tokens = 16
chunk_overlap_tokens = 1
""",
        encoding="utf-8",
    )
    return cfg


@pytest.mark.skip(reason="Wave 3: comandos search/status — plan 04-03")
def test_json_output() -> None:
    pass


@pytest.mark.skip(reason="Wave 3: comandos search/status — plan 04-03")
def test_rich_output() -> None:
    pass


@pytest.mark.skip(reason="Wave 3: comandos search/status — plan 04-03")
def test_status_command() -> None:
    pass
