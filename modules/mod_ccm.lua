-- mod_ccm.lua (saved as mod_ccm.lua, loaded as "ccm")
-- Adds ClawCommander roster shell commands:
--   prosodyctl shell ccm add <operator_jid> <agent_jid> <display_name> <group>
--   prosodyctl shell ccm remove <operator_jid> <agent_jid>
--
-- Roster entries are written symmetrically (subscription = "both" on both sides)
-- so that Prosody routes presence in both directions without a subscription handshake.

local rm = require "core.rostermanager";
local jid_split = require "util.jid".split;

module:add_item("shell-command", {
    section = "ccm";
    section_desc = "ClawCommander agent management";
    name = "add";
    desc = "Add an agent to operator roster (and operator to agent roster): ccm add <operator_jid> <agent_jid> <display_name> <group>";
    args = {
        { name = "operator_jid";  type = "string" };
        { name = "agent_jid";     type = "string" };
        { name = "display_name";  type = "string" };
        { name = "group";         type = "string" };
    };
    host_selector = "operator_jid";
    handler = function(self, operator_jid, agent_jid, display_name, group)
        local op_user, op_host = jid_split(operator_jid);
        if not op_user or not op_host then
            return false, "Invalid operator JID: " .. tostring(operator_jid);
        end

        local agent_user, agent_host = jid_split(agent_jid);
        if not agent_user or not agent_host then
            return false, "Invalid agent JID: " .. tostring(agent_jid);
        end

        -- Write agent into operator's roster
        local op_roster = rm.load_roster(op_user, op_host);
        if not op_roster then
            return false, "Could not load roster for " .. operator_jid;
        end

        op_roster[agent_jid] = {
            subscription = "both";
            nick = display_name or agent_jid;
            groups = { [group or "Agents"] = true };
        };

        local ok, err = rm.save_roster(op_user, op_host, op_roster);
        if not ok then
            return false, "Failed to save operator roster: " .. tostring(err);
        end

        -- Write operator into agent's roster
        local agent_roster = rm.load_roster(agent_user, agent_host);
        if not agent_roster then
            return false, "Could not load roster for " .. agent_jid;
        end

        agent_roster[operator_jid] = {
            subscription = "both";
            nick = operator_jid;
            groups = { ["Operators"] = true };
        };

        local ok2, err2 = rm.save_roster(agent_user, agent_host, agent_roster);
        if not ok2 then
            return false, "Failed to save agent roster: " .. tostring(err2);
        end

        return true, "Added " .. agent_jid .. " to roster of " .. operator_jid
            .. " and " .. operator_jid .. " to roster of " .. agent_jid
            .. " (nick: " .. (display_name or agent_jid) .. ", group: " .. (group or "Agents") .. ")";
    end;
});

module:add_item("shell-command", {
    section = "ccm";
    section_desc = "ClawCommander agent management";
    name = "remove";
    desc = "Remove an agent from operator roster (and operator from agent roster): ccm remove <operator_jid> <agent_jid>";
    args = {
        { name = "operator_jid"; type = "string" };
        { name = "agent_jid";    type = "string" };
    };
    host_selector = "operator_jid";
    handler = function(self, operator_jid, agent_jid)
        local op_user, op_host = jid_split(operator_jid);
        if not op_user or not op_host then
            return false, "Invalid operator JID: " .. tostring(operator_jid);
        end

        local agent_user, agent_host = jid_split(agent_jid);
        if not agent_user or not agent_host then
            return false, "Invalid agent JID: " .. tostring(agent_jid);
        end

        -- Remove agent from operator's roster
        local op_roster = rm.load_roster(op_user, op_host);
        if not op_roster then
            return false, "Could not load roster for " .. operator_jid;
        end

        if not op_roster[agent_jid] then
            return false, agent_jid .. " not found in roster of " .. operator_jid;
        end

        op_roster[agent_jid] = nil;

        local ok, err = rm.save_roster(op_user, op_host, op_roster);
        if not ok then
            return false, "Failed to save operator roster: " .. tostring(err);
        end

        -- Remove operator from agent's roster
        local agent_roster = rm.load_roster(agent_user, agent_host);
        if agent_roster and agent_roster[operator_jid] then
            agent_roster[operator_jid] = nil;
            local ok2, err2 = rm.save_roster(agent_user, agent_host, agent_roster);
            if not ok2 then
                return false, "Removed from operator roster but failed to update agent roster: " .. tostring(err2);
            end
        end

        return true, "Removed " .. agent_jid .. " from roster of " .. operator_jid
            .. " and " .. operator_jid .. " from roster of " .. agent_jid;
    end;
});
