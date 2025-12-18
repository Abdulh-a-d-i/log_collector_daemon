#!/bin/bash
set -e
echo "[Installer] Starting installation..."
# Accept parameters from backend
LOG_FILE="$1"
API_URL="$2"
SYSTEM_INFO_URL="$3"
AUTH_TOKEN="$4"
BACKEND_PUBLIC_KEY="$5"  # Backend's SSH public key for file browser
TELEMETRY_BACKEND_URL="$6"  # Telemetry backend URL for historical data

# Provide defaults if arguments are missing
LOG_FILE=${LOG_FILE:-/var/log/syslog}
API_URL=${API_URL:-http://13.235.113.192:3000/api/ticket}
SYSTEM_INFO_URL=${SYSTEM_INFO_URL:-http://13.235.113.192:3000/api/system_info}
# Extract base URL from API_URL for telemetry (remove /api/ticket)
BASE_URL=$(echo "$API_URL" | sed 's/\/api\/ticket$//')
TELEMETRY_BACKEND_URL=${TELEMETRY_BACKEND_URL:-$BASE_URL}

echo "[Installer] Log file: $LOG_FILE"
echo "[Installer] API URL: $API_URL"
echo "[Installer] System Info URL: $SYSTEM_INFO_URL"
echo "[Installer] Telemetry Backend URL: $TELEMETRY_BACKEND_URL"
if [ -n "$AUTH_TOKEN" ]; then
  echo "[Installer] Auth token: ${AUTH_TOKEN:0:20}..."
fi
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
    
    if ! id "resolvix" &>/dev/null; then
        sudo useradd -m -s /bin/bash resolvix
        echo "[Installer] ✅ Created resolvix user"
    else
        echo "[Installer] ✅ User resolvix already exists"
    fi
    
    sudo usermod -aG adm resolvix
    echo "[Installer] ✅ Added to 'adm' group for /var/log access"
}

setup_ssh_access() {
    echo "[Installer] 🔑 Configuring SSH access for backend..."
    
    RESOLVIX_HOME=$(eval echo ~resolvix)
    
    sudo mkdir -p $RESOLVIX_HOME/.ssh
    sudo chmod 700 $RESOLVIX_HOME/.ssh
    
    if [ -n "$BACKEND_PUBLIC_KEY" ]; then
        echo "$BACKEND_PUBLIC_KEY" | sudo tee -a $RESOLVIX_HOME/.ssh/authorized_keys > /dev/null
        sudo chmod 600 $RESOLVIX_HOME/.ssh/authorized_keys
        sudo chown -R resolvix:resolvix $RESOLVIX_HOME/.ssh
        echo "[Installer] ✅ SSH access configured for resolvix user"
    else
        echo "[Installer] ⚠️  Warning: No SSH public key provided, file browser will not work"
    fi
}

# ============================================
# Setup File Browser Access
# ============================================

create_file_browser_user
setup_ssh_access

# ============================================
# APT Lock Handling Function
# ============================================

wait_for_apt_lock() {
    echo "[Installer] 🔒 Checking for apt locks..."
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
           sudo fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
           sudo fuser /var/cache/apt/archives/lock >/dev/null 2>&1; then
            
            attempt=$((attempt + 1))
            echo "[Installer] ⏳ apt is locked (attempt $attempt/$max_attempts). Waiting 10 seconds..."
            
            # Show which process is holding the lock
            if pgrep -a "apt|dpkg|packagekit" > /dev/null; then
                echo "[Installer] 📦 Processes using apt:"
                pgrep -a "apt|dpkg|packagekit" || true
            fi
            
            sleep 10
        else
            echo "[Installer] ✅ apt lock is free"
            return 0
        fi
    done
    
    echo "[Installer] ⚠️  apt still locked after $max_attempts attempts"
    echo "[Installer] 🛠️  Attempting to kill packagekitd..."
    sudo killall packagekitd 2>/dev/null || true
    sleep 5
    
    return 0
}

# ============================================
# Install Packages with Lock Handling
# ============================================

install_packages() {
    wait_for_apt_lock
    
    echo "[Installer] 📦 Updating package lists..."
    sudo apt update -y
    
    echo "[Installer] 📦 Installing required packages..."
    sudo apt install -y python3 python3-venv python3-pip
}

install_packages

# create venv
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# activate
. venv/bin/activate

# upgrade pip and install dependencies
pip install --upgrade pip
pip install websockets psutil requests flask_cors
pip install pika


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

  # send payload to API
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
    
    headers = {}
    if "$AUTH_TOKEN":
        headers["Authorization"] = f"Bearer $AUTH_TOKEN"
    
    resp = requests.post("$SYSTEM_INFO_URL", json=system_info, headers=headers, timeout=10)
    
    print(f"[Installer] Response status: {resp.status_code}")
    print(f"[Installer] Response body: {resp.text[:200]}")
    
    if resp.status_code == 200 or resp.status_code == 201:
        print("✅ System info sent successfully")
        
        # Extract machine ID from response and save to system_info.json
        try:
            response_data = resp.json()
            if 'system_info' in response_data and 'id' in response_data['system_info']:
                machine_id = response_data['system_info']['id']
                system_info['id'] = machine_id
                
                with open("system_info.json", "w") as f:
                    json.dump(system_info, f, indent=2)
                
                print(f"✅ Machine UUID saved: {machine_id}")
            else:
                print("⚠️  Warning: No machine ID in response")
        except Exception as e:
            print(f"⚠️  Warning: Could not save machine ID: {e}")
        
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



# ============================================
# Create Configuration Files
# ============================================

echo "[Installer] 📝 Creating configuration files..."

# Create config directory
sudo mkdir -p /etc/resolvix
sudo chmod 755 /etc/resolvix

# Create default config.json
sudo tee /etc/resolvix/config.json > /dev/null <<CONFIG_EOF
{
  "connectivity": {
    "api_url": "${API_URL}",
    "telemetry_backend_url": "${TELEMETRY_BACKEND_URL}"
  },
  "monitoring": {
    "log_files": ["${LOG_FILE}"]
  },
  "ports": {
    "control": 8754,
    "ws": 8755,
    "telemetry_ws": 8756
  },
  "intervals": {
    "telemetry": 3,
    "heartbeat": 30
  }
}
CONFIG_EOF

sudo chmod 644 /etc/resolvix/config.json
echo "[Installer] ✅ Created /etc/resolvix/config.json"

# Create secrets.json (if passwords provided)
if [ -n "$AUTH_TOKEN" ] || [ -n "$DB_PASSWORD" ]; then
  sudo tee /etc/resolvix/secrets.json > /dev/null <<SECRETS_EOF
{
  "auth_token": "${AUTH_TOKEN:-}",
  "db_password": "${DB_PASSWORD:-}",
  "telemetry_jwt_token": ""
}
SECRETS_EOF

  sudo chmod 600 /etc/resolvix/secrets.json
  sudo chown $(whoami):$(whoami) /etc/resolvix/secrets.json
  echo "[Installer] ✅ Created /etc/resolvix/secrets.json (restricted permissions)"
else
  echo "[Installer] ⚠️  No secrets to store, skipping secrets.json"
fi

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
ExecStart=${PYTHON_PATH} ${WORK_DIR}/log_collector_daemon.py --log-file "${LOG_FILE}" --api-url "${API_URL}" --telemetry-backend-url "${TELEMETRY_BACKEND_URL}"
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
echo "[Info] File browser user: resolvix"
if [ -n "$BACKEND_PUBLIC_KEY" ]; then
  echo "[Info] SSH access: Enabled for resolvix user"
  echo "[Info] Test: ssh -i ~/.ssh/resolvix_rsa resolvix@<NODE_IP> 'ls /var/log'"
else
  echo "[Info] SSH access: Disabled (no key provided)"
fi
