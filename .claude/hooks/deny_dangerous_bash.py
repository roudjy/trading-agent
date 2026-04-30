#!/usr/bin/env python3
"""PreToolUse Bash — deny destructive / deploy / SSH / config-read commands.

Patterns are intentionally conservative; over-blocking is acceptable in
auto mode because the cost of a wrong pass is much higher than the cost
of a wrong block.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook  # noqa: E402

DENY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Destructive Git ----------------------------------------------------
    (re.compile(r"\bgit\s+push\b.*--force(?:-with-lease)?\b"), "git_push_force"),
    (re.compile(r"\bgit\s+reset\b.*--hard\b"), "git_reset_hard"),
    (re.compile(r"\bgit\s+filter-(?:repo|branch)\b"), "git_filter_history"),
    (re.compile(r"\bgit\s+clean\b\s+-[fF]"), "git_clean_force"),
    (re.compile(r"\bgit\s+commit\b.*--no-verify\b"), "git_commit_no_verify"),
    (re.compile(r"\bgit\s+push\b.*--no-verify\b"), "git_push_no_verify"),
    (re.compile(r"\bgit\s+(?:branch|tag)\b.*-D\b"), "git_force_delete_ref"),

    # Destructive shell --------------------------------------------------
    # Note: `\b` after `/` would not match end-of-string (slash is non-word
    # and EOL is non-word, no boundary). Use an explicit alternation that
    # accepts a slash, end-of-string, or a word/path boundary.
    (re.compile(r"\brm\s+-rf?\s+(?:state|logs|research|config|/|\$|~)(?:\b|$|/)"), "rm_rf_protected"),
    (re.compile(r"\b:\(\)\{.*\};:"), "fork_bomb"),

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
    (re.compile(r"\b(?:cat|head|tail|less|more|nl|view|bat)\s+(?:[^|;]*)config/config\.yaml\b"), "read_config_yaml"),
    (re.compile(r"python\S*\s+.*open\s*\(\s*[\"']config/config\.yaml"), "py_open_config"),
    (re.compile(r"\b(?:cat|head|tail|less|more)\s+(?:[^|;]*)\.env(?:\.\S+)?\b"), "read_env"),
    (re.compile(r"\b(?:cat|head|tail|less|more)\s+(?:[^|;]*)state/[^/\s]*\.secret\b"), "read_state_secret"),

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
    # Strip leading "powershell -c '...'" wrappers — the dangerous pattern
    # is what runs, not the wrapper.
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
