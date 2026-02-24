"""
xmppctl.py - prosodyctl wrapper for ClawCommander
Handles all Prosody server interactions via subprocess.
"""

import subprocess
import logging

log = logging.getLogger(__name__)


def _run(command, input_data=None):
    """
    Run a prosodyctl command. Returns (success, output) tuple.
    input_data: optional string piped to stdin (for shell commands).
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            input=input_data,
        )
        log.debug(f"prosodyctl ok: {command!r} -> {result.stdout.strip()}")
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log.error(f"prosodyctl failed: {command!r} -> {e.stderr.strip()}")
        return False, e.stderr.strip()


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def register(username, domain, password):
    """Create a new Prosody user account."""
    return _run(f"sudo prosodyctl register {username} {domain} {password}")


def deluser(jid):
    """Delete a Prosody user account."""
    return _run(f"sudo prosodyctl deluser {jid}")


def passwd(jid, new_password):
    """Change password for an existing Prosody user."""
    return _run(f"sudo prosodyctl passwd {jid} {new_password}")


# ---------------------------------------------------------------------------
# Roster management (via prosodyctl shell)
# ---------------------------------------------------------------------------

def roster_add(operator_jid, agent_jid, display_name, group):
    """Add agent to operator's roster with nick and group via ccm shell command."""
    return _run(f'sudo prosodyctl shell ccm add {operator_jid} {agent_jid} "{display_name}" {group}')


def roster_remove(operator_jid, agent_jid):
    """Remove agent from operator's roster via ccm shell command."""
    return _run(f"sudo prosodyctl shell ccm remove {operator_jid} {agent_jid}")


def user_list(domain):
    """List all registered users on a domain."""
    return _run(f"sudo prosodyctl shell user list {domain}")


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

def start():
    return _run("sudo prosodyctl start")


def stop():
    return _run("sudo prosodyctl stop")


def restart():
    return _run("sudo prosodyctl restart")


def reload():
    """Reload config without full restart."""
    return _run("sudo prosodyctl reload")


def status():
    return _run("sudo prosodyctl status")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def about():
    return _run("sudo prosodyctl about")


def check(what, ping_server=None):
    """
    Run prosodyctl check. what = config|dns|certs|disabled|turn|connectivity
    """
    cmd = f"sudo prosodyctl check {what}"
    if what == "turn" and ping_server:
        cmd += f" --ping={ping_server}"
    return _run(cmd)


# ---------------------------------------------------------------------------
# Plugin management
# ---------------------------------------------------------------------------

def install_plugin(mod_name):
    return _run(f"sudo prosodyctl install {mod_name}")


def remove_plugin(mod_name):
    return _run(f"sudo prosodyctl remove {mod_name}")


def list_plugins():
    return _run("sudo prosodyctl list")
