import os
import sys
import time
import tarfile
from datetime import datetime, timedelta

def collect_logs(path, destination):
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(minutes=1)
    output_file = "/tmp/latest_logs.tar.gz"

    with tarfile.open(output_file, "w:gz") as tar:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if datetime.fromtimestamp(os.path.getmtime(file_path)) > cutoff_time:
                        tar.add(file_path, arcname=os.path.relpath(file_path, path))
        elif os.path.isfile(path):
            if datetime.fromtimestamp(os.path.getmtime(path)) > cutoff_time:
                tar.add(path, arcname=os.path.basename(path))

    if destination:
        print(f"Simulating sending {output_file} to {destination}")
        # TODO: Implement real sending logic here (HTTP POST etc.)
    else:
        print(f"Logs compressed and saved locally at {output_file}")

def daemon(path, destination):
    while True:
        collect_logs(path, destination)
        time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 log_collector_daemon.py <path_to_monitor> [destination]")
        sys.exit(1)

    path_to_monitor = sys.argv[1]
    destination = sys.argv[2] if len(sys.argv) > 2 else ""

    if not os.path.exists(path_to_monitor):
        print("Invalid path. Exiting.")
        sys.exit(1)

    is_directory = os.path.isdir(path_to_monitor)
    print(f"Monitoring {'directory' if is_directory else 'file'}: {path_to_monitor}")

    daemon(path_to_monitor, destination)
