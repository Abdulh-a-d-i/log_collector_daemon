# Python Daemon Script (log_collector_daemon.py)

import os
import sys
import time
import tarfile
import requests
from datetime import datetime

LOG_FILE_PATH = "/var/log/syslog"
DESTINATION_API = ""  # Will be set from command-line argument
LOCAL_SAVE_PATH = "/tmp/latest_logs.tar.gz"
SEND_INTERVAL = 60  # 1 minute
LOG_LIMIT = 100  # Number of logs to keep


def read_last_n_logs(file_path, n):
    with open(file_path, 'r') as f:
        lines = f.readlines()
    return lines[-n:]


def save_logs_to_file(log_lines, output_file):
    with open('/tmp/temp_logs.txt', 'w') as f:
        f.writelines(log_lines)

    with tarfile.open(output_file, 'w:gz') as tar:
        tar.add('/tmp/temp_logs.txt', arcname='logs.txt')

    os.remove('/tmp/temp_logs.txt')


def send_file_to_server(file_path, destination):
    try:
        with open(file_path, 'rb') as f:
            files = {'file': ("latest_logs.tar.gz", f)}
            response = requests.post(destination, files=files)
            print(f"Sent to {destination}, Status Code: {response.status_code}")
    except Exception as e:
        print(f"Failed to send file: {e}")


def daemon_loop():
    while True:
        logs = read_last_n_logs(LOG_FILE_PATH, LOG_LIMIT)
        save_logs_to_file(logs, LOCAL_SAVE_PATH)
        print(f"Updated local log archive: {LOCAL_SAVE_PATH}")

        if DESTINATION_API:
            send_file_to_server(LOCAL_SAVE_PATH, DESTINATION_API)

        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        DESTINATION_API = sys.argv[1]

    print("Log Collector Daemon Started...")
    daemon_loop()
