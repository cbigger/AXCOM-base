#!/usr/bin/env python3
"""
controller.py
"""

import asyncio
import logging
import tomllib
import secrets
import string
import re
import ssl
import multiprocessing
import slixmpp
from pathlib import Path
from dotenv import load_dotenv, set_key
import os
import argparse
import xmppctl
import dockerctl
from agent_controller import AgentController
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RECONNECT_DELAY = 10


def load_config(path="./config.toml"):
    with open(path, "rb") as f:
        return tomllib.load(f)

def load_password(path):
    load_dotenv(path)
    value = os.getenv("CONTROLLER_PASSWORD", None)
    return value

def generate_password(length=32):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def sanitize_name(name):
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def build_ssl_context(ca_certs):
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    for cert_path in ca_certs:
        ctx.load_verify_locations(cert_path)
        log.info(f"SSL: loaded cert {cert_path}")
    return ctx


# ---------------------------------------------------------------------------
# Agent subprocess entry point
# ---------------------------------------------------------------------------

def _run_agent(jid, password, connection_dict, ready_event):
    """
    Runs in a child process. Creates an AgentController, starts it,
    and runs the asyncio loop forever.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    agent = AgentController(jid, password, connection_dict, ready_event)
    agent.start()
    loop.run_forever()


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class Controller(slixmpp.ClientXMPP):
    def __init__(self, config):
        self.cfg = config
        orch = config["controller"]
        password = load_password(config["dotenv"]["dotenv_path"])
        super().__init__(orch["jid"], password)

        self.operator_jid = config["operator"]["jid"]
        self.vhosts = config["vhosts"]
        self.server = orch.get("server", "127.0.0.1")
        self.xmpp_port = orch.get("port", 5222)

        self.ssl_context = ssl.create_default_context()
        self['feature_mechanisms'].unencrypted_plain = False
        self['feature_mechanisms'].unencrypted_scram = False

        self.agent_processes = {}  # jid -> multiprocessing.Process

        # Docker state
        self.docker_cfg = config.get("docker", {})
        self.docker_containers = {}  # jid -> container_name
        self._docker_ready_events = {}  # jid -> asyncio.Event
        self._docker_llm_results = {}   # jid -> status string

        self.add_event_handler("session_start", self._on_session_start)
        self.add_event_handler("message", self._on_message)
        self.add_event_handler("disconnected", self._on_disconnected)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self.connect(self.server, self.xmpp_port)

    async def _on_session_start(self, event):
        self.send_presence(pstatus="AXMON controller online")
        await self.get_roster()
        log.info(f"controller connected as {self.boundjid}")

    async def _on_disconnected(self, event):
        log.warning(f"Disconnected from XMPP server. Reconnecting in {RECONNECT_DELAY}s...")
        await asyncio.sleep(RECONNECT_DELAY)
        self.connect(self.server, self.xmpp_port)

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _on_message(self, msg):
        if msg["type"] not in ("chat", "normal"):
            return

        sender = str(msg["from"].bare)
        body = msg["body"].strip()

        # Handle status reports from docker agents
        if body.startswith("AGENT_READY ") or body.startswith("LLM_STATUS "):
            self._handle_agent_status(sender, body)
            return

        if sender != self.operator_jid:
            log.warning(f"Ignored message from non-operator JID: {sender}")
            return

        log.info(f"Command from operator: {body!r}")

        parts = body.split()
        if not parts:
            return

        cmd = parts[0].lower()
        args = parts[1:]

        response = await self._dispatch(cmd, args)
        msg.reply(response).send()

    def _handle_agent_status(self, sender, body):
        """Process AGENT_READY and LLM_STATUS messages from docker agents."""
        parts = body.split(None, 2)
        msg_type = parts[0]

        if msg_type == "AGENT_READY":
            agent_jid = parts[1] if len(parts) > 1 else sender
            log.info(f"Docker agent ready: {agent_jid}")
            if agent_jid in self._docker_ready_events:
                self._docker_ready_events[agent_jid].set()
            # Forward to operator
            self.send_message(
                mto=self.operator_jid,
                mbody=f"[docker] Agent {agent_jid} XMPP connection confirmed.",
                mtype="chat",
            )

        elif msg_type == "LLM_STATUS":
            rest = body[len("LLM_STATUS "):]
            jid_and_status = rest.split(None, 1)
            agent_jid = jid_and_status[0] if jid_and_status else sender
            status = jid_and_status[1] if len(jid_and_status) > 1 else "UNKNOWN"
            log.info(f"Docker agent LLM status: {agent_jid} -> {status}")
            self._docker_llm_results[agent_jid] = status
            # Forward to operator
            self.send_message(
                mto=self.operator_jid,
                mbody=f"[docker] Agent {agent_jid} LLM status: {status}",
                mtype="chat",
            )

    async def _dispatch(self, cmd, args):
        if cmd == "help":
            return self._cmd_help()
        elif cmd == "spawn":
            return self._cmd_spawn(args)
        elif cmd == "spawn-test":
            return await self._cmd_spawn_test_agent()
        elif cmd == "kill":
            return self._cmd_kill(args)
        elif cmd == "list":
            return self._cmd_list()
        elif cmd == "status":
            return self._cmd_status()
        elif cmd == "docker-build":
            return await self._cmd_docker_build()
        elif cmd == "docker-spawn":
            return await self._cmd_docker_spawn(args)
        elif cmd == "docker-kill":
            return self._cmd_docker_kill(args)
        elif cmd == "docker-list":
            return self._cmd_docker_list()
        elif cmd == "docker-logs":
            return self._cmd_docker_logs(args)
        else:
            return f"Unknown command: {cmd!r}. Send 'help' for commands."

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _cmd_spawn_test_agent(self):
        jid = "test@localhost"
        password = "password"
        connection_dict = {"server": self.server, "port": self.xmpp_port}
        connection_timeout = 15  # seconds

        if jid in self.agent_processes:
            proc = self.agent_processes[jid]
            if proc.is_alive():
                return f"Agent {jid} is already running (pid {proc.pid})."
            else:
                log.info(f"Replacing dead process for {jid}.")

        ready_event = multiprocessing.Event()

        proc = multiprocessing.Process(
            target=_run_agent,
            args=(jid, password, connection_dict, ready_event),
            daemon=True,
            name=f"agent-{jid}",
        )
        proc.start()
        self.agent_processes[jid] = proc
        log.info(f"Spawned agent process for {jid} (pid {proc.pid})")

        loop = asyncio.get_event_loop()
        connected = await loop.run_in_executor(
            None, ready_event.wait, connection_timeout
        )

        if connected:
            log.info(f"Agent {jid} confirmed connected.")
            return f"Agent {jid} online (pid {proc.pid})."
        else:
            log.warning(f"Agent {jid} did not confirm connection within {connection_timeout}s.")
            return (
                f"Agent {jid} process started (pid {proc.pid}) "
                f"but connection was not confirmed within {connection_timeout}s. "
                "Check agent logs."
            )

    def _cmd_help(self):
        return (
            "AXCOM controller commands:\n"
            "\n"
            "  Process agents:\n"
            "    spawn <vhost_key> <name>  - Create agent (subprocess)\n"
            "    spawn-test                - Spawn hardcoded test agent\n"
            "    kill <jid>                - Delete an agent\n"
            "\n"
            "  Docker agents:\n"
            "    docker-build                    - Build agent container image\n"
            "    docker-spawn <vhost_key> <name> - Create agent (Docker container)\n"
            "    docker-kill <jid>               - Stop and remove container agent\n"
            "    docker-list                     - List running Docker agents\n"
            "    docker-logs <jid> [lines]       - View container logs\n"
            "\n"
            "  General:\n"
            "    list   - List all registered agents by vhost\n"
            "    status - Prosody server status\n"
            "    help   - This message\n"
            f"\nAvailable vhosts: {', '.join(self.vhosts.keys())}"
        )

    def _cmd_spawn(self, args):
        if len(args) < 2:
            return "Usage: spawn <vhost_key> <name>"

        vhost_key = args[0].lower()
        name = sanitize_name(args[1])

        if vhost_key not in self.vhosts:
            known = ", ".join(self.vhosts.keys())
            return f"Unknown vhost key: {vhost_key!r}. Known: {known}"

        domain = self.vhosts[vhost_key]
        jid = f"{name}@{domain}"
        display_name = f"{args[1]} [{vhost_key}]"
        password = generate_password()

        ok, out = xmppctl.register(name, domain, password)
        if not ok:
            return f"Failed to register {jid}:\n{out}"

        ok, out = xmppctl.roster_add(self.operator_jid, jid, display_name, vhost_key.capitalize())
        if not ok:
            log.warning(f"Roster add failed for {jid}: {out}")

        log.info(f"Spawned agent: {jid}")
        return (
            f"Agent created: {jid}\n"
            f"Password: {password}\n"
            f"Domain: {domain}\n"
            "Added to operator roster."
        )

    def _cmd_kill(self, args):
        if len(args) < 1:
            return "Usage: kill <jid>"

        jid = args[0]

        ok, out = xmppctl.deluser(jid)
        if not ok:
            return f"Failed to delete {jid}:\n{out}"

        ok, out = xmppctl.roster_remove(self.operator_jid, jid)
        if not ok:
            log.warning(f"Roster remove failed for {jid}: {out}")

        if jid in self.agent_processes:
            proc = self.agent_processes.pop(jid)
            if proc.is_alive():
                proc.terminate()
                log.info(f"Terminated process for {jid} (pid {proc.pid})")

        log.info(f"Killed agent: {jid}")
        return f"Agent {jid} deleted and removed from roster."

    def _cmd_list(self):
        lines = ["Registered agents:"]
        any_found = False
        for key, domain in self.vhosts.items():
            ok, out = xmppctl.user_list(domain)
            if ok and out:
                for line in out.splitlines():
                    line = line.strip()
                    if line:
                        lines.append(f"  {line}@{domain}  [{key}]")
                        any_found = True
        if not any_found:
            return "No agents registered."
        return "\n".join(lines)

    def _cmd_status(self):
        ok, out = xmppctl.status()
        return out if out else "No output from prosodyctl status."

    # ------------------------------------------------------------------
    # Docker commands
    # ------------------------------------------------------------------

    def _docker_image_tag(self):
        return self.docker_cfg.get("image_tag", dockerctl.DEFAULT_IMAGE_TAG)

    def _docker_build_context(self):
        return self.docker_cfg.get("build_context", "..")

    def _docker_dockerfile(self):
        return self.docker_cfg.get("dockerfile", "../agent/Dockerfile")

    def _docker_xmpp_host(self):
        return self.docker_cfg.get("xmpp_host", "host.docker.internal")

    def _docker_cert_dir(self):
        return self.docker_cfg.get("cert_dir", "/etc/prosody/certs")

    def _jid_to_container_name(self, jid):
        return "ccm-" + jid.replace("@", "-at-").replace(".", "-")

    async def _cmd_docker_build(self):
        """Build the agent container image."""
        tag = self._docker_image_tag()
        build_ctx = self._docker_build_context()
        dockerfile = self._docker_dockerfile()
        log.info(f"Building Docker image {tag} from {build_ctx}")

        loop = asyncio.get_event_loop()
        ok, out = await loop.run_in_executor(
            None, dockerctl.build_image, build_ctx, dockerfile, tag
        )
        if ok:
            return f"Image {tag} built successfully."
        else:
            return f"Image build failed:\n{out}"

    async def _cmd_docker_spawn(self, args):
        """Register an agent on Prosody and launch it in a Docker container."""
        if len(args) < 2:
            return "Usage: docker-spawn <vhost_key> <name>"

        vhost_key = args[0].lower()
        name = sanitize_name(args[1])

        if vhost_key not in self.vhosts:
            known = ", ".join(self.vhosts.keys())
            return f"Unknown vhost key: {vhost_key!r}. Known: {known}"

        domain = self.vhosts[vhost_key]
        jid = f"{name}@{domain}"
        display_name = f"{args[1]} [{vhost_key}]"
        password = generate_password()
        container_name = self._jid_to_container_name(jid)
        image_tag = self._docker_image_tag()

        # Ensure image exists
        if not dockerctl.image_exists(image_tag):
            log.info("Agent image not found, building...")
            build_result = await self._cmd_docker_build()
            if "failed" in build_result.lower():
                return f"Cannot spawn: {build_result}"

        # Check for existing container
        if dockerctl.container_exists(container_name):
            if dockerctl.is_running(container_name):
                return f"Container {container_name} is already running for {jid}."
            else:
                dockerctl.remove_agent(container_name, force=True)

        # Register on Prosody
        ok, out = xmppctl.register(name, domain, password)
        if not ok:
            return f"Failed to register {jid}:\n{out}"

        ok, out = xmppctl.roster_add(
            self.operator_jid, jid, display_name, vhost_key.capitalize()
        )
        if not ok:
            log.warning(f"Roster add failed for {jid}: {out}")

        # Load OpenRouter API key from environment
        load_dotenv(self.cfg["dotenv"]["dotenv_path"])
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

        # Build environment for container
        env_vars = {
            "AGENT_JID": jid,
            "AGENT_PASSWORD": password,
            "XMPP_SERVER": self._docker_xmpp_host(),
            "XMPP_PORT": str(self.xmpp_port),
            "CONTROLLER_JID": self.cfg["controller"]["jid"],
            "OPENROUTER_API_KEY": openrouter_key,
        }

        cert_dir = self._docker_cert_dir()
        network_mode = self.docker_cfg.get("network_mode", "host")
        volumes = [f"{cert_dir}:/certs:ro"]
        extra_hosts = None if network_mode == "host" else ["host.docker.internal:host-gateway"]

        # Set up readiness tracking
        ready_event = asyncio.Event()
        self._docker_ready_events[jid] = ready_event

        # Launch container
        loop = asyncio.get_event_loop()
        ok, out = await loop.run_in_executor(
            None,
            lambda: dockerctl.run_agent(
                container_name, env_vars, image_tag,
                extra_hosts, volumes, network_mode,
            ),
        )

        if not ok:
            self._docker_ready_events.pop(jid, None)
            return f"Failed to start container for {jid}:\n{out}"

        self.docker_containers[jid] = container_name
        log.info(f"Docker container {container_name} started for {jid}")

        # Wait for XMPP readiness confirmation
        connection_timeout = 30
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=connection_timeout)
            xmpp_status = "XMPP connected"
        except asyncio.TimeoutError:
            xmpp_status = f"XMPP connection not confirmed within {connection_timeout}s"
        finally:
            self._docker_ready_events.pop(jid, None)

        # Check for LLM result (may arrive shortly after AGENT_READY)
        await asyncio.sleep(5)
        llm_status = self._docker_llm_results.pop(jid, "pending")

        return (
            f"Docker agent created: {jid}\n"
            f"Container: {container_name}\n"
            f"Domain: {domain}\n"
            f"XMPP: {xmpp_status}\n"
            f"LLM: {llm_status}\n"
            "Added to operator roster."
        )

    def _cmd_docker_kill(self, args):
        """Stop and remove a Docker agent container, delete from Prosody."""
        if len(args) < 1:
            return "Usage: docker-kill <jid>"

        jid = args[0]
        container_name = self.docker_containers.get(jid)

        if not container_name:
            container_name = self._jid_to_container_name(jid)

        # Stop and remove container
        if dockerctl.container_exists(container_name):
            ok, out = dockerctl.stop_and_remove(container_name)
            if not ok:
                log.warning(f"Container removal issue for {container_name}: {out}")
        else:
            log.info(f"No container found for {jid}, cleaning up Prosody only.")

        # Delete from Prosody
        ok, out = xmppctl.deluser(jid)
        if not ok:
            return f"Container removed but failed to delete {jid} from Prosody:\n{out}"

        ok, out = xmppctl.roster_remove(self.operator_jid, jid)
        if not ok:
            log.warning(f"Roster remove failed for {jid}: {out}")

        self.docker_containers.pop(jid, None)
        self._docker_ready_events.pop(jid, None)
        self._docker_llm_results.pop(jid, None)

        log.info(f"Docker agent killed: {jid}")
        return f"Docker agent {jid} stopped, removed, and deleted from Prosody."

    def _cmd_docker_list(self):
        """List running Docker agent containers."""
        ok, containers = dockerctl.list_agents(all_states=True)
        if not ok:
            return f"Failed to list Docker agents:\n{containers}"

        if not containers:
            return "No Docker agent containers found."

        lines = ["Docker agent containers:"]
        for c in containers:
            lines.append(
                f"  {c['jid']}  [{c['status']}]  container={c['name']}"
            )
        return "\n".join(lines)

    def _cmd_docker_logs(self, args):
        """Get logs from a Docker agent container."""
        if len(args) < 1:
            return "Usage: docker-logs <jid> [lines]"

        jid = args[0]
        tail = int(args[1]) if len(args) > 1 else 50
        container_name = self.docker_containers.get(jid)

        if not container_name:
            container_name = self._jid_to_container_name(jid)

        ok, out = dockerctl.logs(container_name, tail=tail)
        if not ok:
            return f"Failed to get logs for {jid}:\n{out}"

        return f"Logs for {jid} ({container_name}):\n{out}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="AXCOM Controller")
    parser.add_argument(
        "--spawn-test",
        action="store_true",
        help="Spawn the test agent on startup without waiting for an XMPP command",
    )
    args = parser.parse_args()

    config = load_config("../config.toml")
    bot = Controller(config)

    if args.spawn_test:
        async def _startup_spawn_test(event):
            result = await bot._cmd_spawn_test_agent()
            log.info(f"spawn-test result: {result}")

        bot.add_event_handler("session_start", _startup_spawn_test)

    bot.start()
    asyncio.get_event_loop().run_forever()

    """
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config("../config.toml")

    bot = Controller(config)
    bot.start()

    asyncio.get_event_loop().run_forever()
"""
