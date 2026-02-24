import slixmpp
import asyncio
import ssl
import logging
class AgentController(slixmpp.ClientXMPP):
    def __init__(self, jid, password, connection_dict, ready_event): # for the time being we are going to pass it right over
#        self.cfg = config              # eventually we are going to have the docker version so that'll have a conf package on spin up
        super().__init__(jid, password)
        self.ready_event = ready_event
        self.server = connection_dict["server"] ## "127.0.0.1"
        self.xmpp_port = connection_dict["port"] ## default? 5222)


        self.ssl_context = ssl.create_default_context()
        self['feature_mechanisms'].unencrypted_plain = False
        self['feature_mechanisms'].unencrypted_scram = False

        self.add_event_handler("session_start", self._on_session_start)
        self.add_event_handler("message", self._on_message)
        self.add_event_handler("disconnected", self._on_disconnected)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self.connect(self.server, self.xmpp_port)

    async def _on_session_start(self, event):
        self.send_presence(pstatus="Agent Zero online")
        await self.get_roster()
#        log.info(f"Agent zero connected as {self.boundjid}")
        print(f"Agent zero connected as {self.boundjid}")
        self.ready_event.set()

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

        response = "ECHO: " + msg["body"]
        msg.reply(response).send()


        sender = str(msg["from"].bare)
        if sender != self.operator_jid:
            log.warning(f"Ignored message from non-operator JID: {sender}")
            return

        body = msg["body"].strip()
        log.info(f"Command from operator: {body!r}")

        parts = body.split()
        if not parts:
            return

        cmd = parts[0].lower()
        args = parts[1:]

        response = await self._dispatch(cmd, args)
        msg.reply(response).send()
