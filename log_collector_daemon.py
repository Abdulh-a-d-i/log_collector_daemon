import os
import time
import tarfile
import subprocess
from datetime import datetime

# Configuration (You can modify these)
REMOTE_USER = "username"
REMOTE_HOST = "your.server.com"
REMOTE_PATH = "/path/to/upload/"

def compress_logs(log_dir, output_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = os.path.join(output_dir, f"logs_{timestamp}.tar.gz")

    with tarfile.open(archive_name, "w:gz") as tar:
        tar.add(log_dir, arcname=os.path.basename(log_dir))
    print(f"Compressed logs to {archive_name}")
    return archive_name

def send_logs(archive_path):
    scp_command = [
        "scp", archive_path,
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"
    ]
    result = subprocess.run(scp_command, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Successfully sent {archive_path}")
        os.remove(archive_path)
    else:
        print(f"Failed to send {archive_path}: {result.stderr}")

def daemon(log_dir):
    while True:
        try:
            archive = compress_logs(log_dir, "/tmp")
            send_logs(archive)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(60)  # Sleep for 1 minute

if __name__ == "__main__":
    log_directory = input("Enter the log directory path: ").strip()
    if not os.path.isdir(log_directory):
        print("Invalid directory. Exiting.")
        exit(1)

    print("Running as daemon. Press Ctrl+C to stop.")
    daemon(log_directory)
