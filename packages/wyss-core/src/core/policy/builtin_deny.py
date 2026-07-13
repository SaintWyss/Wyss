"""Denylist built-in: reglas D NO removibles por config (regla #2 del owner).

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
        description="Write/delete bajo directorios de sistema (kernel, servicios, root).",
        action_type="file.*",
        target_patterns=(
            "/etc/**",
            "/boot/**",
            "/usr/**",
            "/sys/**",
            "/proc/**",
            "/var/lib/**",
            "/root/**",
        ),
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
        target_patterns=("mkfs*", "*/mkfs*", "*fdisk*", "*parted*", "*dd if=*"),
    ),
    DenyRule(
        id="shell-fetch-pipe-exec",
        description="shell.run que canaliza descarga a un intérprete (curl|bash, wget|sh...).",
        action_type="shell.run",
        arg_substrings=("| bash", "|bash", "| sh", "|sh", "| python", "|python", "| perl"),
    ),
    DenyRule(
        id="shell-privilege-escalation",
        description="shell.run que escala privilegios (sudo/su/doas/pkexec).",
        action_type="shell.run",
        target_patterns=(
            "sudo",
            "*/sudo",
            "su",
            "*/su",
            "doas",
            "*/doas",
            "pkexec",
            "*/pkexec",
        ),
    ),
    DenyRule(
        id="shell-rm-bypass",
        description=(
            "shell.run con rm/rmdir/shred como binario — el borrado va por file.delete "
            "(papelera + journal), nunca por shell irreversible."
        ),
        action_type="shell.run",
        target_patterns=("rm", "*/rm", "rmdir", "*/rmdir", "shred", "*/shred"),
    ),
    DenyRule(
        id="shell-recursive-delete",
        description="Borrado recursivo embebido en args de shell (rm -rf/-fr/-r ...).",
        action_type="shell.run",
        arg_substrings=("rm -rf", "rm -fr", "rm -r "),
    ),
    DenyRule(
        id="shell-perm-destructive",
        description="chmod/chown destructivo: world-writable (777), 000 o recursivo.",
        action_type="shell.run",
        arg_substrings=("chmod 777", "chmod -r", "chmod 000", "chown -r"),
    ),
    DenyRule(
        id="shell-firewall-tamper",
        description=(
            "Deshabilitar/vaciar el firewall (ufw disable, systemctl stop/disable/mask "
            "firewalld/nftables, iptables -F, nft flush). Los subcomandos de lectura "
            "(status) NO matchean: la regla es por verbo destructivo, no por binario."
        ),
        action_type="shell.run",
        arg_substrings=(
            "ufw disable",
            "stop firewalld",
            "disable firewalld",
            "mask firewalld",
            "stop nftables",
            "disable nftables",
            "iptables -f",
            "iptables --flush",
            "nft flush",
        ),
    ),
)
