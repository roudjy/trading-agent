#!/usr/bin/env python3
"""PreToolUse Bash - deny destructive / deploy / SSH / config-read commands.

Revision 5 hardening:
  - python -c is denied outright (use scripts/ files or python -m).
  - Process substitution and command substitution to secret paths denied.
  - Find -exec on secret paths denied.
  - Conservative regex set; over-blocking is acceptable since legitimate
    operator work runs from the operator's own shell, not via Claude.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook

DENY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Destructive Git ----------------------------------------------------
    (re.compile(r"\bgit\s+push\b.*--force(?:-with-lease)?\b"), "git_push_force"),
    (re.compile(r"\bgit\s+reset\b.*--hard\b"), "git_reset_hard"),
    (re.compile(r"\bgit\s+filter-(?:repo|branch)\b"), "git_filter_history"),
    (re.compile(r"\bgit\s+clean\b\s+-[fF]"), "git_clean_force"),
    (re.compile(r"\bgit\s+commit\b.*--no-verify\b"), "git_commit_no_verify"),
    (re.compile(r"\bgit\s+push\b.*--no-verify\b"), "git_push_no_verify"),
    (re.compile(r"\bgit\s+(?:branch|tag)\b.*-D\b"), "git_force_delete_ref"),
    # R5.3: git rebase -i would let the agent rewrite history interactively.
    (re.compile(r"\bgit\s+rebase\s+(?:-i|--interactive)\b"), "git_rebase_interactive"),
    # R5.3: git config alterations could disable hooks.
    (re.compile(r"\bgit\s+config\b[^|;]*\bcore\.hooksPath\b"), "git_config_hooks_path"),

    # Destructive shell --------------------------------------------------
    # Note: \b after / would not match end-of-string (slash and EOL are
    # both non-word). Use explicit alternation.
    (re.compile(r"\brm\s+-rf?\s+(?:state|logs|research|config|/|\$|~)(?:\b|$|/)"), "rm_rf_protected"),
    (re.compile(r"\b:\(\)\{.*\};:"), "fork_bomb"),
    # R5.3: chmod / chown that could undo permissions on hooks.
    (re.compile(r"\bchmod\s+(?:[ugoa]*\+x|\d+)\s+\.claude/hooks"), "chmod_hooks"),

    # Deploy / production ------------------------------------------------
    (re.compile(r"docker\s+compose\s+-f\s+docker-compose\.prod\.yml\b"), "docker_compose_prod"),
    (re.compile(r"(?:^|\s)bash\s+scripts/deploy\.sh\b"), "deploy_script_bash"),
    (re.compile(r"(?:^|\s)\./scripts/deploy\.sh\b"), "deploy_script_direct"),
    (re.compile(r"(?:^|\s)sh\s+scripts/deploy\.sh\b"), "deploy_script_sh"),

    # SSH / remote access ------------------------------------------------
    (re.compile(r"\bssh\s+(?:-\S+\s+)*(?:[A-Za-z0-9._-]+@)?23\.88\.110\.92\b"), "ssh_to_vps"),
    (re.compile(r"\bssh\s+(?:-\S+\s+)*root@\S+"), "ssh_as_root"),
    (re.compile(r"\bscp\s+.*\s+[A-Za-z0-9._-]+@\S+"), "scp_remote"),
    (re.compile(r"\brsync\s+.*\s+[A-Za-z0-9._-]+@\S+"), "rsync_remote"),

    # Read of secrets via shell -----------------------------------------
    # The deny_config_read hook is the canonical layer; these are kept
    # for defense in depth and to give a clear message at the bash layer.
    (re.compile(r"\b(?:cat|head|tail|less|more|nl|view|bat)\s+(?:[^|;]*)config/conf[^|;\s]*\.ya?ml"), "read_config_yaml"),
    (re.compile(r"\b(?:cat|head|tail|less|more)\s+(?:[^|;]*)\.env(?:\.\S+)?\b"), "read_env"),
    (re.compile(r"\b(?:cat|head|tail|less|more)\s+(?:[^|;]*)state/[^/\s]*\.secret\b"), "read_state_secret"),
    # R5.1: secret-path reads via file-text tools (verb + secret).
    (re.compile(r"\b(?:awk|sed|gawk|tac|od|xxd|hexdump|strings|cut|nl)\b[^|;]*(?:config/conf[^|;\s>]*\.ya?ml|\.env(?:\.[^|;\s]+)?|state/[^/\s|;>]*\.secret|automation/[^/\s|;>]*\.secret)"), "file_tool_read_secret"),
    # R5.1: bash redirect-read of a secret path.
    (re.compile(r"(?<!<)<\s*(?:config/conf[^|;\s>]*\.ya?ml|\.env(?:\.[^|;\s]+)?|state/[^/\s|;>]*\.secret|automation/[^/\s|;>]*\.secret)"), "redirect_read_secret"),
    # R5.1: find command whose argument list contains a secret token.
    (re.compile(r"\bfind\b[^|;]*(?:config/conf[^|;\s>]*\.ya?ml|\.env(?:\.[^|;\s]+)?|state/[^/\s|;>]*\.secret|automation/[^/\s|;>]*\.secret)"), "find_with_secret"),

    # R5.3: python -c outright (chr/base64 obfuscation impossible to regex).
    (re.compile(r"\bpython[0-9.]*\s+-c\b"), "python_dash_c"),
    (re.compile(r"\bpython[0-9.]*\s+--command\b"), "python_command"),
    # python -m is fine (module run) - keep allowed.

    # R5.3: eval / base64 -d obfuscation is denied at the bash layer.
    (re.compile(r"\beval\b"), "eval_command"),
    (re.compile(r"\bbase64\s+(?:--decode|-d|-D)\b"), "base64_decode"),

    # Outbound network with payloads ------------------------------------
    # First-version: deny non-localhost curl/wget. Refine if legitimate need.
    (re.compile(r"\bcurl\s+(?!.*(?:127\.0\.0\.1|localhost|0\.0\.0\.0|--help|--version))[^|;]*https?://"), "curl_remote"),
    (re.compile(r"\bwget\s+(?!.*(?:127\.0\.0\.1|localhost|0\.0\.0\.0|--help|--version))[^|;]*https?://"), "wget_remote"),

    # GitHub Actions disable / settings.local.json edit ------------------
    (re.compile(r"\.claude/settings\.local\.json"), "edit_settings_local"),
)


def check(payload: dict[str, Any]) -> tuple[bool, str | None]:
    if payload.get("tool_name") != "Bash":
        return (True, None)
    cmd = (payload.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return (True, None)
    for pat, label in DENY_PATTERNS:
        if pat.search(cmd):
            return (
                False,
                f"dangerous_bash matched '{label}'. "
                "If this is legitimate operator work, run it from your own shell, "
                "not via Claude.",
            )
    return (True, None)


if __name__ == "__main__":
    sys.exit(
        run_pre_hook(
            name="deny_dangerous_bash",
            event_phase="PreToolUse",
            check=check,
        )
    )
