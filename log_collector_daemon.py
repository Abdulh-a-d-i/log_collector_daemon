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
import logging
from logging.handlers import RotatingFileHandler

# Setup logging
LOG_FILE = "/var/log/resolvix.log"
try:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger = logging.getLogger('resolvix')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    # Also log to console
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(console)
except Exception as e:
    # Fallback to console only
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logger = logging.getLogger('resolvix')
    logger.error(f"Could not create log file {LOG_FILE}: {e}")

# -------- CONFIGURATION & defaults --------
DEFAULT_WS_PORT = int(os.getenv("LIVE_WS_PORT", "8755"))  # port where livelogs.py will host WS
DEFAULT_TELEMETRY_WS_PORT = int(os.getenv("TELEMETRY_WS_PORT", "8756"))  # port for telemetry WS
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
    def __init__(self, log_file, api_url, ws_port=DEFAULT_WS_PORT, 
                 telemetry_ws_port=DEFAULT_TELEMETRY_WS_PORT, node_id=None, 
                 interval=1, tail_lines=200, telemetry_interval=DEFAULT_TELEMETRY_INTERVAL):
        self.log_file = os.path.abspath(log_file)
        self.api_url = api_url.rstrip("/") if api_url else None
        self.ws_port = int(ws_port)
        self.telemetry_ws_port = int(telemetry_ws_port)
        self.node_id = node_id or get_node_id()
        self.interval = interval
        self.tail_lines = tail_lines
        self.telemetry_interval = telemetry_interval
        self._stop_flag = threading.Event()
        self._thread = None
        self._live_proc = None  # subprocess for livelogs.py
        self._telemetry_proc = None  # subprocess for telemetry_ws.py
        self._live_lock = threading.Lock()
        self._telemetry_lock = threading.Lock()

        # compiled keyword regex for faster matching
        kw = "|".join(re.escape(k) for k in ERROR_KEYWORDS)
        self._err_re = re.compile(rf"\b({kw})\b", re.IGNORECASE)

    def start(self):
        # starts background thread for monitoring
        logger.info(f"Starting log monitoring for: {self.log_file}")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Node ID: {self.node_id}")
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2)
        # ensure live proc stopped
        self.stop_livelogs()
        self.stop_telemetry()

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
            logger.warning(f"Waiting for log file: {self.log_file}")
            time.sleep(1)
        if self._stop_flag.is_set():
            return

        logger.info(f"Log file found, starting monitoring: {self.log_file}")
        try:
            with open(self.log_file, "r", errors="ignore") as f:
                # go to EOF
                f.seek(0, os.SEEK_END)
                logger.info("Monitoring started, waiting for error logs...")
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
                            "application": "system",
                            "log_line": line.rstrip("\n"),
                            "severity": severity
                        }
                        logger.info(f"Error detected [{severity}]: {line.strip()[:100]}")
                        # best-effort post; don't crash daemon if fails
                        if self.api_url:
                            try:
                                resp = requests.post(f"{self.api_url}/logs", json=payload, timeout=5)
                                if resp.status_code >= 400:
                                    logger.error(f"API POST failed with status {resp.status_code}")
                                else:
                                    logger.debug(f"Error log sent to API successfully")
                            except Exception as e:
                                logger.error(f"Error posting to API: {e}")
                        else:
                            logger.info(f"No API configured, logging locally: {json.dumps(payload)}")
        except Exception as e:
            logger.error(f"Monitor loop exception: {e}", exc_info=True)

    # ---------------- subprocess control for livelogs ----------------
    def start_livelogs(self):
        with self._live_lock:
            if self._live_proc and self._live_proc.poll() is None:
                logger.warning("Livelogs already running")
                return False, "already_running"
            script = os.path.join(os.path.dirname(__file__), "livelogs.py")
            if not os.path.exists(script):
                logger.error(f"livelogs.py not found at {script}")
                return False, "livelogs_missing"
            cmd = [sys.executable, script, self.log_file, str(self.ws_port), self.node_id]
            try:
                self._live_proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
                logger.info(f"Livelogs started on port {self.ws_port}, PID: {self._live_proc.pid}")
                return True, str(self._live_proc.pid)
            except Exception as e:
                logger.error(f"Failed to start livelogs: {e}")
                return False, f"spawn_error: {e}"

    def stop_livelogs(self):
        with self._live_lock:
            if not self._live_proc or self._live_proc.poll() is not None:
                self._live_proc = None
                logger.warning("No active livelogs process to stop")
                return False, "no_active_process"
            try:
                logger.info(f"Stopping livelogs PID: {self._live_proc.pid}")
                self._live_proc.terminate()
                try:
                    self._live_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    logger.warning("Livelogs did not terminate, killing...")
                    self._live_proc.kill()
                    self._live_proc.wait(timeout=3)
                logger.info("Livelogs stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping livelogs: {e}")
                return False, f"stop_error:{e}"
            finally:
                self._live_proc = None
            return True, "stopped"

    # ---------------- subprocess control for telemetry ----------------
    def start_telemetry(self):
        with self._telemetry_lock:
            if self._telemetry_proc and self._telemetry_proc.poll() is None:
                logger.warning("Telemetry already running")
                return False, "already_running"
            script = os.path.join(os.path.dirname(__file__), "telemetry_ws.py")
            if not os.path.exists(script):
                logger.error(f"telemetry_ws.py not found at {script}")
                return False, "telemetry_ws_missing"
            cmd = [
                sys.executable, script, 
                self.node_id, 
                str(self.telemetry_ws_port),
                "--interval", str(self.telemetry_interval)
            ]
            try:
                self._telemetry_proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
                logger.info(f"Telemetry started on port {self.telemetry_ws_port}, PID: {self._telemetry_proc.pid}, interval: {self.telemetry_interval}s")
                return True, str(self._telemetry_proc.pid)
            except Exception as e:
                logger.error(f"Failed to start telemetry: {e}")
                return False, f"spawn_error: {e}"

    def stop_telemetry(self):
        with self._telemetry_lock:
            if not self._telemetry_proc or self._telemetry_proc.poll() is not None:
                self._telemetry_proc = None
                logger.warning("No active telemetry process to stop")
                return False, "no_active_process"
            try:
                logger.info(f"Stopping telemetry PID: {self._telemetry_proc.pid}")
                self._telemetry_proc.terminate()
                try:
                    self._telemetry_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    logger.warning("Telemetry did not terminate, killing...")
                    self._telemetry_proc.kill()
                    self._telemetry_proc.wait(timeout=3)
                logger.info("Telemetry stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping telemetry: {e}")
                return False, f"stop_error:{e}"
            finally:
                self._telemetry_proc = None
            return True, "stopped"

    def get_status(self):
        """Get current status of all services"""
        with self._live_lock:
            livelogs_running = self._live_proc and self._live_proc.poll() is None
            livelogs_pid = self._live_proc.pid if livelogs_running else None
        
        with self._telemetry_lock:
            telemetry_running = self._telemetry_proc and self._telemetry_proc.poll() is None
            telemetry_pid = self._telemetry_proc.pid if telemetry_running else None
        
        return {
            "node_id": self.node_id,
            "log_file": self.log_file,
            "livelogs": {
                "running": livelogs_running,
                "pid": livelogs_pid,
                "ws_port": self.ws_port
            },
            "telemetry": {
                "running": telemetry_running,
                "pid": telemetry_pid,
                "ws_port": self.telemetry_ws_port,
                "interval": self.telemetry_interval
            }
        }

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
        logger.info(f"Control command received: {cmd}")
        
        # Livelogs commands
        if cmd == "start_livelogs":
            ok, info = daemon.start_livelogs()
            if ok:
                return jsonify({"status": "started", "pid": info, "ws_port": daemon.ws_port}), HTTPStatus.OK
            else:
                return jsonify({"status": "error", "detail": info}), HTTPStatus.BAD_REQUEST

        if cmd == "stop_livelogs":
            ok, info = daemon.stop_livelogs()
            if ok:
                return jsonify({"status": "stopped"}), HTTPStatus.OK
            else:
                return jsonify({"status": "error", "detail": info}), HTTPStatus.BAD_REQUEST
        
        # Telemetry commands
        if cmd == "start_telemetry":
            ok, info = daemon.start_telemetry()
            if ok:
                return jsonify({
                    "status": "started", 
                    "pid": info, 
                    "ws_port": daemon.telemetry_ws_port,
                    "interval": daemon.telemetry_interval
                }), HTTPStatus.OK
            else:
                return jsonify({"status": "error", "detail": info}), HTTPStatus.BAD_REQUEST

        if cmd == "stop_telemetry":
            ok, info = daemon.stop_telemetry()
            if ok:
                return jsonify({"status": "stopped"}), HTTPStatus.OK
            else:
                return jsonify({"status": "error", "detail": info}), HTTPStatus.BAD_REQUEST

        logger.warning(f"Unknown command: {cmd}")
        return jsonify({"status": "unknown_command"}), HTTPStatus.BAD_REQUEST

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok", 
            "node_id": daemon.node_id
        }), HTTPStatus.OK
    
    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(daemon.get_status()), HTTPStatus.OK

    return app


# -------- CLI / Entrypoint --------
def parse_args():
    parser = argparse.ArgumentParser(description="Log Collector Daemon (error monitoring + telemetry + control endpoint)")
    parser.add_argument("--log-file", "-l", required=True, help="Path to log file to monitor")
    parser.add_argument("--api-url", "-a", required=True, help="Central API URL to send logs")
    parser.add_argument("--control-port", "-p", type=int, default=DEFAULT_CONTROL_PORT, help="Port for control HTTP server")
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="Port where livelogs will host websocket")
    parser.add_argument("--telemetry-ws-port", type=int, default=DEFAULT_TELEMETRY_WS_PORT, help="Port where telemetry websocket will be hosted")
    parser.add_argument("--node-id", "-n", help="optional node identifier")
    parser.add_argument("--telemetry-interval", "-t", type=int, default=DEFAULT_TELEMETRY_INTERVAL, 
                        help="Telemetry collection interval in seconds (default: 60)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    logger.info("="*60)
    logger.info("Resolvix Daemon Starting")
    logger.info("="*60)
    daemon = LogCollectorDaemon(
        log_file=args.log_file, 
        api_url=args.api_url, 
        ws_port=args.ws_port,
        telemetry_ws_port=args.telemetry_ws_port,
        node_id=args.node_id,
        telemetry_interval=args.telemetry_interval
    )
    daemon.start()
    app = make_app(daemon)
    # run flask on specified control port
    logger.info(f"Control HTTP endpoint: http://0.0.0.0:{args.control_port}")
    logger.info(f"Livelogs WebSocket port: {args.ws_port}")
    logger.info(f"Telemetry WebSocket port: {args.telemetry_ws_port}")
    logger.info(f"Telemetry interval: {args.telemetry_interval}s")
    logger.info(f"Log file: /var/log/resolvix.log")
    try:
        # do not use debug in production
        app.run(host="0.0.0.0", port=args.control_port)
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    finally:
        logger.info("Shutting down daemon...")
        daemon.stop()
        logger.info("Daemon stopped")
