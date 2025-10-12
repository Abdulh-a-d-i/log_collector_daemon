#!/bin/bash
set -e

echo "[Installer] Starting installation..."

# Install Python3 and venv if not present
sudo apt update -y
sudo apt install -y python3 python3-venv python3-pip

# Create and activate virtual environment
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate

# Install required Python dependencies
pip install --upgrade pip
pip install flask requests

# Make Python scripts executable
chmod +x log_collector_daemon.py
chmod +x livelogs.py

# Optionally setup systemd service
SERVICE_NAME="log_collector_daemon"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -f "$SERVICE_FILE" ]; then
  echo "[Installer] Creating systemd service..."
  sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Log Collector Daemon
After=network.target

[Service]
ExecStart=$(pwd)/venv/bin/python3 $(pwd)/log_collector_daemon.py
WorkingDirectory=$(pwd)
Restart=always
User=$(whoami)
Environment=PATH=$(pwd)/venv/bin

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable $SERVICE_NAME
  sudo systemctl start $SERVICE_NAME
fi

echo "[Installer] Installation complete."
echo "[Info] Daemon listening on port 8754"
