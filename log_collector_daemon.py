#!/usr/bin/env python3
# log_collector_daemon.py
import asyncio
import json
import os
import re
import datetime
import argparse
import sys
from websockets.server import serve
import asyncio.subprocess as asp

DEFAULT_PORT = 8575
WS_PATH = "/logs"

class LogCollectorDaemon:
    def __init__(self, log_file, port=DEFAULT_PORT, node_id=None, tail_interval=1):
        self.log_file = log_file
        self.port = port
        self.node_id = node_id or os.uname().nodename
        self.tail_interval = tail_interval
        self.clients = set()
        self.livelogs_proc = None
        self.livelogs_lock = asyncio.Lock()
        # regex for error keywords
        self.pattern = re.compile(r"(emerg|emergency|alert|crit|critical|err|error)", re.IGNORECASE)

    async def broadcast(self, message: dict):
        if not self.clients:
            return
        payload = json.dumps(message)
        # send concurrently, but catch per-client exceptions
        coros = []
        dead = []
        for ws in list(self.clients):
            coros.append(self._safe_send(ws, payload, dead))
        if coros:
            await asyncio.gather(*coros)
        # cleanup dead clients
        for d in dead:
            self.clients.discard(d)

    async def _safe_send(self, ws, payload, dead_list):
        try:
            await ws.send(payload)
        except Exception:
            try:
                await ws.close()
            except:
                pass
            dead_list.append(ws)

    async def error_monitor_loop(self):
        """Continuously tail the log file for error keywords and broadcast them."""
        # if file does not exist yet, wait until created
        while not os.path.exists(self.log_file):
            await asyncio.sleep(1)
        try:
            with open(self.log_file, "r", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(self.tail_interval)
                        continue
                    if self.pattern.search(line):
                        msg = {
                            "type": "error_log",
                            "node_id": self.node_id,
                            "timestamp": datetime.datetime.utcnow().isoformat(),
                            "log": line.rstrip("\n"),
                        }
                        await self.broadcast(msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # broadcast or log locally
            print(f"[daemon] error_monitor_loop exception: {e}", file=sys.stderr)

    async def start_livelogs(self):
        """Start livelogs.py subprocess and create a task to read its stdout."""
        async with self.livelogs_lock:
            if self.livelogs_proc and self.livelogs_proc.returncode is None:
                return False  # already running
            script = os.path.join(os.path.dirname(__file__), "livelogs.py")
            if not os.path.exists(script):
                raise FileNotFoundError(f"livelogs.py not found at {script}")
            # spawn subprocess
            self.livelogs_proc = await asp.create_subprocess_exec(
                sys.executable, script, self.log_file,
                stdout=asp.PIPE,
                stderr=asp.PIPE,
                # on unix, subprocesses inherit signals; we will terminate gracefully
            )
            # start stdout reader task
            asyncio.create_task(self._read_livelogs_output())
            return True

    async def stop_livelogs(self):
        async with self.livelogs_lock:
            if not self.livelogs_proc or self.livelogs_proc.returncode is not None:
                self.livelogs_proc = None
                return False
            try:
                self.livelogs_proc.terminate()
                await asyncio.wait_for(self.livelogs_proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.livelogs_proc.kill()
                await self.livelogs_proc.wait()
            finally:
                self.livelogs_proc = None
            return True

    async def _read_livelogs_output(self):
        proc = self.livelogs_proc
        if not proc or not proc.stdout:
            return
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="ignore").rstrip("\n")
                msg = {
                    "type": "live_log",
                    "node_id": self.node_id,
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "log": text,
                }
                await self.broadcast(msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[daemon] _read_livelogs_output exception: {e}", file=sys.stderr)

    async def ws_handler(self, websocket, path):
        """Handle a single WS connection. Validate path==WS_PATH."""
        if path != WS_PATH:
            await websocket.close(code=1008, reason="Invalid path")
            return
        self.clients.add(websocket)
        try:
            # send initial info
            await websocket.send(json.dumps({
                "type": "info",
                "node_id": self.node_id,
                "message": "connected",
            }))

            async for raw in websocket:
                try:
                    data = json.loads(raw)
                except Exception:
                    # ignore non-json messages
                    continue
                cmd = data.get("command")
                if cmd == "start_live_logs":
                    await self.start_livelogs()
                    await websocket.send(json.dumps({"type":"control","status":"live_started"}))
                elif cmd == "stop_live_logs":
                    stopped = await self.stop_livelogs()
                    await websocket.send(json.dumps({"type":"control","status":"live_stopped" if stopped else "no_live"}))
                else:
                    await websocket.send(json.dumps({"type":"control","status":"unknown_command"}))
        except Exception as e:
            # client disconnected or error
            pass
        finally:
            try:
                await websocket.close()
            except:
                pass
            self.clients.discard(websocket)

    async def run(self):
        print(f"[daemon] Starting WebSocket server on ws://0.0.0.0:{self.port}{WS_PATH}")
        # start server
        async with serve(self.ws_handler, "0.0.0.0", self.port):
            # run error monitor forever
            await self.error_monitor_loop()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", "-l", help="Path to log file")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help="WebSocket port")
    parser.add_argument("--node-id", "-n", help="Node identifier (optional)")
    args = parser.parse_args()
    # decide log file: CLI -> ENV -> prompt -> default
    log_file = args.log_file or os.getenv("LOG_FILE_PATH")
    if not log_file:
        try:
            # interactive prompt (install flow will provide)
            val = input("Enter log file path (press Enter for /var/log/syslog): ").strip()
        except Exception:
            val = ""
        log_file = val or "/var/log/syslog"
    # do not fail if the path does not exist yet; monitor will wait
    return log_file, args.port, args.node_id

if __name__ == "__main__":
    log_file, port, node_id = parse_args()
    daemon = LogCollectorDaemon(log_file=log_file, port=port, node_id=node_id)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        print("[daemon] Interrupted, exiting.")
