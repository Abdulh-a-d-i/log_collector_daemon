#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import socket
import platform
import logging
import argparse
import subprocess
from datetime import datetime, timedelta, timezone

import tailer
import pika
import json
import requests

# ----------------------- Logging -----------------------
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

def write_txt_with_header(lines: list[str], output_file: str, node_info: dict):
    """Write logs to .txt file with node info header"""
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Node ID: {node_info['node_id']}\n")
            f.write(f"Hostname: {node_info['hostname']}\n")
            f.write(f"OS: {node_info['os']}\n")
            f.write(f"Log Path: {node_info['log_path']}\n")
            f.write(f"Application: {node_info['application']}\n")
            f.write("---- BEGIN LOGS ----\n")
            f.writelines(lines)
        logger.info("Wrote log file %s", output_file)
        return True
    except Exception as e:
        logger.error("Error writing .txt file: %s", e)
        return False

# ----------------------- Core -----------------------
class LogCollectorDaemon:
    def __init__(self, log_file_path, save_dir, interval_seconds=60,
                 tail_lines=200, rabbitmq_url=None, rabbitmq_queue="logs",
                 control_queue="control", application="system"):
        self.log_file_path = os.path.abspath(log_file_path)
        self.save_dir = os.path.abspath(save_dir)
        self.interval_seconds = max(5, int(interval_seconds))
        self.tail_lines = max(10, int(tail_lines))
        self.rabbitmq_url = rabbitmq_url
        self.rabbitmq_queue = rabbitmq_queue
        self.control_queue = control_queue
        self.application = application

        os.makedirs(self.save_dir, exist_ok=True)
        self.output_file = os.path.join(self.save_dir, "latest_logs.txt")
        self.node_info = get_node_info(self.log_file_path, self.application)

        logger.info("Initialized logcollector: log_file=%s save_dir=%s interval=%s queue=%s control=%s",
            self.log_file_path, self.save_dir, self.interval_seconds,
            self.rabbitmq_queue, self.control_queue)

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

    def _send_rabbitmq(self):
        if not self.rabbitmq_url:
            return False
        try:
            with open(self.output_file, "rb") as f:
                body = f.read()

            params = pika.URLParameters(self.rabbitmq_url)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=self.rabbitmq_queue, durable=True)

            props = pika.BasicProperties(
                delivery_mode=2,
                content_type="text/plain",
                headers=self.node_info,
            )

            ch.basic_publish(exchange="", routing_key=self.rabbitmq_queue, body=body, properties=props)
            conn.close()
            logger.info("RabbitMQ: sent %d bytes to queue '%s'", len(body), self.rabbitmq_queue)
            return True
        except Exception as e:
            logger.error("RabbitMQ publish error: %s", e)
            return False

    def _listen_for_commands(self):
        """Listen to control queue for uninstall command"""
        try:
            params = pika.URLParameters(self.rabbitmq_url)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=self.control_queue, durable=True)

            def callback(ch_, method, properties, body):
                try:
                    msg = json.loads(body.decode())
                    if msg.get("command") == "uninstall" and msg.get("target_id") == self.node_info["node_id"]:
                        logger.warning("Received uninstall command for this node!")
                        subprocess.Popen(["/bin/bash", "uninstall.sh"])
                        os._exit(0)
                except Exception as e:
                    logger.error("Error handling control message: %s", e)

            ch.basic_consume(queue=self.control_queue, on_message_callback=callback, auto_ack=True)
            logger.info("Started listening for control commands on queue %s", self.control_queue)
            ch.start_consuming()
        except Exception as e:
            logger.error("Control listener error: %s", e)

    def run(self):
        # Run command listener in a separate process/thread
        import threading
        t = threading.Thread(target=self._listen_for_commands, daemon=True)
        t.start()

        logger.info("Starting Log Collector loop")
        while True:
            start_ts = time.time()
            try:
                lines = self._collect_recent_logs()
                if lines:
                    if write_txt_with_header(lines, self.output_file, self.node_info):
                        self._send_rabbitmq()
                else:
                    logger.info("No logs collected this cycle")
            except Exception as e:
                logger.error("Loop error: %s", e)

            elapsed = time.time() - start_ts
            to_sleep = max(1, self.interval_seconds - int(elapsed))
            time.sleep(to_sleep)

# ----------------------- CLI -----------------------
def parse_args():
    p = argparse.ArgumentParser(description="Collect logs and send to RabbitMQ, with control listener")
    p.add_argument("--log-file", required=True, help="Log file to monitor")
    p.add_argument("--save-dir", required=True, help="Directory to write txt files")
    p.add_argument("--interval", type=int, default=60, help="Interval seconds")
    p.add_argument("--tail-lines", type=int, default=200, help="Lines from tail")
    p.add_argument("--rabbitmq-url", required=True, help="RabbitMQ connection URL")
    p.add_argument("--rabbitmq-queue", default="logs", help="RabbitMQ log queue")
    p.add_argument("--control-queue", default="control", help="RabbitMQ control queue")
    p.add_argument("--application", default="system", help="Application name for logs")
    return p.parse_args()

def main():
    args = parse_args()
    daemon = LogCollectorDaemon(
        log_file_path=args.log_file,
        save_dir=args.save_dir,
        interval_seconds=args.interval,
        tail_lines=args.tail_lines,
        rabbitmq_url=args.rabbitmq_url,
        rabbitmq_queue=args.rabbitmq_queue,
        control_queue=args.control_queue,
        application=args.application,
    )
    daemon.run()

if __name__ == "__main__":
    main()
