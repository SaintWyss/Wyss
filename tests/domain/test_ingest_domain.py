"""Tests para los tipos de dominio de ingesta y las nuevas excepciones.

Ciclo TDD RED para Task 2 del plan 03-01.
"""

import pytest

# ── RED phase: estos imports fallan hasta que se implemente el código ──────────


def test_file_status_importable() -> None:
    """FileStatus es importable desde core.domain."""
    from core.domain import FileStatus  # noqa: F401


def test_file_status_has_all_states() -> None:
    """FileStatus tiene exactamente los 8 estados requeridos."""
    from core.domain import FileStatus

    assert FileStatus.pending.value == "pending"
    assert FileStatus.extracted.value == "extracted"
    assert FileStatus.embedded.value == "embedded"
    assert FileStatus.failed.value == "failed"
    assert FileStatus.excluded_secret.value == "excluded_secret"
    assert FileStatus.skipped_unsupported.value == "skipped_unsupported"
    assert FileStatus.skipped_symlink.value == "skipped_symlink"
    assert FileStatus.skipped_size.value == "skipped_size"

    # Exactamente 8 estados
    assert len(FileStatus) == 8


def test_ingest_settings_importable() -> None:
    """IngestSettings es importable desde core.domain."""
    from core.domain import IngestSettings  # noqa: F401


def test_ingest_settings_is_frozen() -> None:
    """IngestSettings es un frozen dataclass con tuplas (no listas)."""
    from core.domain import IngestSettings

    s = IngestSettings(
        chunk_size_tokens=512,
        chunk_overlap_tokens=51,
        max_file_bytes=104_857_600,
        dir_denylist=(".git", "node_modules"),
        entropy_allowlist=(),
        default_kb_id="default",
        max_attempts=3,
    )
    assert s.chunk_size_tokens == 512
    assert s.chunk_overlap_tokens == 51
    assert s.max_file_bytes == 104_857_600
    assert isinstance(s.dir_denylist, tuple)
    assert isinstance(s.entropy_allowlist, tuple)
    assert s.default_kb_id == "default"
    assert s.max_attempts == 3

    # Frozen: dataclasses frozen levantan FrozenInstanceError (subclase de AttributeError)
    with pytest.raises(AttributeError):
        s.chunk_size_tokens = 999  # type: ignore[misc]


def test_file_record_importable() -> None:
    """FileRecord es importable desde core.domain."""
    from core.domain import FileRecord  # noqa: F401


def test_file_record_fields() -> None:
    """FileRecord tiene los campos correctos."""
    from core.domain import FileRecord, FileStatus

    r = FileRecord(
        path="/tmp/test.txt",
        kb_id="default",
        size=100,
        mtime=1.0,
        sha256=None,
        status=FileStatus.pending,
        attempts=0,
        error=None,
    )
    assert r.path == "/tmp/test.txt"
    assert r.status == FileStatus.pending
    assert r.sha256 is None


def test_estimate_result_importable() -> None:
    """EstimateResult es importable desde core.domain."""
    from core.domain import EstimateResult  # noqa: F401


def test_estimate_result_fields() -> None:
    """EstimateResult tiene los campos requeridos."""
    from core.domain import EstimateResult

    e = EstimateResult(
        files=10,
        total_bytes=1024,
        projected_chunks=5,
        embed_time_s=0.01,
        cost_usd=0.0,
    )
    assert e.files == 10
    assert e.cost_usd == 0.0


def test_ingest_run_result_importable() -> None:
    """IngestRunResult es importable desde core.domain."""
    from core.domain import IngestRunResult  # noqa: F401


def test_ingest_run_result_fields() -> None:
    """IngestRunResult tiene los campos requeridos."""
    from core.domain import IngestRunResult

    r = IngestRunResult(
        indexed=5,
        failed=1,
        excluded_secret=2,
        skipped=3,
        run_id="run-001",
    )
    assert r.indexed == 5
    assert r.run_id == "run-001"


# ── Excepciones nuevas ─────────────────────────────────────────────────────────


def test_index_integrity_error_importable() -> None:
    """IndexIntegrityError es importable desde core.domain."""
    from core.domain import IndexIntegrityError  # noqa: F401


def test_index_integrity_error_is_wyss_error() -> None:
    """IndexIntegrityError hereda de WyssError."""
    from core.domain import IndexIntegrityError, WyssError

    err = IndexIntegrityError("fallo WAL")
    assert isinstance(err, WyssError)
    assert "fallo WAL" in str(err)


def test_extraction_error_importable() -> None:
    """ExtractionError es importable desde core.domain."""
    from core.domain import ExtractionError  # noqa: F401


def test_extraction_error_fields() -> None:
    """ExtractionError expone path y error_type sin traceback completo."""
    from core.domain import ExtractionError, WyssError

    err = ExtractionError("/tmp/bad.pdf", "corrupted")
    assert isinstance(err, WyssError)
    assert err.path == "/tmp/bad.pdf"
    assert err.error_type == "corrupted"
    # El mensaje menciona path y error_type
    assert "/tmp/bad.pdf" in str(err)
    assert "corrupted" in str(err)


def test_unsupported_file_error_importable() -> None:
    """UnsupportedFileError es importable desde core.domain."""
    from core.domain import UnsupportedFileError  # noqa: F401


def test_unsupported_file_error_fields() -> None:
    """UnsupportedFileError expone path."""
    from core.domain import UnsupportedFileError, WyssError

    err = UnsupportedFileError("/tmp/encrypted.pdf")
    assert isinstance(err, WyssError)
    assert err.path == "/tmp/encrypted.pdf"
    assert "/tmp/encrypted.pdf" in str(err)


def test_secret_file_excluded_importable() -> None:
    """SecretFileExcluded es importable desde core.domain."""
    from core.domain import SecretFileExcluded  # noqa: F401


def test_secret_file_excluded_fields() -> None:
    """SecretFileExcluded expone pattern_name y layer; el ctor NO acepta el contenido."""
    from core.domain import SecretFileExcluded, WyssError

    err = SecretFileExcluded("anthropic_key", "builtin_pattern")
    assert isinstance(err, WyssError)
    assert err.pattern_name == "anthropic_key"
    assert err.layer == "builtin_pattern"
    # El mensaje contiene el nombre del patrón y la capa
    assert "anthropic_key" in str(err)
    assert "builtin_pattern" in str(err)


def test_secret_file_excluded_ctor_has_no_content_param() -> None:
    """SecretFileExcluded solo acepta pattern_name y layer (D-20: nunca el secreto)."""
    import inspect

    from core.domain import SecretFileExcluded

    sig = inspect.signature(SecretFileExcluded)
    params = list(sig.parameters.keys())
    # Solo debe tener pattern_name y layer (más self implícito)
    assert "pattern_name" in params
    assert "layer" in params
    # No debe haber un parámetro para el contenido
    for forbidden in ("content", "secret", "value", "text", "file_content"):
        assert forbidden not in params
