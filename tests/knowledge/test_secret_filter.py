"""Tests del filtro de secretos de 3 capas (KNOW-07)."""

import re

from knowledge.secret_filter import SecretFilter

_TEST_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
)


def _filter(*, entropy_allowlist: frozenset[str] = frozenset()) -> SecretFilter:
    return SecretFilter(
        builtin_patterns=_TEST_PATTERNS,
        entropy_allowlist=entropy_allowlist,
    )


def test_path_denylist_excludes_sensitive_names_without_content() -> None:
    secret_filter = _filter()

    assert secret_filter.check_path("/x/.env") == ("path_denylist", "path")
    assert secret_filter.check_path("/x/.env.local") == ("path_denylist", "path")
    assert secret_filter.check_path("/x/server.key") == ("path_denylist", "path")
    assert secret_filter.check_path("/x/server.pem") == ("path_denylist", "path")
    assert secret_filter.check_path("/x/id_rsa") == ("path_denylist", "path")
    assert secret_filter.check_path("/x/credentials") == ("path_denylist", "path")
    assert secret_filter.check_path("/x/notas.txt") is None


def test_builtin_pattern_is_detected_by_injected_patterns() -> None:
    secret_filter = _filter()

    result = secret_filter.check_content(
        "token=sk-ant-api03-FAKE_KEY_FOR_TEST_abc123def456",
        "/x/notas.txt",
    )

    assert result == ("anthropic_key", "builtin_pattern")


def test_high_entropy_base64_token_is_detected() -> None:
    secret_filter = _filter()

    result = secret_filter.check_content(
        "token=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
        "/x/notas.txt",
    )

    assert result == ("high_entropy", "entropy")


def test_high_entropy_hex_token_is_detected() -> None:
    secret_filter = _filter()

    result = secret_filter.check_content(
        "checksum=0123456789abcdef0123456789abcdef",
        "/x/notas.txt",
    )

    assert result == ("high_entropy", "entropy")


def test_normal_english_prose_is_not_detected() -> None:
    secret_filter = _filter()

    result = secret_filter.check_content(
        "This is ordinary prose with a longer conversational sentence and no hidden token.",
        "/x/notas.txt",
    )

    assert result is None


def test_entropy_allowlist_only_disables_layer3() -> None:
    secret_filter = _filter(entropy_allowlist=frozenset({"/x/fixtures/*"}))

    entropy_result = secret_filter.check_content(
        "token=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
        "/x/fixtures/example.txt",
    )
    builtin_result = secret_filter.check_content(
        "token=sk-ant-api03-FAKE_KEY_FOR_TEST_abc123def456",
        "/x/fixtures/example.txt",
    )

    assert entropy_result is None
    assert builtin_result == ("anthropic_key", "builtin_pattern")


def test_secret_value_never_in_return() -> None:
    secret_filter = _filter()
    raw_secret = "sk-ant-api03-FAKE_KEY_FOR_TEST_abc123def456"

    result = secret_filter.check_content(f"token={raw_secret}", "/x/notas.txt")

    assert result is not None
    assert all(raw_secret not in part for part in result)
