-- =============================================================================
-- vhosts/admin.cfg.lua
-- Admin agents domain.
-- Kill switch: set enabled = false and reload Prosody to block all traffic.
-- =============================================================================

VirtualHost "admin.local"
    enabled = true
    modules_enabled = {
        "roster",
        "vcard",
        "private",
        "ping",
    }
