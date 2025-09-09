#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import socket
import platform
import logging
# import subprocess   # commented because uninstall functionality disabled
from datetime import datetime

import tailer
# import pika         # commented for RabbitMQ disable
import json
import requests

# --------------------------------------------------------
# ----------------------- Logging ------------------------
# --------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("logcollector")

# ----------------------- Helpers -----------------------
def get_node_info(log_file_path: str, application: str = "system"):
    """Gather node info for headers and metadata"""
    node_id = socket.gethostbyname(socket.gethostname())
    hostname = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()}"
    return {
        "node_id": node_id,
        "hostname": hostname,
        "os": os_info,
        "log_path": log_file_path,
        "application": application,
    }

# ----------------------- Core -----------------------
class LogCollectorDaemon:
    def __init__(self, log_file_path, save_dir, interval_seconds=60,
                 tail_lines=200, application="system", endpoint_url=None):
        self.log_file_path = os.path.abspath(log_file_path)
        self.save_dir = os.path.abspath(save_dir)
        self.interval_seconds = max(5, int(interval_seconds))
        self.tail_lines = max(10, int(tail_lines))
        self.application = application
        self.endpoint_url = endpoint_url  # NEW ENDPOINT

        os.makedirs(self.save_dir, exist_ok=True)
        self.node_info = get_node_info(self.log_file_path, self.application)

        logger.info(
            "Initialized logcollector: log_file=%s save_dir=%s interval=%s",
            self.log_file_path, self.save_dir, self.interval_seconds
        )

    def _collect_recent_logs(self):
        """Collect logs from tail"""
        try:
            if not os.path.exists(self.log_file_path):
                logger.warning("Log file not found yet: %s", self.log_file_path)
                return []

            with open(self.log_file_path, "r", errors="ignore") as f:
                recent_lines = tailer.tail(f, self.tail_lines)

            return [(line if line.endswith("\n") else line + "\n") for line in recent_lines]
        except Exception as e:
            logger.error("Error collecting logs: %s", e)
            return []

    # ---------------- New Functionality ----------------
    def _detect_severity(self, log_line: str) -> str:
        """Detect severity level from log line"""
        text = log_line.lower()
        if "emerg" in text or "emergency" in text:
            return "emergency"
        elif "alert" in text:
            return "alert"
        elif "crit" in text or "critical" in text:
            return "critical"
        elif "err" in text or "error" in text:
            return "error"
        return "unknown"

    def _send_error_log(self, log_line: str):
        """Send a single high-severity log line to endpoint"""
        if not self.endpoint_url:
            logger.warning("No endpoint provided, skipping send")
            return

        severity = self._detect_severity(log_line)

        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "system_ip": self.node_info["node_id"],
            "log_path": self.node_info["log_path"],
            "application": self.node_info["application"],
            "log_line": log_line.strip(),
            "severity": severity
        }
        try:
            resp = requests.post(self.endpoint_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Sent %s log successfully to %s", severity.upper(), self.endpoint_url)
            else:
                logger.error("Failed to send log: %s %s", resp.status_code, resp.text)
        except Exception as e:
            logger.error("Error sending log: %s", e)

    def run(self):
        logger.info("Starting Log Collector loop (monitoring for EMERG, ALERT, CRIT, ERR)")
        keywords = ["emerg", "emergency", "alert", "crit", "critical", "err", "error"]
        while True:
            start_ts = time.time()
            try:
                lines = self._collect_recent_logs()
                for line in lines:
                    if any(word in line.lower() for word in keywords):
                        self._send_error_log(line)
            except Exception as e:
                logger.error("Loop error: %s", e)

            elapsed = time.time() - start_ts
            to_sleep = max(1, self.interval_seconds - int(elapsed))
            time.sleep(to_sleep)


# ----------------------- Entry Point -----------------------
def main():
    # ---- Read from environment only ----
    log_file = os.getenv("LOG_FILE_PATH")
    save_dir = os.getenv("SAVE_DIR", "/tmp/logcollector")
    interval = int(os.getenv("INTERVAL_SECONDS", "60"))
    tail_lines = int(os.getenv("TAIL_LINES", "200"))
    application = os.getenv("APPLICATION", "system")
    endpoint_url = os.getenv("API_URL")

    if not log_file or not endpoint_url:
        raise RuntimeError("Missing required env vars: LOG_FILE_PATH or API_URL")

    daemon = LogCollectorDaemon(
        log_file_path=log_file,
        save_dir=save_dir,
        interval_seconds=interval,
        tail_lines=tail_lines,
        application=application,
        endpoint_url=endpoint_url,
    )
    daemon.run()

if __name__ == "__main__":
    main()
