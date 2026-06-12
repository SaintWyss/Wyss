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
