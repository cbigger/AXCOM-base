# ClawCommander - Setup Notes



Okay so install goes like this:

Prosody is fresh install.
We have a 'vhosts' directory which is already set up with vhost config files


Install script (this will be the systemd install file eventually and run under the prosody user)
we start from the install directory ./installation

// We create the vhosts dir
mkdir /etc/prosody/vhosts

// we move our preconfigured cfg and vhost cfgs there
cp prosody/prosody.cfg.lua
cp prosody/vhosts/*.cfg.lua /etc/prosody/vhosts/

// we double check to make sure that we have a certs dir
mkdir /etc/prosody/certs

// we generate our certs for each domain (not sure how to automate past the defaults, no manual entry needed though
prosodyctl cert generate localhost
prosodyctl cert generate research.local
prosodyctl cert generate security.local
prosodyctl cert generate admin.local

// we move the certs to the right spot because they put them in a weird one
cp /var/lib/prosody/*.crt /etc/prosody/certs/
cp /var/lib/prosody/*.key /etc/prosody/certs/


// we fix the permission issues, setting world readable on the crts and directory (might need to make them owned by prosody too?)
chmod o+x /etc/prosody/certs/
chmod o+r /etc/prosody/certs/*.crt









// we use the cli tools to setup the initial users properly






















-------------------------------------___-





## /etc/hosts

Add to `/etc/hosts` on the server (operator machine):

```
127.0.0.1   localhost
127.0.0.1   research.local
127.0.0.1   security.local
127.0.0.1   admin.local
```

## Prosody

### Install

```bash
sudo apt install prosody
```

### Config

```bash
sudo cp prosody/prosody.cfg.lua /etc/prosody/prosody.cfg.lua
sudo mkdir -p /etc/prosody/vhosts
sudo cp prosody/vhosts/*.cfg.lua /etc/prosody/vhosts/
```

### Certs (self-signed, one per vhost)

Generate in this order — localhost first, so the running daemon stops complaining
about the missing key on subsequent commands:

```bash
sudo prosodyctl cert generate localhost
sudo prosodyctl cert generate research.local
sudo prosodyctl cert generate security.local
sudo prosodyctl cert generate admin.local
```

Certs are written to `/var/lib/prosody/<domain>.crt` and `<domain>.key`.
Answer `y` to any replace prompts. The vhost configs reference these paths directly.


### Start

```bash
sudo systemctl enable prosody
sudo systemctl start prosody
sudo prosodyctl check config
```

## ClawCommander Service

### Install

```bash
sudo useradd --system --no-create-home --shell /sbin/nologin clawcommander

sudo mkdir -p /opt/clawcommander
sudo cp orchestrator.py xmppctl.py config.toml /opt/clawcommander/
sudo python3 -m venv /opt/clawcommander/venv
sudo /opt/clawcommander/venv/bin/pip install slixmpp
sudo chown -R clawcommander:clawcommander /opt/clawcommander
```

### Sudoers

```bash
echo "clawcommander ALL=(ALL) NOPASSWD: /usr/bin/prosodyctl" \
    | sudo tee /etc/sudoers.d/clawcommander
sudo chmod 440 /etc/sudoers.d/clawcommander
```

### Enable

```bash
sudo cp clawcommander.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable clawcommander
sudo systemctl start clawcommander
sudo journalctl -u clawcommander -f
```

## Usage

Connect your XMPP client to `operator@localhost`. Message `orchestrator@localhost`:

```
help
spawn research myagent
kill myagent@research.local
list
status
```

## Kill switch per vhost

Set `enabled = false` in the relevant vhost config file and run:

```bash
sudo prosodyctl reload
```

All connections on that domain are immediately blocked.
