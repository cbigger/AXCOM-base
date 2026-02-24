-- =============================================================================
-- vhosts/security.cfg.lua
-- Security agents domain.
-- Kill switch: set enabled = false and reload Prosody to block all traffic.
-- =============================================================================

VirtualHost "security.local"
    enabled = true
    modules_enabled = {
        "roster",
        "vcard",
        "private",
        "ping",
    }
