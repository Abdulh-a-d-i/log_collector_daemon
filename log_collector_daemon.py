#!/usr/bin/env python3
import subprocess
import signal
import os
import time
from flask import Flask, request, jsonify

app = Flask(__name__)
LIVE_PROCESS = None  # global reference to the subprocess
PORT = 8754

@app.route("/control", methods=["POST"])
def control():
    """
    Accepts control commands like start_live_logs / stop_live_logs
    """
    global LIVE_PROCESS
    data = request.get_json(force=True)
    cmd = data.get("command")

    if cmd == "start_live_logs":
        if LIVE_PROCESS and LIVE_PROCESS.poll() is None:
            return jsonify({"status": "already_running"}), 200

        log_file = data.get("log_file", "/var/log/syslog")
        server_url = data.get("server_url")
        node_id = data.get("node_id", os.uname().nodename)

        if not server_url:
            return jsonify({"error": "Missing server_url"}), 400

        # Spawn the live log script
        LIVE_PROCESS = subprocess.Popen(
            ["python3", "livelogs.py", log_file, server_url, node_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return jsonify({"status": "started", "pid": LIVE_PROCESS.pid}), 200

    elif cmd == "stop_live_logs":
        if LIVE_PROCESS and LIVE_PROCESS.poll() is None:
            LIVE_PROCESS.terminate()
            try:
                LIVE_PROCESS.wait(timeout=3)
            except subprocess.TimeoutExpired:
                LIVE_PROCESS.kill()
            LIVE_PROCESS = None
            return jsonify({"status": "stopped"}), 200
        return jsonify({"status": "no_active_process"}), 200

    return jsonify({"error": "unknown command"}), 400


if __name__ == "__main__":
    print(f"[log_collector_daemon] Starting HTTP server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
