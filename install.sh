#!/bin/bash

# install.sh
# This script will install the log collector daemon service

SERVICE_NAME=logcollector
SERVICE_FILE=/etc/systemd/system/$SERVICE_NAME.service
SCRIPT_PATH=$(pwd)/log_collector_daemon.py

read -p "Enter full path of the log directory to monitor: " LOG_DIRECTORY

if [ ! -d "$LOG_DIRECTORY" ]; then
    echo "Directory does not exist. Exiting."
    exit 1
fi

read -p "Enter destination path or URL (Leave blank to save locally): " DESTINATION

echo "[Unit]
Description=Log Collector Daemon Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $SCRIPT_PATH $LOG_DIRECTORY $DESTINATION
Restart=on-failure

[Install]
WantedBy=multi-user.target" | sudo tee $SERVICE_FILE > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

echo "Service installed and started successfully!"
