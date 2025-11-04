#!/bin/bash
set -e
echo "[Installer] Starting installation..."

# packages for Debian/Ubuntu
sudo apt update -y
sudo apt install -y python3 python3-venv python3-pip

# create venv
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# activate
. venv/bin/activate

# upgrade pip and install dependencies
pip install --upgrade pip
pip install websockets psutil

# make scripts executable
chmod +x livelogs.py log_collector_daemon.py system_info.py

# run system info once
echo "[Installer] Collecting system information..."
python3 system_info.py
echo "[Installer] Saved system_info.json"

# ask for log file path
read -p "Enter log file path (press Enter for /var/log/syslog): " LOG_FILE
LOG_FILE=${LOG_FILE:-/var/log/syslog}

# confirm existence or continue (daemon waits if missing)
if [ ! -f "$LOG_FILE" ]; then
  echo "[Warning] Log file not found at $LOG_FILE. The daemon will wait until the file exists."
fi

# create systemd service template (using current directory)
SERVICE_NAME="log_collector_daemon"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
WORK_DIR="$(pwd)"
PYTHON_PATH="$WORK_DIR/venv/bin/python3"

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Log Collector Daemon
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=${WORK_DIR}
ExecStart=${PYTHON_PATH} ${WORK_DIR}/log_collector_daemon.py --log-file "${LOG_FILE}"
Restart=always
RestartSec=10
Environment=PATH=${WORK_DIR}/venv/bin

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo "[Installer] Installation complete. Daemon should be running."
echo "[Info] WebSocket endpoint: ws://<NODE_IP>:8575/logs"
