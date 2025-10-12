#!/usr/bin/env python3
import sys
import time
import requests

def tail_log(file_path, server_url, node_id):
    try:
        with open(file_path, "r") as f:
            # Go to end of file
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue

                payload = {"node_id": node_id, "log": line.strip()}
                try:
                    requests.post(server_url, json=payload, timeout=5)
                except Exception as e:
                    # Don't crash if backend temporarily unavailable
                    print(f"Error sending log: {e}")
                    time.sleep(2)
    except KeyboardInterrupt:
        print("Log streaming stopped.")
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: livelogs.py <log_file> <server_url> <node_id>")
        sys.exit(1)

    log_file, server_url, node_id = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"[livelogs] Streaming {log_file} to {server_url} as {node_id}")
    tail_log(log_file, server_url, node_id)
