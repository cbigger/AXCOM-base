#!/bin/bash
# install-service.sh
# Installs the AXCOM controller as a systemd daemon under a dedicated service user.
#
# Prerequisites: run install.sh first. This script expects that prosody has been
# configured, TLS certs are in place, and the .env file exists in the project root.
#
# Run as root: sudo bash install-service.sh
set -e

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SERVICE_USER="axcom"
SERVICE_GROUP="axcom"
INSTALL_DIR="/opt/axcom"
UNIT_FILE="/etc/systemd/system/axcom-controller.service"
UNIT_NAME="axcom-controller"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo bash install-service.sh)." >&2
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo "ERROR: .env not found in $SCRIPT_DIR." >&2
    echo "       Run install.sh first to generate accounts and the .env file." >&2
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/config.toml" ]]; then
    echo "ERROR: config.toml not found in $SCRIPT_DIR." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Service user
# ---------------------------------------------------------------------------

echo "[1/7] Creating service user '$SERVICE_USER'..."

if id "$SERVICE_USER" &>/dev/null; then
    echo "      User '$SERVICE_USER' already exists, skipping creation."
else
    useradd \
        --system \
        --no-create-home \
        --home-dir "$INSTALL_DIR" \
        --shell /usr/sbin/nologin \
        --comment "AXCOM Controller service account" \
        "$SERVICE_USER"
    echo "      Created system user: $SERVICE_USER"
fi

# The controller shells out to prosodyctl to register/delete XMPP accounts,
# which requires membership in the prosody group.
if getent group prosody &>/dev/null; then
    usermod -aG prosody "$SERVICE_USER"
    echo "      Added $SERVICE_USER to group: prosody"
else
    echo "      WARNING: 'prosody' group not found. xmppctl commands may fail." >&2
fi

# The controller manages Docker containers via the Docker socket.
if getent group docker &>/dev/null; then
    usermod -aG docker "$SERVICE_USER"
    echo "      Added $SERVICE_USER to group: docker"
else
    echo "      WARNING: 'docker' group not found. Docker commands will fail." >&2
    echo "               Run install-docker.sh if Docker is required." >&2
fi

# ---------------------------------------------------------------------------
# Copy project files
# ---------------------------------------------------------------------------

echo "[2/7] Copying project files to $INSTALL_DIR..."

mkdir -p "$INSTALL_DIR"

# Copy everything except the old venv (it has baked-in paths and will be rebuilt).
rsync -a --exclude='.venv' "$SCRIPT_DIR/" "$INSTALL_DIR/"

echo "      Files copied."

# ---------------------------------------------------------------------------
# Update config.toml with the new install path
# ---------------------------------------------------------------------------

echo "[3/7] Updating config.toml paths..."

TOML_FILE="$INSTALL_DIR/config.toml"
sed -i "s|^dotenv_path=.*|dotenv_path=\"$INSTALL_DIR/.env\"|" "$TOML_FILE"
echo "      dotenv_path set to: $INSTALL_DIR/.env"

# ---------------------------------------------------------------------------
# Rebuild the virtualenv at its final location
# ---------------------------------------------------------------------------

echo "[4/7] Building virtualenv at $INSTALL_DIR/.venv..."

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet slixmpp python-dotenv

echo "      Virtualenv built."

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

echo "[5/7] Setting ownership..."

# The service user owns the entire install directory.
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$INSTALL_DIR"

# The .env contains credentials -- restrict it to the service user only.
chmod 600 "$INSTALL_DIR/.env"

# Prosody cert keys are root:prosody 640. The service user is now in the
# prosody group so it can read them. The certs directory itself is 751,
# which is also traversable. No changes needed there.

echo "      Ownership set."

# ---------------------------------------------------------------------------
# Systemd unit file
# ---------------------------------------------------------------------------

echo "[6/7] Installing systemd unit..."

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=AXCOM Controller Bot
# Start after the network is up and prosody has started, but do not
# require either to remain running -- the bot handles its own reconnect logic.
After=network-online.target prosody.service
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}

WorkingDirectory=${INSTALL_DIR}/controller
ExecStart=${INSTALL_DIR}/.venv/bin/python controller.py

# Restart on failure with the same delay the bot uses internally for XMPP reconnects.
Restart=on-failure
RestartSec=10

# Give the process time to shut down cleanly before SIGKILL.
TimeoutStopSec=30

StandardOutput=journal
StandardError=journal
SyslogIdentifier=axcom-controller

[Install]
WantedBy=multi-user.target
EOF

echo "      Unit file written to: $UNIT_FILE"

# ---------------------------------------------------------------------------
# Enable and start
# ---------------------------------------------------------------------------

echo "[7/7] Enabling and starting $UNIT_NAME..."

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
systemctl start "$UNIT_NAME"

echo ""
systemctl --no-pager status "$UNIT_NAME"

echo ""
echo "___________________________"
echo ""
echo "Service install complete."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status $UNIT_NAME"
echo "  sudo systemctl restart $UNIT_NAME"
echo "  sudo journalctl -u $UNIT_NAME -f"
