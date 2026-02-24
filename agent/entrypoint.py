#!/usr/bin/env python3
"""
entrypoint.py - Docker agent entrypoint for ClawCommander.

Reads configuration from environment variables, connects to the XMPP server,
confirms the connection, tests the OpenRouter LLM driver, and reports results
back to the controller via XMPP messages.

Environment variables:
    AGENT_JID          - Full JID for this agent (e.g. scout@research.local)
    AGENT_PASSWORD     - XMPP password
    XMPP_SERVER        - Prosody server address (default: host.docker.internal)
    XMPP_PORT          - Prosody c2s port (default: 5222)
    CONTROLLER_JID     - Controller JID to report status to
    OPENROUTER_API_KEY - OpenRouter API key for LLM access (optional)
    CERT_DIR           - Directory with CA certs inside container (default: /certs)
"""

import os
import sys
import asyncio
import logging
import ssl
import glob
import slixmpp

log = logging.getLogger("docker_agent")

AGENT_JID = os.environ.get("AGENT_JID")
AGENT_PASSWORD = os.environ.get("AGENT_PASSWORD")
XMPP_SERVER = os.environ.get("XMPP_SERVER", "host.docker.internal")
XMPP_PORT = int(os.environ.get("XMPP_PORT", "5222"))
CONTROLLER_JID = os.environ.get("CONTROLLER_JID", "controller@localhost")
CERT_DIR = os.environ.get("CERT_DIR", "/certs")

RECONNECT_DELAY = 10


class DockerAgent(slixmpp.ClientXMPP):
    """
    XMPP agent that runs inside a Docker container.
    On startup it confirms XMPP connectivity and tests the LLM driver,
    then falls back to echo mode for operator interaction.
    """

    def __init__(self):
        if not AGENT_JID or not AGENT_PASSWORD:
            log.error("AGENT_JID and AGENT_PASSWORD must be set.")
            sys.exit(1)

        super().__init__(AGENT_JID, AGENT_PASSWORD)
        self.xmpp_server = XMPP_SERVER
        self.xmpp_port = XMPP_PORT
        self.controller_jid = CONTROLLER_JID

        # Build SSL context: load all .crt files from the cert directory.
        # Hostname checking is disabled because Docker agents connect via
        # host.docker.internal while certs are issued for vhost domains
        # (e.g. research.local). The certs are self-signed for internal use.
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        certs_loaded = 0
        if os.path.isdir(CERT_DIR):
            for cert_file in sorted(glob.glob(os.path.join(CERT_DIR, "*.crt"))):
                try:
                    self.ssl_context.load_verify_locations(cert_file)
                    log.info(f"Loaded CA cert: {cert_file}")
                    certs_loaded += 1
                except ssl.SSLError as e:
                    log.warning(f"Could not load cert {cert_file}: {e}")
        if certs_loaded == 0:
            log.warning(f"No .crt files found in {CERT_DIR}, using system defaults")

        self['feature_mechanisms'].unencrypted_plain = False
        self['feature_mechanisms'].unencrypted_scram = False

        self.add_event_handler("session_start", self._on_session_start)
        self.add_event_handler("message", self._on_message)
        self.add_event_handler("disconnected", self._on_disconnected)

    def begin(self):
        self.connect(self.xmpp_server, self.xmpp_port)

    async def _on_session_start(self, event):
        self.send_presence(pstatus="Docker agent online")
        await self.get_roster()
        log.info(f"Docker agent connected as {self.boundjid}")

        self.send_message(
            mto=self.controller_jid,
            mbody=f"AGENT_READY {self.boundjid.bare}",
            mtype="chat",
        )

        await self._test_llm()

    async def _test_llm(self):
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            self.send_message(
                mto=self.controller_jid,
                mbody=f"LLM_STATUS {self.boundjid.bare} NO_API_KEY",
                mtype="chat",
            )
            log.warning("No OPENROUTER_API_KEY set, skipping LLM test.")
            return

        try:
            from openrouter_kdr import Interpreter

            loop = asyncio.get_event_loop()
            interp = Interpreter()
            result = await loop.run_in_executor(
                None,
                interp.create_chat,
                [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Reply with exactly one word: CONFIRMED"},
                ],
            )
            self.send_message(
                mto=self.controller_jid,
                mbody=f"LLM_STATUS {self.boundjid.bare} OK {result[:200]}",
                mtype="chat",
            )
            log.info(f"LLM test passed: {result[:100]}")
        except Exception as e:
            self.send_message(
                mto=self.controller_jid,
                mbody=f"LLM_STATUS {self.boundjid.bare} ERROR {str(e)[:200]}",
                mtype="chat",
            )
            log.error(f"LLM test failed: {e}")

    async def _on_message(self, msg):
        if msg["type"] not in ("chat", "normal"):
            return
        sender = str(msg["from"].bare)
        body = msg["body"].strip()
        log.info(f"Message from {sender}: {body!r}")
        msg.reply("ECHO: " + body).send()

    async def _on_disconnected(self, event):
        log.warning(f"Disconnected. Reconnecting in {RECONNECT_DELAY}s...")
        await asyncio.sleep(RECONNECT_DELAY)
        self.connect(self.xmpp_server, self.xmpp_port)


if __name__ == "__main__":
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    log.info(f"Starting Docker agent: JID={AGENT_JID} server={XMPP_SERVER}:{XMPP_PORT}")
    agent = DockerAgent()
    agent.begin()
    asyncio.get_event_loop().run_forever()
