#!/usr/bin/env bash
set -euo pipefail

# -------- Vars --------
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="logcollector.service"
ENV_DIR="/etc/logcollector"
ENV_FILE="$ENV_DIR/logcollector.env"
WRAPPER="$PROJECT_DIR/run_logcollector.sh"

# -------- Root helper --------
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  SUDO="sudo"
else
  SUDO=""
fi

# -------- Pre-reqs --------
echo "[1/7] Installing system prerequisites (python3-venv if available)..."
if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update -y
  $SUDO apt-get install -y python3-venv
elif command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y python3-virtualenv || true
elif command -v yum >/dev/null 2>&1; then
  $SUDO yum install -y python3-virtualenv || true
else
  echo "Package manager not detected. Ensure Python venv is available."
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3 and re-run."
  exit 1
fi

# -------- Venv --------
echo "[2/7] Creating virtual environment..."
if [[ ! -d "$PROJECT_DIR/venv" ]]; then
  python3 -m venv "$PROJECT_DIR/venv"
fi
source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip

echo "[3/7] Installing Python dependencies..."
pip install tailer requests pika

# -------- Inputs --------
echo "[4/7] Gathering configuration..."
read -rp "Full path of the log file to monitor: " LOG_FILE_PATH
if [[ ! -e "$LOG_FILE_PATH" ]]; then
  echo "WARNING: $LOG_FILE_PATH does not exist yet; the daemon will wait for it."
fi

read -rp "Directory to save compressed bundles (will be created): " SAVE_DIR
mkdir -p "$SAVE_DIR"

read -rp "Collect interval in seconds (default 60): " INTERVAL
INTERVAL=${INTERVAL:-60}

read -rp "Tail how many lines per cycle (default 200): " TAIL_LINES
TAIL_LINES=${TAIL_LINES:-200}

echo
echo "Choose transport (RabbitMQ recommended):"
read -rp "Use RabbitMQ? [y/N]: " USE_RMQ
USE_RMQ=${USE_RMQ:-N}

RABBITMQ_URL=""
RABBITMQ_QUEUE="logs"
if [[ "$USE_RMQ" =~ ^[Yy]$ ]]; then
  echo "Provide RabbitMQ connection as a URL, e.g.: amqp://user:pass@host:5672/ or amqps://user:pass@host:5671/vhost"
  read -rp "RabbitMQ URL: " RABBITMQ_URL
  read -rp "RabbitMQ queue name (default 'logs'): " RABBITMQ_QUEUE_IN
  RABBITMQ_QUEUE=${RABBITMQ_QUEUE_IN:-logs}
fi

read -rp "HTTP API URL to also POST tar.gz (optional, leave blank to skip): " API_URL
API_URL=${API_URL:-}

# -------- Env file --------
echo "[5/7] Writing environment file to $ENV_FILE ..."
$SUDO mkdir -p "$ENV_DIR"
$SUDO bash -c "cat > '$ENV_FILE' <<EOF
LOG_FILE_PATH=$LOG_FILE_PATH
SAVE_DIR=$SAVE_DIR
INTERVAL_SECONDS=$INTERVAL
TAIL_LINES=$TAIL_LINES
RABBITMQ_URL=$RABBITMQ_URL
RABBITMQ_QUEUE=$RABBITMQ_QUEUE
API_URL=$API_URL
PYTHONUNBUFFERED=1
EOF"
$SUDO chmod 600 "$ENV_FILE"

# -------- Wrapper script (handles optional args cleanly) --------
echo "[6/7] Creating wrapper script $WRAPPER ..."
cat > "$WRAPPER" <<'EOSH'
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="/etc/logcollector/logcollector.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

ARGS=( "--log-file" "${LOG_FILE_PATH}" "--save-dir" "${SAVE_DIR}" "--interval" "${INTERVAL_SECONDS}" "--tail-lines" "${TAIL_LINES}" )

if [[ -n "${RABBITMQ_URL:-}" ]]; then
  ARGS+=( "--rabbitmq-url" "${RABBITMQ_URL}" "--rabbitmq-queue" "${RABBITMQ_QUEUE:-logs}" )
fi

if [[ -n "${API_URL:-}" ]]; then
  ARGS+=( "--api-url" "${API_URL}" )
fi

exec "${PROJECT_DIR}/venv/bin/python" "${PROJECT_DIR}/log_collector_daemon.py" "${ARGS[@]}"
EOSH
chmod +x "$WRAPPER"

# -------- systemd service --------
echo "[7/7] Installing systemd service..."
$SUDO bash -c "cat > /etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=Log Collector Daemon (bundle and forward to RabbitMQ/HTTP)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$WRAPPER
Restart=on-failure
RestartSec=5
Nice=5
# set lower CPU/IO priority if desired:
# IOSchedulingClass=best-effort
# IOSchedulingPriority=7

[Install]
WantedBy=multi-user.target
EOF"

$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE_NAME"
$SUDO systemctl restart "$SERVICE_NAME"

echo "✅ Installation complete."
echo "Service status: sudo systemctl status $SERVICE_NAME"
echo "Logs: journalctl -u $SERVICE_NAME -f"
