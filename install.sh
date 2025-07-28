#!/bin/bash

REPO_PATH=$(pwd)
SERVICE_TEMPLATE="$REPO_PATH/service/logcollector.service.template"
SERVICE_FILE="/etc/systemd/system/logcollector.service"

echo "Enter full path of the log directory to monitor:"
read LOG_DIR

if [ ! -e "$LOG_DIR" ]; then
    echo "Path does not exist. Exiting."
    exit 1
fi

PYTHON_PATH=$(which python3)

# Generate service file by replacing placeholders
sudo sed \
    -e "s|__PYTHON_PATH__|$PYTHON_PATH|" \
    -e "s|__SCRIPT_PATH__|$REPO_PATH/log_collector_daemon.py|" \
    -e "s|__LOG_DIRECTORY__|$LOG_DIR|" \
    $SERVICE_TEMPLATE | sudo tee $SERVICE_FILE > /dev/null

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable logcollector.service
sudo systemctl start logcollector.service

echo "Service installed and started successfully!"
