import os
import sys
import time
import tarfile
from datetime import datetime, timedelta

def collect_and_compress_logs(log_directory, destination):
    now = datetime.now()
    one_minute_ago = now - timedelta(minutes=1)

    logs_to_compress = []

    for root, dirs, files in os.walk(log_directory):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.isfile(file_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if mtime >= one_minute_ago:
                    logs_to_compress.append(file_path)

    if not logs_to_compress:
        print("No logs to compress.")
        return

    tar_path = "/tmp/latest_logs.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for log_file in logs_to_compress:
            tar.add(log_file, arcname=os.path.basename(log_file))

    print(f"Compressed logs saved to {tar_path}")

    if destination and destination != " ":
        # You can later add code to send to ElasticSearch or remote location here.
        print(f"Sending logs to {destination} (Feature Placeholder)")
    else:
        print("No destination provided. Logs saved locally.")

def daemon(log_directory, destination):
    while True:
        collect_and_compress_logs(log_directory, destination)
        time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 log_collector_daemon.py <log_directory> [destination]")
        sys.exit(1)

    log_directory = sys.argv[1]
    if not os.path.isdir(log_directory):
        print("Invalid directory. Exiting.")
        sys.exit(1)

    destination = sys.argv[2] if len(sys.argv) > 2 else ""

    print(f"Monitoring logs in {log_directory}")
    print(f"Destination: {destination if destination else 'Local Storage'}")

    daemon(log_directory, destination)
