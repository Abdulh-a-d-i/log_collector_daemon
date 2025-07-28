import os
import sys
import time
import subprocess
import tarfile
import requests
from datetime import datetime, timedelta

LOG_FILE_PATH = "/tmp/latest_logs.log"
COMPRESSED_FILE_PATH = "/tmp/latest_logs.tar.gz"

# Function to read last N logs
def read_last_n_logs(log_file, n=50):
    try:
        output = subprocess.check_output(["tail", f"-n{n}", log_file])
        return output.decode('utf-8')
    except Exception as e:
        print(f"Error reading logs: {e}")
        return ""

# Function to read logs from last X minutes
def read_logs_last_minute(log_file, minutes=1):
    try:
        since_time = (datetime.now() - timedelta(minutes=minutes)).strftime('%b %d %H:%M')
        output = subprocess.check_output(["awk", f'{{ if ($0 >= "{since_time}") print $0 }}', log_file])
        return output.decode('utf-8')
    except Exception as e:
        print(f"Error reading logs: {e}")
        return ""

# Function to save logs to file
def save_logs_to_file(log_data):
    with open(LOG_FILE_PATH, 'w') as file:
        file.write(log_data)

# Function to compress log file
def compress_log_file():
    with tarfile.open(COMPRESSED_FILE_PATH, "w:gz") as tar:
        tar.add(LOG_FILE_PATH, arcname=os.path.basename(LOG_FILE_PATH))

# Function to send file to server
def send_to_server(destination_url):
    try:
        with open(COMPRESSED_FILE_PATH, 'rb') as file:
            files = {'file': file}
            response = requests.post(destination_url, files=files)
            print(f"Uploaded to server: {response.status_code}")
    except Exception as e:
        print(f"Error sending file: {e}")

# Daemon main loop
def daemon(log_file, destination_url):
    # First time: get last 50 logs
    logs = read_last_n_logs(log_file, n=50)
    save_logs_to_file(logs)
    compress_log_file()
    if destination_url:
        send_to_server(destination_url)

    # Loop every minute
    while True:
        time.sleep(60)
        logs = read_logs_last_minute(log_file)
        save_logs_to_file(logs)
        compress_log_file()
        if destination_url:
            send_to_server(destination_url)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 log_collector_daemon.py <log_file_path> [destination_url]")
        sys.exit(1)

    log_file_path = sys.argv[1]
    if not os.path.isfile(log_file_path):
        print("Invalid log file path. Exiting.")
        sys.exit(1)

    destination = sys.argv[2] if len(sys.argv) > 2 else ""

    print("Daemon started. Press Ctrl+C to stop.")
    daemon(log_file_path, destination)
