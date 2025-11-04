#!/usr/bin/env python3
import sys
import time
import os

def tail_log(file_path):
    try:
        with open(file_path, "r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                print(line.strip(), flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[livelogs] Error: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: livelogs.py <log_file>")
        sys.exit(1)
    tail_log(sys.argv[1])
