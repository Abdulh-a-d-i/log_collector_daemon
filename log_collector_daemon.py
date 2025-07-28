import os
import sys
import time
import tarfile
import subprocess
import requests
from datetime import datetime

def compress_logs(log_dir, output_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = os.path.join(output_dir, f"logs_{timestamp}.tar.gz")

    with tarfile.open(archive_name, "w:gz") as tar:
        tar.add(log_dir, arcname=os.path.basename(log_dir))
    print(f"Compressed logs to {archive_name}")
    return archive_name

def send_via_scp(archive_path, destination):
    scp_command = [
        "scp", archive_path,
        destination
    ]
    result = subprocess.run(scp_command, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Successfully sent {archive_path} via SCP")
        os.remove(archive_path)
    else:
        print(f"Failed to send {archive_path} via SCP: {result.stderr}")

def send_via_http(archive_path, destination_url):
    try:
        with open(archive_path, 'rb') as f:
            files = {'file': (os.path.basename(archive_path), f)}
            response = requests.post(destination_url, files=files)
        if response.status_code == 200:
            print(f"Successfully sent {archive_path} via HTTP POST to {destination_url}")
            os.remove(archive_path)
        else:
            print(f"Failed HTTP POST. Status: {response.status_code} Response: {response.text}")
    except Exception as e:
        print(f"Error sending via HTTP: {e}")

def daemon(log_dir, destination):
    while True:
        try:
            archive = compress_logs(log_dir, "/tmp")

            # ======== DESTINATION HANDLING SECTION (EDIT LATER) ========
            if destination == "":
                print(f"No destination provided. Saved {archive} locally.")
            elif ":" in destination and not destination.startswith("scp://"):
                # Example: localhost:8080 (Send via HTTP POST)
                dest_url = f"http://{destination}/upload"
                send_via_http(archive, dest_url)
            else:
                # Example: user@remote:/path/to/dir/ (Send via SCP)
                send_via_scp(archive, destination)
            # ===========================================================
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(60)  # Sleep for 1 minute

if __name__ == "__main__":
    log_directory = input("Enter the log directory path: ").strip()
    if not os.path.isdir(log_directory):
        print("Invalid directory. Exiting.")
        sys.exit(1)

    destination = input("Enter destination (leave blank to save locally): ").strip()

    print("Running as daemon. Press Ctrl+C to stop.")
    daemon(log_directory, destination)
