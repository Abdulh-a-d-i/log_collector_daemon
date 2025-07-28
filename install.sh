#!/bin/bash

# Function to validate inputs
validate_input() {
    local input=$1
    local description=$2
    if [ -z "$input" ]; then
        echo "Error: $description cannot be empty"
        exit 1
    fi
}

# Get user inputs
read -p "Enter log file path (e.g., /var/log/syslog): " LOG_FILE_PATH
validate_input "$LOG_FILE_PATH" "Log file path"

read -p "Enter local save directory (e.g., /home/user/logs): " SAVE_DIR
validate_input "$SAVE_DIR" "Save directory"

read -p "Enter API endpoint URL (optional, press Enter to skip): " API_URL

# Get current user and Python path
CURRENT_USER=$(whoami)
PYTHON_PATH=$(which python3)
SCRIPT_PATH=$(realpath "$(dirname "$0")/log_collector_daemon.py")

# Validate Python and script existence
if [ ! -f "$PYTHON_PATH" ]; then
    echo "Error: Python3 not found"
    exit 1
fi

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: log_collector_daemon.py not found"
    exit 1
fi

# Create save directory if it doesn't exist
mkdir -p "$SAVE_DIR"

# Create service file from template
SERVICE_FILE="/etc/systemd/system/logcollector.service"
TEMPLATE_FILE="$(dirname "$0")/service.template"

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "Error: service.template not found"
    exit 1
fi

# Replace placeholders in service template
if [ -z "$API_URL" ]; then
    EXEC_START="$PYTHON_PATH $SCRIPT_PATH $LOG_FILE_PATH $SAVE_DIR"
else
    EXEC_START="$PYTHON_PATH $SCRIPT_PATH $LOG_FILE_PATH $SAVE_DIR $API_URL"
fi

sed -e "s|{USER}|$CURRENT_USER|g" \
    -e "s|{PYTHON_PATH}|$PYTHON_PATH|g" \
    -e "s|{SCRIPT_PATH}|$SCRIPT_PATH|g" \
    -e "s|{EXEC_START}|$EXEC_START|g" \
    "$TEMPLATE_FILE" > "$SERVICE_FILE"

# Set permissions
chmod 644 "$SERVICE_FILE"

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable logcollector.service
systemctl start logcollector.service

echo "Log Collector Daemon installed and started successfully!"
echo "Service status:"
systemctl status logcollector.service
