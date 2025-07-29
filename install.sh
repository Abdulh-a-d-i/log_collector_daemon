#!/bin/bash

set -e

# Step 1: Create Virtual Environment
echo "Creating Python Virtual Environment..."
python3 -m venv venv

# Step 2: Activate Virtual Environment
echo "Activating Virtual Environment..."
source venv/bin/activate

# Step 3: Install Required Python Packages
echo "Installing required Python packages..."
pip install --upgrade pip
pip install tailer requests

# Step 4: Ask User Inputs
read -p "Enter full path of the log file to monitor: " LOG_FILE_PATH
if [ ! -f "$LOG_FILE_PATH" ]; then
    echo "Log file does not exist. Exiting."
    exit 1
fi

read -p "Enter full path of the directory to save logs: " SAVE_DIR
mkdir -p "$SAVE_DIR"

read -p "Enter API URL to send logs (leave blank if not sending): " API_URL

# Step 5: Prepare systemd service file
SERVICE_FILE="logcollector.service"
cp service.template $SERVICE_FILE

# Replace placeholders in service file
sed -i "s|{LOG_FILE_PATH}|$LOG_FILE_PATH|g" $SERVICE_FILE
sed -i "s|{SAVE_DIR}|$SAVE_DIR|g" $SERVICE_FILE
sed -i "s|{API_URL}|$API_URL|g" $SERVICE_FILE
sed -i "s|{PROJECT_DIR}|$(pwd)|g" $SERVICE_FILE
sed -i "s|{USER}|$USER|g" $SERVICE_FILE
sed -i "s|{PROJECT_DIR}|$(pwd)|g" $SERVICE_FILE

# Step 6: Install systemd service
sudo mv $SERVICE_FILE /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable logcollector.service

# Step 7: Start the Service
sudo systemctl restart logcollector.service

echo "Installation completed successfully!"
echo "Log Collector Daemon is now running in background."
