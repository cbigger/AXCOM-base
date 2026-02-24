-- =============================================================================
-- vhosts/research.cfg.lua
-- Research agents domain.
-- Kill switch: set enabled = false and reload Prosody to block all traffic.
-- =============================================================================

VirtualHost "research.local"
    enabled = true
    modules_enabled = {
        "roster",
        "vcard",
        "private",
        "ping",
    }
