#!/usr/bin/env python3
"""
claw.py - ClawCommander CLI
Direct command-line interface to the orchestrator functions.
Mirrors the XMPP bot command surface exactly.

Usage:
  claw.py spawn <vhost_key> <name>
  claw.py kill <jid>
  claw.py list
  claw.py status
  claw.py help




from dotenv import set_key

# Define the path to your .env file
dotenv_path = ".env"

# Set a new key-value pair or update an existing one
set_key(dotenv_path, "DATABASE_URL", "postgres://user:password@localhost/db")
set_key(dotenv_path, "API_KEY", "new_secret_token")

print("Variables written to .env")

"""

import sys
import argparse
import tomllib
import secrets
import string
import re
from dotenv import set_key, load_dotenv
import os
import xmppctl
import dockerctl


def load_config(path="config.toml"):
    with open(path, "rb") as f:
        return tomllib.load(f)

def load_password(key, path="../.env"):
    load_dotenv(path)
    value = os.getenv(key, None)
    return value

def generate_password(length=32):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def sanitize_name(name):
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(config, args):
    dotenv_path = config["dotenv"]["dotenv_path"]
  # Setup the operator account
    oname = "operator"
    odomain = "localhost"
    ojid = f"{oname}@{odomain}"
    odisplay_name = oname

    opassword = load_password("OPERATOR_PASSWORD", path=dotenv_path)
    if opassword == None:
        print("No password found in .env. Generating new password for operator...")
        opassword = generate_password()
        print("Saving operator password to environment file...")
        set_key(dotenv_path, "OPERATOR_PASSWORD", opassword)
        print("New password for operator saved.")

    print(f"Registering {ojid} ...")
    ok, out = xmppctl.register(oname, odomain, opassword)
    if not ok:
        print(f"Failed to register {ojid}:\n{out}")
        sys.exit(1)

    print("operator created and registered!")


  # Setup the orchestrator account
    cname = "controller"
    cdomain = "localhost"
    cjid = f"{cname}@{cdomain}"
    cdisplay_name = cname

    cpassword = load_password("CONTROLLER_PASSWORD", dotenv_path)
    if cpassword == None:
        print("No existing controller password found. Generating new password for controller...")
        cpassword = generate_password()
        print("Saving controller password to environment file...")
        set_key(dotenv_path, "CONTROLLER_PASSWORD", cpassword)
        print("New password for controller has been saved.")


    print(f"Registering {cjid} ...")
    ok, out = xmppctl.register(cname, cdomain, cpassword)
    if not ok:
        print(f"Failed to register {cjid}:\n{out}")
        sys.exit(1)
    print("controller created and registered!")

  # And finally handle the roster registration
    print(f"Adding {cjid} to operator's roster ...")
    ok, out = xmppctl.roster_add(
        ojid,
        cjid,
        cdisplay_name,
        "localhost",        #vhost_key.capitalize(),
    )
    if not ok:
        print(f"Warning: roster add failed:\n{out}")


    print("Operator and Controller init OK")



def cmd_spawn(cfg, args):
    vhost_key = args.vhost_key.lower()
    vhosts = cfg["vhosts"]

    if vhost_key not in vhosts:
        print(f"Unknown vhost key: {vhost_key!r}. Known: {', '.join(vhosts.keys())}")
        sys.exit(1)

    name = sanitize_name(args.name)
    domain = vhosts[vhost_key]
    jid = f"{name}@{domain}"
    display_name = f"{args.name} [{vhost_key}]"
    password = generate_password()

    print(f"Registering {jid} ...")
    ok, out = xmppctl.register(name, domain, password)
    if not ok:
        print(f"Failed to register {jid}:\n{out}")
        sys.exit(1)

    print(f"Adding {jid} to operator roster ...")
    ok, out = xmppctl.roster_add(
        cfg["operator"]["jid"],
        jid,
        display_name,
        vhost_key.capitalize(),
    )
    if not ok:
        print(f"Warning: roster add failed:\n{out}")

    print(f"\nAgent created: {jid}")
    print(f"Password:      {password}")
    print(f"Domain:        {domain}")


def cmd_kill(cfg, args):
    jid = args.jid
    print(f"Deleting {jid} ...")
    ok, out = xmppctl.deluser(jid)
    if not ok:
        print(f"Failed to delete {jid}:\n{out}")
        sys.exit(1)

    print(f"Removing {jid} from operator roster ...")
    ok, out = xmppctl.roster_remove(cfg["operator"]["jid"], jid)
    if not ok:
        print(f"Warning: roster remove failed:\n{out}")

    print(f"Agent {jid} deleted.")


def cmd_list(cfg, args):
    vhosts = cfg["vhosts"]
    any_found = False
    for key, domain in vhosts.items():
        ok, out = xmppctl.user_list(domain)
        if ok and out:
            for line in out.splitlines():
                line = line.strip()
                if line:
                    print(f"  {line}@{domain}  [{key}]")
                    any_found = True
    if not any_found:
        print("No agents registered.")


def cmd_status(cfg, args):
    ok, out = xmppctl.status()
    print(out)


def cmd_help(cfg, args):
    vhosts = ", ".join(cfg["vhosts"].keys())
    print(
        "ClawCommander CLI\n"
        "\n"
        "Process agents:\n"
        "  spawn <vhost_key> <name>  - Create and register a new agent\n"
        "  kill <jid>                - Delete an agent\n"
        "\n"
        "Docker agents:\n"
        "  docker-build                    - Build agent container image\n"
        "  docker-spawn <vhost_key> <name> - Create agent in Docker container\n"
        "  docker-kill <jid>               - Stop and remove container agent\n"
        "  docker-list                     - List Docker agent containers\n"
        "  docker-logs <jid> [lines]       - View container logs\n"
        "\n"
        "General:\n"
        "  list   - List all registered agents by vhost\n"
        "  status - Prosody server status\n"
        "  init   - Initialize operator and controller accounts\n"
        "  help   - This message\n"
        f"\nAvailable vhosts: {vhosts}"
    )


# ---------------------------------------------------------------------------
# Docker commands
# ---------------------------------------------------------------------------

def _jid_to_container_name(jid):
    return "ccm-" + jid.replace("@", "-at-").replace(".", "-")


def cmd_docker_build(cfg, args):
    docker_cfg = cfg.get("docker", {})
    build_ctx = docker_cfg.get("build_context", "..")
    dockerfile = docker_cfg.get("dockerfile", "../agent/Dockerfile")
    tag = docker_cfg.get("image_tag", dockerctl.DEFAULT_IMAGE_TAG)

    print(f"Building image {tag} ...")
    ok, out = dockerctl.build_image(build_ctx, dockerfile, tag)
    if ok:
        print(f"Image {tag} built successfully.")
    else:
        print(f"Build failed:\n{out}")
        sys.exit(1)


def cmd_docker_spawn(cfg, args):
    docker_cfg = cfg.get("docker", {})
    tag = docker_cfg.get("image_tag", dockerctl.DEFAULT_IMAGE_TAG)
    xmpp_host = docker_cfg.get("xmpp_host", "host.docker.internal")
    cert_dir = docker_cfg.get("cert_dir", "/etc/prosody/certs")
    vhosts = cfg["vhosts"]

    vhost_key = args.vhost_key.lower()
    if vhost_key not in vhosts:
        print(f"Unknown vhost key: {vhost_key!r}. Known: {', '.join(vhosts.keys())}")
        sys.exit(1)

    name = sanitize_name(args.name)
    domain = vhosts[vhost_key]
    jid = f"{name}@{domain}"
    display_name = f"{args.name} [{vhost_key}]"
    password = generate_password()
    container_name = _jid_to_container_name(jid)

    # Ensure image exists
    if not dockerctl.image_exists(tag):
        print(f"Image {tag} not found. Building...")
        ok, out = dockerctl.build_image(
            docker_cfg.get("build_context", ".."),
            docker_cfg.get("dockerfile", "../agent/Dockerfile"),
            tag,
        )
        if not ok:
            print(f"Image build failed:\n{out}")
            sys.exit(1)

    # Clean up existing container if stopped
    if dockerctl.container_exists(container_name):
        if dockerctl.is_running(container_name):
            print(f"Container {container_name} is already running for {jid}.")
            return
        else:
            dockerctl.remove_agent(container_name, force=True)

    # Register on Prosody
    print(f"Registering {jid} ...")
    ok, out = xmppctl.register(name, domain, password)
    if not ok:
        print(f"Failed to register {jid}:\n{out}")
        sys.exit(1)

    print(f"Adding {jid} to operator roster ...")
    ok, out = xmppctl.roster_add(
        cfg["operator"]["jid"], jid, display_name, vhost_key.capitalize()
    )
    if not ok:
        print(f"Warning: roster add failed:\n{out}")

    # Load OpenRouter key
    dotenv_path = cfg["dotenv"]["dotenv_path"]
    load_dotenv(dotenv_path)
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    # Build env vars for container
    env_vars = {
        "AGENT_JID": jid,
        "AGENT_PASSWORD": password,
        "XMPP_SERVER": xmpp_host,
        "XMPP_PORT": str(cfg["controller"].get("port", 5222)),
        "CONTROLLER_JID": cfg["controller"]["jid"],
        "OPENROUTER_API_KEY": openrouter_key,
    }

    network_mode = docker_cfg.get("network_mode", "host")
    volumes = [f"{cert_dir}:/certs:ro"]
    extra_hosts = None if network_mode == "host" else ["host.docker.internal:host-gateway"]

    # Launch container
    print(f"Starting container {container_name} ...")
    ok, out = dockerctl.run_agent(container_name, env_vars, tag, extra_hosts, volumes, network_mode)
    if not ok:
        print(f"Failed to start container:\n{out}")
        sys.exit(1)

    print(f"\nDocker agent created: {jid}")
    print(f"Container: {container_name}")
    print(f"Container ID: {out[:12]}")
    print(f"Domain: {domain}")
    print(f"\nCheck status with: docker-logs {jid}")


def cmd_docker_kill(cfg, args):
    jid = args.jid
    container_name = _jid_to_container_name(jid)

    if dockerctl.container_exists(container_name):
        print(f"Stopping and removing container {container_name} ...")
        ok, out = dockerctl.stop_and_remove(container_name)
        if not ok:
            print(f"Warning: container removal issue: {out}")
    else:
        print(f"No container found for {jid}.")

    print(f"Deleting {jid} from Prosody ...")
    ok, out = xmppctl.deluser(jid)
    if not ok:
        print(f"Failed to delete {jid}:\n{out}")
        sys.exit(1)

    print(f"Removing {jid} from operator roster ...")
    ok, out = xmppctl.roster_remove(cfg["operator"]["jid"], jid)
    if not ok:
        print(f"Warning: roster remove failed:\n{out}")

    print(f"Docker agent {jid} killed.")


def cmd_docker_list(cfg, args):
    ok, containers = dockerctl.list_agents(all_states=True)
    if not ok:
        print(f"Failed to list containers:\n{containers}")
        sys.exit(1)

    if not containers:
        print("No Docker agent containers found.")
        return

    print("Docker agent containers:")
    for c in containers:
        print(f"  {c['jid']}  [{c['status']}]  container={c['name']}")


def cmd_docker_logs(cfg, args):
    jid = args.jid
    tail = int(args.lines) if hasattr(args, 'lines') and args.lines else 50
    container_name = _jid_to_container_name(jid)

    ok, out = dockerctl.logs(container_name, tail=tail)
    if not ok:
        print(f"Failed to get logs:\n{out}")
        sys.exit(1)

    print(f"Logs for {jid} ({container_name}):")
    print(out)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="clicontroller",
        description="ClawCommander CLI - agent lifecycle management",
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command")

    sp = sub.add_parser("spawn", help="Create and register a new agent")
    sp.add_argument("vhost_key", help="Vhost category key (e.g. research, security)")
    sp.add_argument("name", help="Agent name")

    kp = sub.add_parser("kill", help="Delete an agent")
    kp.add_argument("jid", help="Full JID of agent to delete (e.g. myagent@research.local)")

    sub.add_parser("list", help="List all registered agents by vhost")
    sub.add_parser("status", help="Prosody server status")
    sub.add_parser("help", help="Show this help")
    sub.add_parser("init", help="Creates controller and operator accounts. Used by install.sh")

    # Docker commands
    sub.add_parser("docker-build", help="Build the agent Docker image")

    ds = sub.add_parser("docker-spawn", help="Create agent in a Docker container")
    ds.add_argument("vhost_key", help="Vhost category key (e.g. research, security)")
    ds.add_argument("name", help="Agent name")

    dk = sub.add_parser("docker-kill", help="Stop and remove a Docker agent")
    dk.add_argument("jid", help="Full JID of agent to kill")

    sub.add_parser("docker-list", help="List Docker agent containers")

    dl = sub.add_parser("docker-logs", help="View Docker agent container logs")
    dl.add_argument("jid", help="Full JID of agent")
    dl.add_argument("lines", nargs="?", default="50", help="Number of log lines (default: 50)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command or args.command == "help":
        cfg = load_config("../config.toml")
        cmd_help(cfg, args)
        return

    cfg = load_config(path="../config.toml")

    dispatch = {
        "spawn": cmd_spawn,
        "kill": cmd_kill,
        "list": cmd_list,
        "status": cmd_status,
        "help": cmd_help,
        "init": cmd_init,
        "docker-build": cmd_docker_build,
        "docker-spawn": cmd_docker_spawn,
        "docker-kill": cmd_docker_kill,
        "docker-list": cmd_docker_list,
        "docker-logs": cmd_docker_logs,
    }

    dispatch[args.command](cfg, args)


if __name__ == "__main__":
    main()
