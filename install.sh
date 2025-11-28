#!/bin/bash
set -e
echo "[Installer] Starting installation..."
# Accept log file path and API URL as arguments
LOG_FILE="$1"
API_URL="$2"

# Provide defaults if arguments are missing
LOG_FILE=${LOG_FILE:-/var/log/syslog}
API_URL=${API_URL:-http://13.235.113.192:3000/api/ticket}

echo "[Installer] Log file: $LOG_FILE"
echo "[Installer] API URL: $API_URL"

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
pip install websockets psutil requests flask_cors

# make scripts executable
chmod +x livelogs.py log_collector_daemon.py system_info.py

# 🔹 run system_info only once using flag
# FLAG_FILE="/var/log/system_info_done.flag"

# if [ ! -f "$FLAG_FILE" ]; then
  echo "[Installer] Collecting system information..."

  # run system_info.py
  python3 system_info.py

  # send payload to API
  NEXTJS_API_URL="http://13.235.113.192:3000/api/system_info"
  echo "[Installer] Sending system info to API: $NEXTJS_API_URL"
  python3 - <<EOF
import requests
import json
with open("system_info.json", "r") as f:
    system_info = json.load(f)

try:
    resp = requests.post("$NEXTJS_API_URL", json=system_info)
    if resp.status_code == 200:
        print("✅ System info sent successfully")
    else:
        print("❌ Failed to send system info:", resp.text)
except Exception as e:
    print("❌ Error sending system info:", e)
EOF

  # create flag file so it doesn't run again
  # sudo touch "$FLAG_FILE"
  # sudo chmod 644 "$FLAG_FILE"
# else
#   echo "[Installer] System info already collected and sent, skipping..."
# fi



# confirm existence or continue (daemon waits if missing)
if [ ! -f "$LOG_FILE" ]; then
  echo "[Warning] Log file not found at $LOG_FILE. The daemon will wait until the file exists."
fi

# create systemd service template (using current directory)
SERVICE_NAME="resolvix"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
WORK_DIR="$(pwd)"
PYTHON_PATH="$WORK_DIR/venv/bin/python3"

# Create log file with proper permissions
sudo touch /var/log/resolvix.log
sudo chmod 666 /var/log/resolvix.log

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Resolvix
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=${WORK_DIR}
ExecStartPre=+/bin/bash -c "touch /var/log/resolvix.log; chmod 666 /var/log/resolvix.log"
ExecStart=${PYTHON_PATH} ${WORK_DIR}/log_collector_daemon.py --log-file "${LOG_FILE}" --api-url "${API_URL}"
Restart=always
RestartSec=10
Environment=PATH=${WORK_DIR}/venv/bin
StandardOutput=append:/var/log/resolvix.log
StandardError=append:/var/log/resolvix.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo "[Installer] Installation complete. Daemon should be running."
echo "[Info] WebSocket endpoint: ws://<NODE_IP>:8755/logs"
