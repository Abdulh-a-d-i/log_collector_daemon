#!/usr/bin/env python3
# log_collector_daemon.py
from flask_cors import CORS
import threading
import time
import os
import re
import json
import argparse
import socket
import platform
import uuid
from datetime import datetime
from http import HTTPStatus
import requests
from flask import Flask, request, jsonify
import subprocess
import sys

# Import the telemetry collector
from telemetry_collector import TelemetryCollector

# -------- CONFIGURATION & defaults --------
DEFAULT_WS_PORT = int(os.getenv("LIVE_WS_PORT", "8755"))  # port where livelogs.py will host WS
DEFAULT_CONTROL_PORT = int(os.getenv("CONTROL_PORT", "8754"))  # this daemon's control HTTP port
DEFAULT_TELEMETRY_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "60"))  # telemetry collection interval
ERROR_KEYWORDS = [
    "emerg", "emergency", "alert", "crit", "critical",
    "err", "error", "fail", "failed", "failure", "panic", "fatal"
]

# -------- helpers --------
def get_node_id():
    try:
        # prefer an IP if possible
        ip = socket.gethostbyname(socket.gethostname())
        return ip
    except Exception:
        return socket.gethostname()

def detect_severity(line: str) -> str:
    text = line.lower()
    if any(k in text for k in ["panic", "fatal", "critical", "crit"]):
        return "critical"
    if any(k in text for k in ["fail", "failed", "failure"]):
        return "failure"
    if any(k in text for k in ["err", "error"]):
        return "error"
    if any(k in text for k in ["warn", "warning"]):
        return "warn"
    return "info"

# Try to parse a timestamp from a common syslog-like prefix.
# If parsing fails, return UTC now.
SYSLOG_MONTHS = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}
def parse_timestamp(line: str) -> str:
    # Common syslog format: "Oct 11 22:14:15 hostname ..." (no year)
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})", line)
    if m:
        mon, day, timepart = m.groups()
        try:
            month = SYSLOG_MONTHS.get(mon, None)
            if month:
                now = datetime.utcnow()
                year = now.year
                dt = datetime.strptime(f"{year} {month} {day} {timepart}", "%Y %m %d %H:%M:%S")
                # if date is in future (year edge), subtract one year
                if dt > now:
                    dt = dt.replace(year=year-1)
                return dt.isoformat() + "Z"
        except Exception:
            pass
    # RFC3339 / ISO-like anywhere in the line
    m2 = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)", line)
    if m2:
        try:
            return m2.group(1)
        except:
            pass
    return datetime.utcnow().isoformat() + "Z"

# -------- Daemon class --------
class LogCollectorDaemon:
    def __init__(self, log_file, api_url, ws_port=DEFAULT_WS_PORT, node_id=None, interval=1, 
                 tail_lines=200, telemetry_interval=DEFAULT_TELEMETRY_INTERVAL, 
                 enable_telemetry=True):
        self.log_file = os.path.abspath(log_file)
        self.api_url = api_url.rstrip("/") if api_url else None
        self.ws_port = int(ws_port)
        self.node_id = node_id or get_node_id()
        self.interval = interval
        self.tail_lines = tail_lines
        self._stop_flag = threading.Event()
        self._thread = None
        self._live_proc = None  # subprocess for livelogs.py
        self._live_lock = threading.Lock()

        # Telemetry collector
        self.telemetry = None
        if enable_telemetry and self.api_url:
            self.telemetry = TelemetryCollector(
                api_url=self.api_url,
                node_id=self.node_id,
                interval=telemetry_interval
            )

        # compiled keyword regex for faster matching
        kw = "|".join(re.escape(k) for k in ERROR_KEYWORDS)
        self._err_re = re.compile(rf"\b({kw})\b", re.IGNORECASE)

    def start(self):
        # starts background thread for monitoring
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
        # Start telemetry collection
        if self.telemetry:
            self.telemetry.start()

    def stop(self):
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2)
        
        # Stop telemetry collection
        if self.telemetry:
            self.telemetry.stop()
            
        # ensure live proc stopped
        self.stop_livelogs()

    def _read_last_lines(self, filepath, lines=200):
        try:
            with open(filepath, "r", errors="ignore") as f:
                return tail_lines_from_file(f, lines)
        except Exception:
            return []

    def _monitor_loop(self):
        # main loop: tail log file continuously and send matches via HTTP POST
        # Wait until file exists; do not crash if missing.
        while not os.path.exists(self.log_file) and not self._stop_flag.is_set():
            time.sleep(1)
        if self._stop_flag.is_set():
            return

        try:
            with open(self.log_file, "r", errors="ignore") as f:
                # go to EOF
                f.seek(0, os.SEEK_END)
                while not self._stop_flag.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(self.interval)
                        continue
                    if self._err_re.search(line):
                        severity = detect_severity(line)
                        ts = parse_timestamp(line)
                        payload = {
                            "timestamp": ts,
                            "system_ip": self.node_id,
                            "log_path": self.log_file,
                            "application": "system",   # or whatever app name
                            "log_line": line.rstrip("\n"),
                            "severity": severity
                        }
                        # best-effort post; don't crash daemon if fails
                        if self.api_url:
                            try:
                                resp = requests.post(f"{self.api_url}/logs", json=payload, timeout=5)
                                # non-200 isn't fatal; log if needed
                                if resp.status_code >= 400:
                                    print(f"[daemon] POST to {self.api_url}/logs returned {resp.status_code}")
                            except Exception as e:
                                print(f"[daemon] Error posting to API: {e}")
                        else:
                            # no API configured: just print locally (safe fallback)
                            print(json.dumps(payload))
        except Exception as e:
            print(f"[daemon] Monitor loop exception: {e}")

    # ---------------- subprocess control ----------------
    def start_livelogs(self):
        with self._live_lock:
            if self._live_proc and self._live_proc.poll() is None:
                return False, "already_running"
            script = os.path.join(os.path.dirname(__file__), "livelogs.py")
            if not os.path.exists(script):
                return False, "livelogs_missing"
            cmd = [sys.executable, script, self.log_file, str(self.ws_port), self.node_id]
            try:
                # spawn as detached process group
                self._live_proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
                return True, str(self._live_proc.pid)
            except Exception as e:
                return False, f"spawn_error: {e}"

    def stop_livelogs(self):
        with self._live_lock:
            if not self._live_proc or self._live_proc.poll() is not None:
                self._live_proc = None
                return False, "no_active_process"
            try:
                self._live_proc.terminate()
                try:
                    self._live_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._live_proc.kill()
                    self._live_proc.wait(timeout=3)
            except Exception as e:
                return False, f"stop_error:{e}"
            finally:
                self._live_proc = None
            return True, "stopped"

# tail helper (efficientish)
def tail_lines_from_file(fobj, n):
    # read from end backwards in blocks
    # simple fallback: read whole file if small
    try:
        fobj.seek(0, os.SEEK_END)
        filesize = fobj.tell()
        blocksize = 1024
        data = ""
        while len(data.splitlines()) <= n and filesize > 0:
            seekpos = max(0, filesize - blocksize)
            fobj.seek(seekpos)
            chunk = fobj.read(min(blocksize, filesize))
            data = chunk + data
            filesize = seekpos
            if seekpos == 0:
                break
        return data.splitlines()[-n:]
    except Exception:
        # fallback to reading everything
        fobj.seek(0)
        return fobj.readlines()[-n:]

# -------- Flask HTTP control app --------
def make_app(daemon: LogCollectorDaemon):
    app = Flask(__name__)
    CORS(app, origins="*")  # Allow all origins

    @app.route("/control", methods=["POST"])
    def control():
        data = request.get_json(force=True)
        cmd = data.get("command")
        if cmd == "start_livelogs":
            ok, info = daemon.start_livelogs()
            if ok:
                return jsonify({"status": "started", "pid": info}), HTTPStatus.OK
            else:
                return jsonify({"status": "error", "detail": info}), HTTPStatus.BAD_REQUEST

        if cmd == "stop_livelogs":
            ok, info = daemon.stop_livelogs()
            if ok:
                return jsonify({"status": "stopped"}), HTTPStatus.OK
            else:
                return jsonify({"status": "error", "detail": info}), HTTPStatus.BAD_REQUEST
        
        if cmd == "get_telemetry":
            if daemon.telemetry:
                metrics = daemon.telemetry.collect_all_metrics()
                return jsonify(metrics), HTTPStatus.OK
            else:
                return jsonify({"status": "telemetry_disabled"}), HTTPStatus.BAD_REQUEST

        return jsonify({"status": "unknown_command"}), HTTPStatus.BAD_REQUEST

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok", 
            "node_id": daemon.node_id,
            "telemetry_enabled": daemon.telemetry is not None
        }), HTTPStatus.OK

    return app


# -------- CLI / Entrypoint --------
def parse_args():
    parser = argparse.ArgumentParser(description="Log Collector Daemon (error monitoring + telemetry + control endpoint)")
    parser.add_argument("--log-file", "-l", required=True, help="Path to log file to monitor")
    parser.add_argument("--api-url", "-a", required=True, help="Central API URL to send logs and telemetry")
    parser.add_argument("--control-port", "-p", type=int, default=DEFAULT_CONTROL_PORT, help="Port for control HTTP server")
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="Port where livelogs will host websocket")
    parser.add_argument("--node-id", "-n", help="optional node identifier")
    parser.add_argument("--telemetry-interval", "-t", type=int, default=DEFAULT_TELEMETRY_INTERVAL, 
                        help="Telemetry collection interval in seconds (default: 60)")
    parser.add_argument("--disable-telemetry", action="store_true", help="Disable telemetry collection")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    daemon = LogCollectorDaemon(
        log_file=args.log_file, 
        api_url=args.api_url, 
        ws_port=args.ws_port, 
        node_id=args.node_id,
        telemetry_interval=args.telemetry_interval,
        enable_telemetry=not args.disable_telemetry
    )
    daemon.start()
    app = make_app(daemon)
    # run flask on specified control port
    print(f"[daemon] Control HTTP endpoint listening on 0.0.0.0:{args.control_port}/control")
    print(f"[daemon] Telemetry: {'enabled' if daemon.telemetry else 'disabled'}")
    try:
        # do not use debug in production
        app.run(host="0.0.0.0", port=args.control_port)
    except KeyboardInterrupt:
        print("[daemon] interrupted")
    finally:
        daemon.stop()
