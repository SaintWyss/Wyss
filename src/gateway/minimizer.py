"""ContextMinimizer fail-closed (GATE-03): el último checkpoint antes de la frontera de red.

`scan(prompt)` detecta secretos de TRES fuentes (D-21) y, ante cualquier match, levanta
`SecretDetected` — la llamada NO sale (fail-closed, D-20), nunca se redacta:

1. `env_values`: valores reales del `.env` cargados al boot (match por substring exacto).
   Es la red de alta precisión: bloquea la clave concreta del owner aunque su formato no
   esté entre los built-in. Se filtran a `len >= 8` para evitar falsos positivos de strings
   triviales (ej. un puerto o un flag corto que aparezca en cualquier prompt).
2. `BUILTIN_SECRET_PATTERNS`: regex de formatos conocidos (sk-ant-, AKIA, ghp_, JWT, PEM...).
3. `config_patterns`: patrones extra por config, AGREGADOS a los built-in (nunca los vacían).

Sigue el patrón de `CognitivePolicyEngine` (reglas inyectadas por constructor, clase pura sin
IO). El merge `BUILTIN_SECRET_PATTERNS + config_patterns` es espejo de `bootstrap/config.py`
(`deny = BUILTIN_DENY + config_deny`): aditivo, jamás sustractivo.
"""

import re

from core.domain.errors import SecretDetected
from gateway.secrets_patterns import BUILTIN_SECRET_PATTERNS

# Longitud mínima de un env_value para considerarlo secreto: descarta strings triviales
# (puertos, flags, palabras cortas) que generarían falsos positivos en prompts normales.
_MIN_ENV_VALUE_LEN: int = 8


class ContextMinimizer:
    """Pura: `scan(prompt) -> prompt` o `raise SecretDetected`. Patrones inyectados al construir."""

    def __init__(
        self,
        env_values: frozenset[str],
        config_patterns: tuple[tuple[str, re.Pattern[str]], ...],
    ) -> None:
        # Solo env_values no triviales (len>=8); evita matchear strings cortos legítimos.
        self._env_values: frozenset[str] = frozenset(
            v for v in env_values if len(v) >= _MIN_ENV_VALUE_LEN
        )
        # Aditivo: config AGREGA a los built-in, nunca los reemplaza ni los vacía (D-21).
        self._patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
            BUILTIN_SECRET_PATTERNS + config_patterns
        )

    def scan(self, prompt: str) -> str:
        """Devuelve `prompt` si está limpio; levanta `SecretDetected(pattern_name)` si no.

        Fail-closed (D-20): ante el primer match la llamada se aborta. El nombre del patrón
        (o `"env_value"`) es lo único que viaja a la excepción — el valor del secreto NUNCA.
        """
        for value in self._env_values:
            if value in prompt:
                raise SecretDetected("env_value")  # no nombra el valor (D-20)
        for name, pattern in self._patterns:
            if pattern.search(prompt):
                raise SecretDetected(name)
        return prompt
