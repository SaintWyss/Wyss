"""Tests del ContextMinimizer fail-closed (GATE-03).

El minimizer es el último checkpoint antes de que un prompt cruce a la red: si un secreto
se filtró al payload, scan() lo DETECTA y levanta SecretDetected (la llamada NO sale, D-20).
Tres fuentes (D-21): env_values reales del .env + regex built-in + patrones extra por config.
"""

import re

import pytest

from core.domain.errors import SecretDetected
from gateway.minimizer import ContextMinimizer


def test_prompt_limpio_pasa_sin_bloqueo() -> None:
    """Un prompt sin secretos atraviesa scan() y vuelve idéntico (sin falso positivo)."""
    m = ContextMinimizer(env_values=frozenset(), config_patterns=())
    assert m.scan("hola mundo") == "hola mundo"


def test_secreto_de_formato_conocido_bloquea_con_su_nombre() -> None:
    """Un sk-ant- en el prompt levanta SecretDetected nombrando el patrón, no el valor."""
    m = ContextMinimizer(env_values=frozenset(), config_patterns=())
    with pytest.raises(SecretDetected) as exc_info:
        m.scan("usá esta key sk-ant-0123456789012345678901 para autenticar")
    assert exc_info.value.pattern_name == "anthropic_key"


def test_env_value_presente_bloquea_sin_filtrar_el_valor() -> None:
    """Un valor real del .env (len>=8) presente en el prompt bloquea como 'env_value'.

    D-20: ni pattern_name ni el mensaje de la excepción contienen el valor del secreto.
    """
    secreto = "mi-litellm-master-key-secreta"
    m = ContextMinimizer(env_values=frozenset({secreto}), config_patterns=())
    with pytest.raises(SecretDetected) as exc_info:
        m.scan(f"el master key es {secreto} no lo compartas")
    assert exc_info.value.pattern_name == "env_value"
    assert secreto not in str(exc_info.value)
    assert secreto not in exc_info.value.pattern_name


def test_notion_token_env_value_bloquea_por_substring() -> None:
    """NOTION-04: NOTION_TOKEN via env_values no puede viajar hacia un LLM."""
    notion_token = "secret_notion_token_de_test_1234567890"
    m = ContextMinimizer(env_values=frozenset({notion_token}), config_patterns=())
    with pytest.raises(SecretDetected) as exc_info:
        m.scan(f"consultar Notion con token {notion_token}")
    assert exc_info.value.pattern_name == "env_value"
    assert notion_token not in str(exc_info.value)


def test_config_patterns_agrega_no_reemplaza() -> None:
    """Un patrón extra por config bloquea su match — config AGREGA a los built-ins (D-21)."""
    custom = (("custom_wyss", re.compile(r"WYSS-[0-9]{6}")),)
    m = ContextMinimizer(env_values=frozenset(), config_patterns=custom)
    with pytest.raises(SecretDetected) as exc_info:
        m.scan("el ticket interno es WYSS-123456 confidencial")
    assert exc_info.value.pattern_name == "custom_wyss"


def test_env_value_trivial_corto_no_bloquea() -> None:
    """Un env_value de len<8 se descarta: evita falsos positivos de strings triviales."""
    m = ContextMinimizer(env_values=frozenset({"abc"}), config_patterns=())
    assert m.scan("abc es parte de abcdef y un commit abc123") == (
        "abc es parte de abcdef y un commit abc123"
    )


# --- Suite de seguridad: fixture "secreto trampa" multi-formato (GATE-03, criterion 2) ----
#
# Cada caso es (id_legible, env_value_plantado_o_None, secreto_trampa, pattern_name_esperado).
# Cubre TODOS los formatos del criterio 2 del ROADMAP: env-value + sk-ant- + sk- + AKIA +
# ghp_ + JWT + PEM private key multilínea. El secreto se embebe en texto legítimo y scan()
# DEBE bloquear: el fixture trampa nunca aparece en un payload saliente.

_PEM_TRAP = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEpAIBAAKCAQEA0123456789abcdefghijklmnopqrstuvwxyz\n"
    "-----END RSA PRIVATE KEY-----"
)

_ENV_TRAP = "mi-litellm-master-key-ultra-secreta"

_TRAP_CASES: tuple[tuple[str, str | None, str, str], ...] = (
    ("env_value", _ENV_TRAP, _ENV_TRAP, "env_value"),
    ("anthropic", None, "sk-ant-api03-0123456789abcdefghij", "anthropic_key"),
    ("openai_legacy", None, "sk-0123456789abcdefghijklmnop", "openai_key"),
    # Shape REAL de las keys modernas de OpenAI: sk-proj- CON guión tras "proj" (CR-01).
    # El patrón legacy (sk- + 20 alfanuméricos) NO la cubre; openai_proj sí debe bloquearla.
    ("openai_proj", None, "sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12", "openai_proj"),
    # Google API key shape real: AIza + 35 chars (CR-01) — antes egresaba sin bloqueo.
    ("google", None, "AIzaSyA1234567890abcdefghijklmnopqrstuv", "google_api"),
    ("aws", None, "AKIA0123456789ABCDEF", "aws_access"),
    ("github", None, "ghp_0123456789abcdefghij0123456789abcdef", "github_pat"),
    ("jwt", None, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.abc-DEF_123", "jwt"),
    ("pem", None, _PEM_TRAP, "pem_private"),
)


@pytest.mark.parametrize("trap", _TRAP_CASES, ids=lambda c: c[0])
def test_cada_formato_trampa_es_bloqueado(trap: tuple[str, str | None, str, str]) -> None:
    """Para cada formato trampa, scan() de un prompt que lo embebe levanta SecretDetected."""
    _id, env_value, secreto, esperado = trap
    env = frozenset({env_value}) if env_value is not None else frozenset()
    m = ContextMinimizer(env_values=env, config_patterns=())
    prompt = f"contexto legítimo previo. dato: {secreto}. texto posterior normal."
    with pytest.raises(SecretDetected) as exc_info:
        m.scan(prompt)
    assert exc_info.value.pattern_name == esperado


@pytest.mark.parametrize("trap", _TRAP_CASES, ids=lambda c: c[0])
def test_el_secreto_nunca_aparece_en_la_excepcion(trap: tuple[str, str | None, str, str]) -> None:
    """D-20: ni pattern_name ni str(exc) contienen el valor del secreto — no se loguea."""
    _id, env_value, secreto, _esperado = trap
    env = frozenset({env_value}) if env_value is not None else frozenset()
    m = ContextMinimizer(env_values=env, config_patterns=())
    with pytest.raises(SecretDetected) as exc_info:
        m.scan(f"el secreto plantado es {secreto} y no debe filtrarse")
    assert secreto not in str(exc_info.value)
    assert secreto not in exc_info.value.pattern_name


def test_no_falso_positivo_en_prompt_realista() -> None:
    """Un prompt con hashes/IDs/base64 cortos legítimos NO levanta SecretDetected."""
    m = ContextMinimizer(env_values=frozenset(), config_patterns=())
    prompt = (
        "el commit abc123 cierra el issue #42; la versión es 1.2.3 y el "
        "hash corto es deadbeef. revisar PR-789 antes del deploy."
    )
    assert m.scan(prompt) == prompt


def test_builtins_no_vaciables_por_config() -> None:
    """Con config_patterns vacío los built-in siguen activos: config no puede desactivarlos."""
    m = ContextMinimizer(env_values=frozenset(), config_patterns=())
    with pytest.raises(SecretDetected) as exc_info:
        m.scan("la key es sk-ant-api03-0123456789abcdefghij ahora")
    assert exc_info.value.pattern_name == "anthropic_key"
