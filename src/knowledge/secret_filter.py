"""Filtro puro de secretos para excluir archivos antes de indexarlos.

La detección corre en tres capas (D-29): nombre/extensión de archivo, patrones built-in
inyectados desde bootstrap, y tokens de alta entropía. Un match en cualquier capa excluye el
archivo entero; el valor del secreto nunca sale de este módulo.
"""

import fnmatch
import math
import re
from pathlib import PurePath
from typing import Final

type SecretMatch = tuple[str, str]

PATH_DENYLIST: Final[frozenset[str]] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
        "credentials",
    }
)
EXT_DENYLIST: Final[frozenset[str]] = frozenset({".key", ".pem", ".p12", ".pfx", ".ppk"})
FILENAME_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\.env(?:\.|$)"),
    re.compile(r"^id_rsa(?:$|\.)"),
    re.compile(r"^id_ed25519(?:$|\.)"),
)

BASE64_CHARS: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
HEX_CHARS: Final[str] = "0123456789abcdefABCDEF"
BASE64_THRESHOLD: Final[float] = 4.5
HEX_THRESHOLD: Final[float] = 3.0

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9+/=_\-]{20,}")


class SecretFilter:
    """Detector de secretos sin IO; todos los patrones externos llegan por inyección."""

    def __init__(
        self,
        *,
        builtin_patterns: tuple[tuple[str, re.Pattern[str]], ...],
        path_denylist: frozenset[str] = PATH_DENYLIST,
        ext_denylist: frozenset[str] = EXT_DENYLIST,
        filename_patterns: tuple[re.Pattern[str], ...] = FILENAME_PATTERNS,
        entropy_allowlist: frozenset[str] = frozenset(),
    ) -> None:
        self._builtin_patterns = builtin_patterns
        self._path_denylist = path_denylist
        self._ext_denylist = ext_denylist
        self._filename_patterns = filename_patterns
        self._entropy_allowlist = entropy_allowlist

    def check_path(self, path: str) -> SecretMatch | None:
        """Capa 1: detecta archivos sensibles por nombre/extensión sin abrirlos."""
        name = PurePath(path).name
        suffix = PurePath(path).suffix

        if name in self._path_denylist or suffix in self._ext_denylist:
            return ("path_denylist", "path")

        for pattern in self._filename_patterns:
            if pattern.search(name):
                return ("path_denylist", "path")

        return None

    def check_content(self, text: str, path: str) -> SecretMatch | None:
        """Capas 2 y 3: detecta patrones conocidos y tokens de alta entropía."""
        for name, pattern in self._builtin_patterns:
            if pattern.search(text):
                return (name, "builtin_pattern")

        if self._is_entropy_allowlisted(path):
            return None

        for token in _TOKEN_RE.findall(text):
            if _shannon_entropy(token, BASE64_CHARS) >= BASE64_THRESHOLD:
                return ("high_entropy", "entropy")
            if _shannon_entropy(token, HEX_CHARS) >= HEX_THRESHOLD:
                return ("high_entropy", "entropy")

        return None

    def _is_entropy_allowlisted(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self._entropy_allowlist)


def _shannon_entropy(data: str, charset: str) -> float:
    """Calcula entropía Shannon contra un charset de referencia."""
    if not data:
        return 0.0

    entropy = 0.0
    length = len(data)
    for char in charset:
        probability = data.count(char) / length
        if probability > 0:
            entropy -= probability * math.log2(probability)
    return entropy
