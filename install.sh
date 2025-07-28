#!/bin/bash

# Prompt for Log File Path
echo -n "Enter full path of the log file to monitor (e.g., /var/log/syslog): "
read log_file

if [ ! -f "$log_file" ]; then
    echo "Log file does not exist. Exiting."
    exit 1
fi

# Prompt for Destination URL (Optional)
echo -n "Enter destination URL to send logs (Leave empty to skip sending to server): "
read destination_url

# Create Systemd Service File
SERVICE_FILE=/etc/systemd/system/logcollector.service

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Log Collector Daemon Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $(pwd)/log_collector_daemon.py $log_file $destination_url
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable logcollector.service
sudo systemctl restart logcollector.service

echo "Service installed and started successfully!"
