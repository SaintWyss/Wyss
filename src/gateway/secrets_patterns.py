"""Patrones de secreto built-in: `Final`, NUNCA vaciables por config (D-21, regla #4/#8).

`BUILTIN_SECRET_PATTERNS` es `Final` — la config TOML solo puede AGREGAR patrones
(`self._patterns = BUILTIN_SECRET_PATTERNS + config_patterns`), nunca vaciar estos. Si la
config pudiera removerlos, la minimización de contexto dejaría de ser absoluta editando un
archivo (un secreto de formato conocido podría exfiltrarse a una API externa). Por eso vive
en código, como `Final`, espejo de `core.policy.builtin_deny.BUILTIN_DENY`.

Cada entrada es `(name, re.Pattern)`: el `name` es lo único que viaja a `SecretDetected`
cuando hay match — el valor del secreto JAMÁS entra a la excepción ni al audit (D-20).

Regex anclados por prefijo conocido (sk-ant-, AKIA, ghp_, ...) verificados contra
gitleaks/secrets-patterns-db (RESEARCH Pattern 2). El PEM se detecta por su header
multilínea explícito (Pitfall 3). Solo stdlib (`re`, `typing.Final`); este módulo vive en
`gateway/` (es regex de adapter/application), NUNCA en `core/`.
"""

import re
from typing import Final

BUILTIN_SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_access", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github_fine", re.compile(r"github_pat_[A-Za-z0-9_]{50,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("pem_private", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
)
