#!/usr/bin/env python3
# livelogs.py
import sys
import time
import os

def tail_log(file_path):
    try:
        with open(file_path, "r", errors="ignore") as f:
            # go to EOF
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.25)
                    continue
                # print each line immediately to stdout, flush
                print(line.rstrip("\n"), flush=True)
    except KeyboardInterrupt:
        # graceful exit
        pass
    except Exception as e:
        print(f"[livelogs] Error: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: livelogs.py <log_file>", file=sys.stderr)
        sys.exit(1)
    tail_log(sys.argv[1])
