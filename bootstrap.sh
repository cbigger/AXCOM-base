#!/bin/bash
# Run as root or via: sudo bash install.sh
# Do NOT run as: sudo ./install.sh  (glob expansion runs as invoking user before sudo)
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use: sudo bash install.sh AND NOT sudo ./install.sh)" >&2
    exit 1
fi

echo "AXCOM bootstrapping Debian install.."
echo ""
echo "Installing prosody, pip, virtualenv, and rsync with apt..."
echo ""
sudo apt install -y prosody python3-pip python3-venv rsync
echo "Running install-docker.sh..."
echo ""
sudo bash install-docker.sh
echo "Running install.sh..."
echo ""
sudo bash install.sh
echo "Running install-service.sh..."
echo ""
sudo bash install-service.sh
echo ""
echo ""
echo "===== Bootstrap complete ====="
echo ""
