#!/bin/bash
# Run as root or via: sudo bash install.sh
# Do NOT run as: sudo ./install.sh  (glob expansion runs as invoking user before sudo)
set -e

INVOKING_USER=$(stat -c '%U' "${BASH_SOURCE[0]}")
echo "Starting ClawCommander install for user $INVOKING_USER"

echo "[1/9] Copying Prosody config..."

mkdir -p /etc/prosody/vhosts
cp configuration/prosody.cfg.lua /etc/prosody/
cp configuration/vhosts/*.cfg.lua /etc/prosody/vhosts/
echo "      Config files copied."

echo "[2/9] Generating TLS certificates..."
mkdir -p /etc/prosody/certs
for domain in localhost research.local security.local admin.local; do
    echo "      Generating cert for: $domain"
    yes "" | prosodyctl cert generate "$domain"
done

echo "[3/9] Installing certificates..."
cp /var/lib/prosody/*.crt /etc/prosody/certs/
cp /var/lib/prosody/*.key /etc/prosody/certs/
echo "      Certs installed."

echo "[4/9] Setting certificate permissions..."
# Certs dir: prosody user needs execute to traverse, others get read on .crt

chown root:prosody /etc/prosody/certs/
chmod 751 /etc/prosody/certs/
# Public certs: readable by all
chmod 644 /etc/prosody/certs/*.crt
# Private keys: readable only by root:prosody
chown prosody:prosody /etc/prosody/certs/*.key
chmod 640 /etc/prosody/certs/*.key
echo "      Permissions set."

echo "Exporting permissions to ca and reloading certificates..."
cp /etc/prosody/certs/*.crt /usr/local/share/ca-certificates/
update-ca-certificates
echo "      ca-certificates updated."

echo "[5/9] Installing Prosody modules..."
cp modules/* /usr/lib/prosody/modules/
echo "      Modules installed."

echo "[6/9] Restarting Prosody..."
systemctl restart prosody
systemctl --no-pager status prosody

echo ""
echo "[7/9] Setting up initial Commander variables..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOML_FILE="$SCRIPT_DIR/config.toml"
sed -i "s|^dotenv_path=.*|dotenv_path=\"$SCRIPT_DIR/.env\"|" "$TOML_FILE"
echo "      dotenv_path set to: $SCRIPT_DIR/.env"

echo ""
echo "[8/9] Creating and building virtualenv.."
python3 -m venv .venv
source .venv/bin/activate
echo ""
echo "  Installing a couple python dependencies..."
pip install slixmpp dotenv

echo ""
echo "  Setting up operator and controller accounts..."
cd $SCRIPT_DIR/controller
python clicontroller.py init
echo ""


echo "[9/9] Setting ownership..."
chown "$INVOKING_USER":"$INVOKING_USER" "$SCRIPT_DIR/.env"
chown -R "$INVOKING_USER":"$INVOKING_USER" "$SCRIPT_DIR/.venv"
echo "      Ownership set to: $INVOKING_USER"


echo "___________________________"


echo ""
echo "Install complete."
