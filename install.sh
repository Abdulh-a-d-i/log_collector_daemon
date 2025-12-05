#!/bin/bash
set -e
echo "[Installer] Starting installation..."
# Accept log file path, API URL, and backend SSH key as arguments
LOG_FILE="$1"
API_URL="$2"
BACKEND_PUBLIC_KEY="$3"  # NEW: Backend's SSH public key for file browser

# Provide defaults if arguments are missing
LOG_FILE=${LOG_FILE:-/var/log/syslog}
API_URL=${API_URL:-http://13.235.113.192:3000/api/ticket}

echo "[Installer] Log file: $LOG_FILE"
echo "[Installer] API URL: $API_URL"
if [ -n "$BACKEND_PUBLIC_KEY" ]; then
  echo "[Installer] SSH key provided: ${BACKEND_PUBLIC_KEY:0:50}..."
else
  echo "[Installer] No SSH key provided (file browser will not work)"
fi

# ============================================
# File Browser Setup Functions
# ============================================

create_file_browser_user() {
    echo "[Installer] 🔐 Setting up file browser access..."
    
    if ! id "log-horizon-observer" &>/dev/null; then
        sudo useradd -r -s /usr/sbin/nologin -d /opt/log-horizon log-horizon-observer
        echo "[Installer] ✅ Created log-horizon-observer user"
    else
        echo "[Installer] ✅ User log-horizon-observer already exists"
    fi
    
    sudo usermod -aG adm log-horizon-observer
    echo "[Installer] ✅ Added to 'adm' group for /var/log access"
}

setup_ssh_access() {
    echo "[Installer] 🔑 Configuring SSH access for backend..."
    
    sudo mkdir -p /opt/log-horizon/.ssh
    sudo chmod 700 /opt/log-horizon/.ssh
    
    if [ -n "$BACKEND_PUBLIC_KEY" ]; then
        echo "$BACKEND_PUBLIC_KEY" | sudo tee /opt/log-horizon/.ssh/authorized_keys > /dev/null
        sudo chmod 600 /opt/log-horizon/.ssh/authorized_keys
        sudo chown -R log-horizon-observer:log-horizon-observer /opt/log-horizon
        echo "[Installer] ✅ SSH access configured"
    else
        echo "[Installer] ⚠️  Warning: No SSH public key provided, file browser will not work"
    fi
}

# ============================================
# Setup File Browser Access
# ============================================

create_file_browser_user
setup_ssh_access

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
  
  if [ ! -f "system_info.json" ]; then
    echo "❌ [Installer] ERROR: system_info.json not created!"
    exit 1
  fi
  
  echo "[Installer] System info collected successfully"
  echo "[Installer] System info file size: $(wc -c < system_info.json) bytes"

  # send payload to API (extract base URL from API_URL)
  BASE_API_URL="${API_URL%/api/ticket}"
  SYSTEM_INFO_URL="${BASE_API_URL}/api/system_info"
  echo "[Installer] Sending system info to: $SYSTEM_INFO_URL"
  python3 - <<EOF
import requests
import json
import sys

try:
    with open("system_info.json", "r") as f:
        system_info = json.load(f)
    
    print(f"[Installer] Payload keys: {list(system_info.keys())}")
    print(f"[Installer] Sending POST request to: $SYSTEM_INFO_URL")
    
    resp = requests.post("$SYSTEM_INFO_URL", json=system_info, timeout=10)
    
    print(f"[Installer] Response status: {resp.status_code}")
    print(f"[Installer] Response body: {resp.text[:200]}")
    
    if resp.status_code == 200 or resp.status_code == 201:
        print("✅ System info sent successfully")
        sys.exit(0)
    else:
        print(f"❌ Failed to send system info: HTTP {resp.status_code}")
        print(f"Response: {resp.text}")
        sys.exit(1)
except FileNotFoundError:
    print("❌ Error: system_info.json not found")
    sys.exit(1)
except requests.exceptions.Timeout:
    print("❌ Error: Request timeout after 10 seconds")
    sys.exit(1)
except requests.exceptions.ConnectionError as e:
    print(f"❌ Error: Cannot connect to backend: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error sending system info: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
  
  SYSTEM_INFO_EXIT_CODE=$?
  if [ $SYSTEM_INFO_EXIT_CODE -ne 0 ]; then
    echo "❌ [Installer] WARNING: Failed to send system info (exit code: $SYSTEM_INFO_EXIT_CODE)"
    echo "[Installer] Continuing with installation..."
  fi

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
echo "[Info] File browser user: log-horizon-observer"
if [ -n "$BACKEND_PUBLIC_KEY" ]; then
  echo "[Info] SSH access: Enabled"
else
  echo "[Info] SSH access: Disabled (no key provided)"
fi
