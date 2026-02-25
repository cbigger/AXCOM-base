"""
dockerctl.py - Docker wrapper for ClawCommander agent containers.
Handles all Docker operations via subprocess, mirroring the xmppctl pattern.
"""

import subprocess
import logging
import json

log = logging.getLogger(__name__)

CONTAINER_LABEL = "axmon-agent=agent"
DEFAULT_IMAGE_TAG = "axmon-agent:latest"


def _run(command, timeout=120):
    """
    Run a docker command via sudo. Returns (success, output) tuple.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log.debug(f"docker ok: {command!r} -> {result.stdout.strip()}")
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log.error(f"docker failed: {command!r} -> {e.stderr.strip()}")
        return False, e.stderr.strip()
    except subprocess.TimeoutExpired:
        log.error(f"docker timed out: {command!r}")
        return False, "Command timed out"


# ---------------------------------------------------------------------------
# Image management
# ---------------------------------------------------------------------------

def build_image(build_context, dockerfile_path, tag=DEFAULT_IMAGE_TAG):
    """Build the agent Docker image from the project root."""
    return _run(
        f"docker build -t {tag} -f {dockerfile_path} {build_context}",
        timeout=300,
    )


def image_exists(tag=DEFAULT_IMAGE_TAG):
    """Check if the agent image exists locally."""
    ok, out = _run(f"docker image inspect {tag}")
    return ok


# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------

def run_agent(container_name, env_vars, image_tag=DEFAULT_IMAGE_TAG,
              extra_hosts=None, volumes=None, network_mode=None):
    """
    Run a new agent container.

    Args:
        container_name: Name for the container (used as --name).
        env_vars: Dict of environment variables to pass.
        image_tag: Docker image to use.
        extra_hosts: List of "host:ip" entries for --add-host.
        volumes: List of "host_path:container_path" volume mounts.
        network_mode: Docker network mode (e.g. "host", "bridge").

    Returns:
        (success, container_id_or_error)
    """
    parts = ["docker run -d --restart unless-stopped"]
    parts.append(f"--name {container_name}")
    parts.append(f"--label {CONTAINER_LABEL}")
    parts.append(f"--label axcom-agent.jid={env_vars.get('AGENT_JID', '')}")

    if network_mode:
        parts.append(f"--network {network_mode}")

    for key, value in env_vars.items():
        parts.append(f'-e {key}="{value}"')

    if extra_hosts:
        for host_entry in extra_hosts:
            parts.append(f"--add-host={host_entry}")

    if volumes:
        for vol in volumes:
            parts.append(f"-v {vol}")

    parts.append(image_tag)
    cmd = " ".join(parts)
    return _run(cmd)


def stop_agent(container_name, timeout=10):
    """Stop a running agent container."""
    return _run(f"docker stop -t {timeout} {container_name}")


def remove_agent(container_name, force=False):
    """Remove an agent container."""
    flag = " -f" if force else ""
    return _run(f"docker rm{flag} {container_name}")


def stop_and_remove(container_name):
    """Stop and remove a container in one operation."""
    stop_agent(container_name)
    return remove_agent(container_name, force=True)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

def list_agents(all_states=False):
    """
    List agent containers.
    Returns (success, list_of_dicts) where each dict has:
        name, id, status, jid, image
    """
    flag = " -a" if all_states else ""
    fmt = '{"name":"{{.Names}}","id":"{{.ID}}","status":"{{.Status}}","image":"{{.Image}}"}'
    ok, out = _run(
        f'docker ps{flag} --filter "label={CONTAINER_LABEL}" --format \'{fmt}\''
    )
    if not ok:
        return False, out

    containers = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                info = json.loads(line)
                # Fetch JID label
                jid_ok, jid_out = _run(
                    f"docker inspect --format '{{{{index .Config.Labels \"axmon.jid\"}}}}' {info['name']}"
                )
                info["jid"] = jid_out if jid_ok else "unknown"
                containers.append(info)
            except json.JSONDecodeError:
                continue
    return True, containers


def logs(container_name, tail=50):
    """Get recent logs from an agent container."""
    return _run(f"docker logs --tail {tail} {container_name}")


def is_running(container_name):
    """Check if a specific container is running."""
    ok, out = _run(
        f"docker inspect --format '{{{{.State.Running}}}}' {container_name}"
    )
    return ok and out.strip().lower() == "true"


def container_exists(container_name):
    """Check if a container exists (any state)."""
    ok, _ = _run(f"docker inspect {container_name}")
    return ok
