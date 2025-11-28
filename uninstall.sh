#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="resolvix.service"
ENV_DIR="/etc/resolvix"
ENV_FILE="$ENV_DIR/resolvix.env"
WRAPPER="$PROJECT_DIR/run_logcollector.sh"
VENV_DIR="$PROJECT_DIR/venv"

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  SUDO="sudo"
fi

echo "Stopping and disabling service..."
$SUDO systemctl stop "$SERVICE_NAME" || true
$SUDO systemctl disable "$SERVICE_NAME" || true
$SUDO systemctl daemon-reload || true

echo "Removing unit file..."
$SUDO rm -f "/etc/systemd/system/$SERVICE_NAME" || true

echo "Removing env file..."
$SUDO rm -f "$ENV_FILE" || true
$SUDO rmdir "$ENV_DIR" 2>/dev/null || true

echo "Removing wrapper and venv..."
rm -f "$WRAPPER" || true
rm -rf "$VENV_DIR" || true

echo "Removing project directory..."
rm -rf "$PROJECT_DIR" || true

echo "✅ Uninstall finished."
