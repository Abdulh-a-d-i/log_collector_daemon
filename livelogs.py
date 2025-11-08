#!/usr/bin/env python3
# livelogs.py
import asyncio
import sys
import os
import json
import re
from datetime import datetime
import signal

try:
    import websockets
except Exception:
    print("websockets library required. Install: pip install websockets", file=sys.stderr)
    sys.exit(1)

# ---------- Helpers ----------
SYSLOG_MONTHS = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def parse_timestamp(line: str) -> str:
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})", line)
    if m:
        mon, day, timepart = m.groups()
        try:
            month = SYSLOG_MONTHS.get(mon)
            if month:
                now = datetime.utcnow()
                year = now.year
                dt = datetime.strptime(f"{year} {month} {int(day)} {timepart}", "%Y %m %d %H:%M:%S")
                if dt > now:
                    dt = dt.replace(year=year-1)
                return dt.isoformat() + "Z"
        except Exception:
            pass
    m2 = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)", line)
    if m2:
        return m2.group(1)
    return datetime.utcnow().isoformat() + "Z"

# ---------- Globals ----------
CLIENTS = set()
SHUTDOWN = False

# ---------- WebSocket Handlers ----------
async def ws_handler(websocket):
    CLIENTS.add(websocket)
    try:
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        CLIENTS.discard(websocket)


# ---------- Log Tailing ----------
async def tail_and_broadcast(log_file, node_id):
    while not os.path.exists(log_file) and not SHUTDOWN:
        await asyncio.sleep(0.5)

    if SHUTDOWN:
        return

    try:
        with open(log_file, "r", errors="ignore") as f:
            f.seek(0, os.SEEK_END)
            while not SHUTDOWN:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.2)
                    continue
                payload = {
                    "type": "live_log",
                    "node_id": node_id,
                    "timestamp": parse_timestamp(line),
                    "log": line.rstrip("\n")
                }
                data = json.dumps(payload)
                to_remove = []
                for ws in list(CLIENTS):
                    try:
                        await ws.send(data)
                    except Exception:
                        to_remove.append(ws)
                        try:
                            await ws.close()
                        except:
                            pass
                for r in to_remove:
                    CLIENTS.discard(r)
    except Exception as e:
        print(f"[livelogs] tail error: {e}", file=sys.stderr)

# ---------- Signal Handler ----------
def _signal_handler(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True

# ---------- Main Async ----------
async def main_async(log_file, ws_port, node_id, ws_path="/livelogs"):
    server = await websockets.serve(ws_handler, "0.0.0.0", ws_port, ping_interval=20, ping_timeout=10, max_size=None)
    if not os.path.exists(log_file):
      print(f"[livelogs] ERROR: Log file does not exist: {log_file}")
      sys.exit(1)
    print(f"[livelogs] WebSocket server running on ws://0.0.0.0:{ws_port}{ws_path}")

    tail_task = asyncio.create_task(tail_and_broadcast(log_file, node_id))

    try:
        # Keep server alive forever
        await asyncio.Future()  # never completes
    except asyncio.CancelledError:
        pass
    finally:
        tail_task.cancel()
        await server.wait_closed()



# ---------- Run ----------
def run(log_file, ws_port, node_id):
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    if not os.path.exists(log_file):
        print(f"[livelogs] ERROR: log file does not exist: {log_file}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main_async(log_file, ws_port, node_id))

# ---------- Entry Point ----------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Live logs WebSocket streamer")
    parser.add_argument("log_file", help="Path to log file to tail")
    parser.add_argument("ws_port", type=int, help="Port to host WebSocket server on")
    parser.add_argument("node_id", help="Node identifier to include in messages")
    args = parser.parse_args()
    run(args.log_file, args.ws_port, args.node_id)
