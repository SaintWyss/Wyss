"""Denylist built-in: 7 reglas D NO removibles por config (regla #2 del owner).

`BUILTIN_DENY` es `Final` — la config TOML solo puede AGREGAR reglas
(`PolicyRules.deny = BUILTIN_DENY + tuple(config_rules)`), nunca vaciar estas. Si la
config pudiera removerlas, el nivel D dejaría de ser absoluto editando un archivo
(violación de la garantía cognitiva). Por eso vive en código, como `Final`.

Cada regla usa `action_type`/`target_patterns` como patterns fnmatch y `params_equal`
como condición de igualdad sobre `Action.parameters`. El umbral agregado de borrado
masivo (> `delete_count_d`) lo evalúa el engine (`_matches_aggregate`), no estas reglas
por sí solas — `mass-delete` aquí captura el borrado recursivo fuera de papelera.

Solo stdlib (`typing.Final`) + `core.domain` — core sigue stdlib-only (import-linter).
"""

from typing import Final

from core.domain.policy import DenyRule

BUILTIN_DENY: Final[tuple[DenyRule, ...]] = (
    DenyRule(
        id="mass-delete",
        description="Borrado recursivo fuera de la papelera (o conteo agregado > umbral D).",
        action_type="file.delete",
        params_equal={"recursive": True, "to_trash": False},
    ),
    DenyRule(
        id="wyss-self-modify",
        description="Write/delete sobre el config/data dir del propio Wyss (regla #6).",
        action_type="file.*",
        target_patterns=("**/wyss/config/**", "**/wyss/data/**", "**/.config/wyss/**"),
    ),
    DenyRule(
        id="audit-tamper",
        description="Write/delete sobre el log de auditoría (data/audit.db*).",
        action_type="file.*",
        target_patterns=("**/audit.db", "**/audit.db-*", "**/data/audit.db*"),
    ),
    DenyRule(
        id="secret-exfiltration",
        description="Acceso a secretos (.env, *.key, id_rsa, ~/.ssh).",
        action_type="file.*",
        target_patterns=("**/.env*", "**/*.key", "**/id_rsa*", "**/.ssh/**"),
    ),
    DenyRule(
        id="system-files-write",
        description="Write/delete bajo /etc, /boot, /usr.",
        action_type="file.*",
        target_patterns=("/etc/**", "/boot/**", "/usr/**"),
    ),
    DenyRule(
        id="git-force-push-main",
        description="git push --force a main/master.",
        action_type="git.push",
        target_patterns=("main", "master"),
        params_equal={"force": True},
    ),
    DenyRule(
        id="disk-format",
        description="shell.run con comando destructivo de disco (mkfs/fdisk/parted/dd if=).",
        action_type="shell.run",
        target_patterns=("mkfs*", "*fdisk*", "*parted*", "*dd if=*"),
    ),
)
