#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import tarfile
import logging
import tempfile
import argparse
from datetime import datetime, timedelta, timezone

import tailer
import requests

# pika is optional at import time; error is handled when publishing
try:
    import pika
except Exception:  # handled later if RabbitMQ is used
    pika = None

# ----------------------- Logging -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("logcollector")

# ----------------------- Helpers -----------------------
ISO_TRY_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
]

SYSLOG_FORMATS = [
    "%b %d %H:%M:%S",   # e.g. "Aug 31 12:34:56"
]

def parse_dt_safe(s: str):
    """Try hard to parse a timestamp prefix from a log line. Returns aware or naive dt, or None."""
    text = s.strip()
    if not text:
        return None

    # Common case: ISO with 'Z'
    prefix = text[:32]
    if "Z" in prefix:
        for f in ISO_TRY_FORMATS:
            try:
                p = prefix.replace("Z", "+0000").replace("+00:00", "+0000")
                return datetime.strptime(p[:32], f)
            except Exception:
                pass

    # Try several ISO-ish formats (with/without tz)
    for f in ISO_TRY_FORMATS:
        try:
            return datetime.strptime(prefix, f)
        except Exception:
            pass

    # Try syslog formats (no year, no tz)
    sys_prefix = text[:15]  # "Aug 31 12:34:56"
    for f in SYSLOG_FORMATS:
        try:
            dt = datetime.strptime(sys_prefix, f)
            # inject current year
            now = datetime.now()
            dt = dt.replace(year=now.year)
            return dt
        except Exception:
            pass

    return None


# ----------------------- Core -----------------------
class LogCollectorDaemon:
    def __init__(
        self,
        log_file_path: str,
        save_dir: str,
        interval_seconds: int = 60,
        tail_lines: int = 200,
        api_url: str | None = None,
        rabbitmq_url: str | None = None,
        rabbitmq_queue: str = "logs",
    ):
        self.log_file_path = os.path.abspath(log_file_path)
        self.save_dir = os.path.abspath(save_dir)
        self.interval_seconds = max(5, int(interval_seconds))
        self.tail_lines = max(10, int(tail_lines))

        self.api_url = (api_url or "").strip() or None
        self.rabbitmq_url = (rabbitmq_url or "").strip() or None
        self.rabbitmq_queue = rabbitmq_queue

        os.makedirs(self.save_dir, exist_ok=True)
        self.output_file = os.path.join(self.save_dir, "latest_logs.tar.gz")

        logger.info(
            "Initialized: log_file=%s save_dir=%s interval=%ss tail_lines=%s api_url=%s rabbitmq_url=%s queue=%s",
            self.log_file_path, self.save_dir, self.interval_seconds, self.tail_lines,
            self.api_url, self.rabbitmq_url, self.rabbitmq_queue,
        )

    # --------- Log collection ----------
    def _collect_recent_logs(self):
        """Collect logs from the last <interval_seconds> window based on timestamp parsing."""
        try:
            if not os.path.exists(self.log_file_path):
                logger.warning("Log file not found yet: %s", self.log_file_path)
                return []

            with open(self.log_file_path, "r", errors="ignore") as f:
                recent_lines = tailer.tail(f, self.tail_lines)

            now = datetime.now(timezone.utc).astimezone()  # local aware
            window_start = now - timedelta(seconds=self.interval_seconds)

            picked = []
            for line in recent_lines:
                dt = parse_dt_safe(line)
                if not dt:
                    # If we can't parse, conservatively include only if within this interval by file tail proximity.
                    # But to stay safe, skip unparseable lines (avoid false positives).
                    continue

                # make dt comparable (assume local if naive)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=now.tzinfo)

                if window_start <= dt <= now:
                    picked.append(line if line.endswith("\n") else line + "\n")

            logger.info("Collected %d lines from last %ds", len(picked), self.interval_seconds)
            return picked
        except Exception as e:
            logger.error("Error reading logs: %s", e)
            return []

    def _create_tar_gz(self, lines: list[str]):
        """Create tar.gz containing a single file logs.log with collected lines."""
        try:
            if os.path.exists(self.output_file):
                os.remove(self.output_file)

            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as tf:
                tf.write("".join(lines))
                temp_log_path = tf.name

            with tarfile.open(self.output_file, "w:gz") as tar:
                tar.add(temp_log_path, arcname="logs.log")

            os.remove(temp_log_path)
            size = os.path.getsize(self.output_file)
            logger.info("Created %s (%d bytes)", self.output_file, size)
            return True
        except Exception as e:
            logger.error("Error creating tar.gz: %s", e)
            return False

    # --------- Publishers ----------
    def _send_http_api(self):
        if not self.api_url:
            return False

        try:
            with open(self.output_file, "rb") as f:
                files = {"file": ("latest_logs.tar.gz", f, "application/gzip")}
                resp = requests.post(self.api_url, files=files, timeout=20)
            if 200 <= resp.status_code < 300:
                logger.info("HTTP API: sent successfully (status %s)", resp.status_code)
                return True
            logger.error("HTTP API failed with status %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("HTTP API error: %s", e)
        return False

    def _send_rabbitmq(self):
        if not self.rabbitmq_url:
            return False
        if pika is None:
            logger.error("pika is not installed. Cannot send to RabbitMQ.")
            return False

        try:
            with open(self.output_file, "rb") as f:
                body = f.read()

            params = pika.URLParameters(self.rabbitmq_url)
            params.heartbeat = 30
            params.blocked_connection_timeout = 30

            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=self.rabbitmq_queue, durable=True)

            props = pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/gzip",
                content_encoding="gzip",
                headers={"filename": "latest_logs.tar.gz", "created_at": datetime.utcnow().isoformat() + "Z"},
            )

            ch.basic_publish(exchange="", routing_key=self.rabbitmq_queue, body=body, properties=props)
            conn.close()
            logger.info("RabbitMQ: sent %d bytes to queue '%s'", len(body), self.rabbitmq_queue)
            return True
        except Exception as e:
            logger.error("RabbitMQ publish error: %s", e)
            return False

    # --------- Main loop ----------
    def run(self):
        logger.info("Starting Log Collector Daemon loop")
        while True:
            start_ts = time.time()
            try:
                lines = self._collect_recent_logs()
                if lines:
                    if self._create_tar_gz(lines):
                        # Prefer RabbitMQ; if not set or fails, try HTTP
                        sent = False
                        if self.rabbitmq_url:
                            sent = self._send_rabbitmq()
                        if not sent and self.api_url:
                            self._send_http_api()
                else:
                    logger.info("No matching logs in the last %d seconds", self.interval_seconds)
            except Exception as e:
                logger.error("Loop error: %s", e)

            # sleep to complete the interval boundary
            elapsed = time.time() - start_ts
            to_sleep = max(1, self.interval_seconds - int(elapsed))
            time.sleep(to_sleep)


# ----------------------- CLI -----------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Collect recent logs, bundle to tar.gz, and publish to RabbitMQ and/or HTTP."
    )

    # backward-compatible positional (optional)
    p.add_argument("pos_log_file", nargs="?", help="(positional) log file path")
    p.add_argument("pos_save_dir", nargs="?", help="(positional) directory to store bundles")

    # preferred named args
    p.add_argument("--log-file", dest="log_file", help="Log file to monitor")
    p.add_argument("--save-dir", dest="save_dir", help="Directory to write bundles")
    p.add_argument("--interval", type=int, default=60, help="Interval seconds (default: 60)")
    p.add_argument("--tail-lines", type=int, default=200, help="Tail N lines to inspect each cycle (default: 200)")

    # transports
    p.add_argument("--rabbitmq-url", help="amqp[s]://user:pass@host:port/vhost")
    p.add_argument("--rabbitmq-queue", default="logs", help="RabbitMQ queue name (default: logs)")
    p.add_argument("--api-url", help="Optional HTTP endpoint to POST the tar.gz")

    args = p.parse_args()

    # Resolve required paths (prefer named flags)
    log_file = args.log_file or args.pos_log_file
    save_dir = args.save_dir or args.pos_save_dir

    if not log_file or not save_dir:
        print("Usage:")
        print("  python log_collector_daemon.py --log-file /path/to/log --save-dir /path/to/dir [--rabbitmq-url ...] [--api-url ...]")
        print("  (positional fallback also supported)")
        sys.exit(1)

    return {
        "log_file": log_file,
        "save_dir": save_dir,
        "interval": args.interval,
        "tail_lines": args.tail_lines,
        "api_url": args.api_url,
        "rabbitmq_url": args.rabbitmq_url,
        "rabbitmq_queue": args.rabbitmq_queue,
    }


def main():
    cfg = parse_args()
    daemon = LogCollectorDaemon(
        log_file_path=cfg["log_file"],
        save_dir=cfg["save_dir"],
        interval_seconds=cfg["interval"],
        tail_lines=cfg["tail_lines"],
        api_url=cfg["api_url"],
        rabbitmq_url=cfg["rabbitmq_url"],
        rabbitmq_queue=cfg["rabbitmq_queue"],
    )
    daemon.run()


if __name__ == "__main__":
    main()
