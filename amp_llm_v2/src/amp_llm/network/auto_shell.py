"""
Auto shell detector and wrapper for SSH sessions.
Detects zsh/bash on remote and configures prompt + silent command mode.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class RemoteShellProfile:
    """Encapsulates detected shell type and prompt formatting."""

    def __init__(self, shell_path: str, prompt_fmt: str, silent_prefix: str):
        self.shell_path = shell_path
        self.prompt_fmt = prompt_fmt
        self.silent_prefix = silent_prefix


async def detect_remote_shell(ssh) -> RemoteShellProfile:
    """
    Detects whether the remote user shell is bash or zsh.
    Falls back to bash if detection fails.
    """
    try:
        result = await ssh.run(
            "echo $SHELL",
            check=False,
            term_type=None
        )

        shell_path = (result.stdout or "").strip()
        if not shell_path:
            shell_path = "/bin/bash"

        logger.info(f"Detected remote shell: {shell_path}")

        # macOS typically defaults to zsh now
        if "zsh" in shell_path:
            prompt_fmt = "{user}@{host} ~ % "
        else:
            prompt_fmt = "[{user}@{host} ~]$ "

        silent_prefix = 'bash -lc "{cmd}"'

        return RemoteShellProfile(shell_path, prompt_fmt, silent_prefix)

    except Exception as e:
        logger.error(f"Failed to detect remote shell: {e}")
        # fallback to bash
        return RemoteShellProfile(
            "/bin/bash",
            "[{user}@{host} ~]$ ",
            'bash -lc "stty -echo; {cmd}; stty echo"'
        )
