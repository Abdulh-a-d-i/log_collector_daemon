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
import pika
import json
from typing import Dict, Optional, List
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("[WARNING] psycopg2 not available - suppression rules disabled")
try:
    from alert_manager import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    
try:
    from process_monitor import ProcessMonitor
    PROCESS_MONITOR_AVAILABLE = True
except ImportError:
    PROCESS_MONITOR_AVAILABLE = False

try:
    from suppression_checker import SuppressionRuleChecker
    SUPPRESSION_CHECKER_AVAILABLE = True
except ImportError:
    SUPPRESSION_CHECKER_AVAILABLE = False
    print("[WARNING] suppression_checker not available - suppression rules disabled")

try:
    from telemetry_queue import TelemetryQueue
    from telemetry_poster import TelemetryPoster
    TELEMETRY_MODULES_AVAILABLE = True
except ImportError as e:
    TELEMETRY_MODULES_AVAILABLE = False
    print(f"[WARNING] Telemetry modules not available: {e}")

try:
    from config_store import init_config, get_config, ConfigStore
    CONFIG_STORE_AVAILABLE = True
except ImportError as e:
    CONFIG_STORE_AVAILABLE = False
    print(f"[WARNING] Config store not available: {e}")

# Daemon version and startup tracking
DAEMON_VERSION = "1.1.0"
DAEMON_START_TIME = time.time()

RABBITMQ_URL = "amqp://resolvix_user:resolvix4321@140.238.255.110:5672";
QUEUE_NAME = "error_logs_queue";

def send_to_rabbitmq(payload):
    try:
        # Parse connection URL
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        
        # Declare queue
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        
        # Send message
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        
        connection.close()
        logger.info("✅ Log sent to RabbitMQ")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send to RabbitMQ: {e}")
        return False

class BackendLogHandler(logging.Handler):
    """Custom log handler that sends ERROR and CRITICAL logs to backend"""
    
    def __init__(self, backend_url, node_id):
        super().__init__()
        self.backend_url = backend_url
        self.node_id = node_id
        self.setLevel(logging.ERROR)
    
    def emit(self, record):
        try:
            log_entry = self.format(record)
            
            # Send to backend via RabbitMQ (reuse existing mechanism)
            payload = {
                'node_id': self.node_id,
                'source': 'resolvix_daemon',
                'priority': 'critical' if record.levelno >= logging.CRITICAL else 'high',
                'log_line': log_entry,
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname
            }
            
            # Use RabbitMQ for immediate delivery
            send_to_rabbitmq(payload)
            
        except Exception:
            # Don't crash daemon if backend is unreachable
            # Silently fail - the error is already logged to file
            pass

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
DEFAULT_WS_PORT = 8755  # port where livelogs.py will host WS
DEFAULT_TELEMETRY_WS_PORT = 8756  # port for telemetry WS
DEFAULT_CONTROL_PORT = 8754  # this daemon's control HTTP port
DEFAULT_TELEMETRY_INTERVAL = 3  # telemetry collection interval in seconds
DEFAULT_HEARTBEAT_INTERVAL = 30  # heartbeat interval in seconds
ERROR_KEYWORDS = [
    "emerg", "emergency", "alert", "crit", "critical",
    "err", "error", "fail", "failed", "failure", "panic", "fatal"
]

# -------- helpers --------
def get_node_id():
    """
    Get the node identifier (IP address).
    Never returns 127.0.0.1 or localhost IPs.
    """
    # Method 1: Try to get IP by connecting to external address (doesn't actually send data)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        # Connect to Google DNS (8.8.8.8) - doesn't send any data
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != "127.0.0.1" and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    
    # Method 2: Try hostname resolution
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and ip != "127.0.0.1" and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    
    # Method 3: Get all network interfaces and pick first non-localhost
    try:
        import netifaces
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get('addr')
                    if ip and ip != "127.0.0.1" and not ip.startswith("127."):
                        return ip
    except ImportError:
        pass  # netifaces not available, skip this method
    except Exception:
        pass
    
    # Method 4: Use hostname as last resort (not ideal but better than 127.0.0.1)
    try:
        hostname = socket.gethostname()
        if hostname and hostname != "localhost":
            return hostname
    except Exception:
        pass
    
    # If all else fails, return a clear error indicator
    logger.warning("Could not determine node IP address. Using 'unknown-node' as identifier.")
    return "unknown-node"

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

def get_log_label(log_path: str) -> str:
    """
    Determine log_label from log file path
    Examples:
      /var/log/apache2/error.log -> apache_errors
      /var/log/nginx/error.log -> nginx_errors
      /var/log/mysql/error.log -> mysql_errors
      /var/log/syslog -> system
    """
    path_lower = log_path.lower()

    # Map patterns to labels
    if 'apache' in path_lower:
        return 'apache_errors'
    elif 'nginx' in path_lower:
        return 'nginx_errors'
    elif 'mysql' in path_lower or 'mariadb' in path_lower:
        return 'mysql_errors'
    elif 'postgresql' in path_lower or 'postgres' in path_lower:
        return 'postgresql_errors'
    elif 'syslog' in path_lower or 'messages' in path_lower:
        return 'system'
    elif 'kern' in path_lower:
        return 'kernel'
    elif 'auth' in path_lower:
        return 'authentication'
    else:
        # Extract from filename
        filename = os.path.basename(log_path)
        label = filename.replace('.log', '').replace('.', '_')
        return label or 'unlabeled'


def determine_priority(log_line: str, severity: str) -> str:
    """
    Determine priority level based on severity and keywords
    Returns: 'critical', 'high', 'medium', 'low'
    """
    log_lower = log_line.lower()

    # Critical keywords
    CRITICAL_KEYWORDS = [
        'fatal', 'panic', 'critical', 'emergency', 'segmentation fault',
        'core dump', 'out of memory', 'system halt', 'kernel panic'
    ]

    # High keywords
    HIGH_KEYWORDS = [
        'error', 'failed', 'failure', 'exception', 'traceback',
        'denied', 'refused', 'timeout', 'unreachable'
    ]

    # Check keywords first (override severity)
    if any(kw in log_lower for kw in CRITICAL_KEYWORDS):
        return 'critical'

    if any(kw in log_lower for kw in HIGH_KEYWORDS):
        return 'high'

    # Check severity
    if severity and severity.lower() in ['fatal', 'critical', 'emergency']:
        return 'critical'
    elif severity and severity.lower() in ['error', 'err', 'failure']:
        return 'high'
    elif severity and severity.lower() in ['warning', 'warn']:
        return 'medium'
    else:
        return 'low'

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

# -------- Helper function to get machine UUID --------
def get_machine_uuid(api_url=None):
    """
    Get the machine's registered UUID from system_info.json or backend API.
    Returns the UUID string or generates one from MAC as fallback.
    """
    # Try reading from system_info.json
    try:
        if os.path.exists('system_info.json'):
            with open('system_info.json', 'r') as f:
                data = json.load(f)
                if 'id' in data:
                    logger.info(f"[MachineUUID] Loaded from system_info.json: {data['id']}")
                    return data['id']
    except Exception as e:
        logger.warning(f"[MachineUUID] Could not read system_info.json: {e}")
    
    # Try fetching from backend API using hostname/IP
    if api_url:
        try:
            hostname = socket.gethostname()
            ip_address = get_node_id()
            
            # Query backend for machine by hostname or IP
            base_url = api_url.rsplit('/api/', 1)[0] if '/api/' in api_url else api_url
            response = requests.get(
                f"{base_url}/api/system_info",
                params={'hostname': hostname},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    machine_id = data[0].get('id')
                    if machine_id:
                        logger.info(f"[MachineUUID] Fetched from backend: {machine_id}")
                        return machine_id
                elif isinstance(data, dict) and 'id' in data:
                    logger.info(f"[MachineUUID] Fetched from backend: {data['id']}")
                    return data['id']
        except Exception as e:
            logger.warning(f"[MachineUUID] Could not fetch from backend: {e}")
    
    # Fallback: generate UUID from MAC address
    fallback_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
    logger.warning(f"[MachineUUID] Using fallback UUID from MAC: {fallback_uuid}")
    return fallback_uuid

# -------- Daemon class --------
class LogCollectorDaemon:
    def __init__(self, log_files, api_url, ws_port=DEFAULT_WS_PORT, 
                 telemetry_ws_port=DEFAULT_TELEMETRY_WS_PORT, node_id=None, 
                 interval=1, tail_lines=200, telemetry_interval=DEFAULT_TELEMETRY_INTERVAL,
                 heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
                 db_host=None, db_name=None, db_user=None, db_password=None, db_port=5432,
                 telemetry_backend_url=None, telemetry_jwt_token=None):
        # Store log files as list of dicts with metadata
        self.log_files = []
        for i, log_file in enumerate(log_files):
            self.log_files.append({
                'id': f"file_{i+1:03d}",
                'path': os.path.abspath(log_file),
                'label': os.path.basename(log_file).replace('.log', '').replace('.', '_') or f'log_{i+1}',
                'priority': 'high',
                'enabled': True,
                'created_at': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat()
            })
        
        # Add daemon's own log file to monitoring (self-monitoring)
        daemon_log_path = os.path.abspath(LOG_FILE)
        if not any(f['path'] == daemon_log_path for f in self.log_files):
            self.log_files.append({
                'id': f"file_{len(self.log_files) + 1:03d}",
                'path': daemon_log_path,
                'label': 'resolvix_daemon',
                'priority': 'critical',
                'enabled': True,
                'auto_monitor': True,  # Cannot be disabled
                'description': 'Resolvix daemon internal logs',
                'created_at': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat()
            })
            logger.info(f"[Self-Monitoring] Added daemon log to monitoring: {daemon_log_path}")
        
        # Keep backward compatibility - use first file for livelogs
        self.log_file = self.log_files[0]['path'] if self.log_files else None
        
        self.api_url = api_url.rstrip("/") if api_url else None
        self.ws_port = int(ws_port)
        self.telemetry_ws_port = int(telemetry_ws_port)
        self.node_id = node_id or get_node_id()
        self.interval = interval
        self.tail_lines = tail_lines
        self.telemetry_interval = telemetry_interval
        self.heartbeat_interval = heartbeat_interval
        self._stop_flag = threading.Event()
        self._monitor_threads = []  # List of monitoring threads (one per file)
        self._heartbeat_thread = None
        self._live_proc = None  # subprocess for livelogs.py
        self._telemetry_proc = None  # subprocess for telemetry_ws.py
        self._live_lock = threading.Lock()
        self._telemetry_lock = threading.Lock()
        
        # Get machine UUID
        self.machine_uuid = get_machine_uuid(self.api_url)

        # compiled keyword regex for faster matching
        kw = "|".join(re.escape(k) for k in ERROR_KEYWORDS)
        self._err_re = re.compile(rf"\b({kw})\b", re.IGNORECASE)
        
        # Database connection and suppression checker
        self.db_connection = None
        self.suppression_checker = None
        if db_host and db_name and db_user and db_password and PSYCOPG2_AVAILABLE and SUPPRESSION_CHECKER_AVAILABLE:
            try:
                self.db_connection = psycopg2.connect(
                    host=db_host,
                    database=db_name,
                    user=db_user,
                    password=db_password,
                    port=db_port
                )
                self.suppression_checker = SuppressionRuleChecker(self.db_connection, cache_ttl=60)
                logger.info("[SuppressionChecker] Enabled with database connection")
            except Exception as e:
                logger.error(f"[SuppressionChecker] Failed to initialize: {e}")
                self.db_connection = None
                self.suppression_checker = None
        else:
            if not (db_host and db_name and db_user and db_password):
                logger.info("[SuppressionChecker] Disabled (no database credentials provided)")
            elif not PSYCOPG2_AVAILABLE:
                logger.warning("[SuppressionChecker] Disabled (psycopg2 not installed)")
            elif not SUPPRESSION_CHECKER_AVAILABLE:
                logger.warning("[SuppressionChecker] Disabled (suppression_checker module not available)")
        
        # Initialize Alert Manager
        if ALERT_MANAGER_AVAILABLE:
            try:
                self.alert_manager = AlertManager(
                    backend_url=self.api_url,
                    hostname=socket.gethostname(),
                    ip_address=self.node_id
                )
                logger.info("[AlertManager] Smart alerting enabled")
            except Exception as e:
                logger.error(f"[AlertManager] Failed to initialize: {e}")
                self.alert_manager = None
        else:
            self.alert_manager = None
            logger.info("[AlertManager] Disabled (module not available)")
        
        # Initialize Process Monitor
        if PROCESS_MONITOR_AVAILABLE:
            try:
                self.process_monitor = ProcessMonitor(history_size=1000)
                logger.info("[ProcessMonitor] Process monitoring enabled")
            except Exception as e:
                logger.error(f"[ProcessMonitor] Failed to initialize: {e}")
                self.process_monitor = None
        else:
            self.process_monitor = None
            logger.info("[ProcessMonitor] Disabled (module not available)")
        
        # Initialize Telemetry Queue and Poster
        self.telemetry_queue = None
        self.telemetry_poster = None
        self.telemetry_post_thread = None
        self.telemetry_backend_url = telemetry_backend_url or self.api_url
        self.telemetry_jwt_token = telemetry_jwt_token
        
        if TELEMETRY_MODULES_AVAILABLE and self.telemetry_backend_url:
            try:
                self.telemetry_queue = TelemetryQueue(
                    db_path='/var/lib/resolvix/telemetry_queue.db',
                    max_size=1000
                )
                logger.info("[Daemon] Telemetry queue initialized")
                
                self.telemetry_poster = TelemetryPoster(
                    backend_url=self.telemetry_backend_url,
                    jwt_token=self.telemetry_jwt_token,
                    retry_backoff=[5, 15, 60],
                    timeout=10
                )
                logger.info(f"[Daemon] Telemetry poster initialized (backend={self.telemetry_backend_url})")
            except Exception as e:
                logger.error(f"[Daemon] Failed to initialize telemetry system: {e}")
                self.telemetry_queue = None
                self.telemetry_poster = None
        else:
            if not TELEMETRY_MODULES_AVAILABLE:
                logger.info("[Daemon] Telemetry modules not available")
            elif not self.telemetry_backend_url:
                logger.info("[Daemon] Telemetry disabled (no backend URL)")

    def start(self):
        # starts background threads for monitoring
        logger.info(f"Starting log monitoring for {len(self.log_files)} file(s)")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Node ID: {self.node_id}")
        
        # Start a monitoring thread for each log file
        for log_file_config in self.log_files:
            thread = threading.Thread(
                target=self._monitor_loop,
                args=(log_file_config,),
                daemon=True,
                name=f"Monitor-{log_file_config['label']}"
            )
            thread.start()
            self._monitor_threads.append(thread)
            logger.info(f"Started monitoring: {log_file_config['path']} [{log_file_config['label']}]")
        
        # start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info(f"Heartbeat started (interval: {self.heartbeat_interval}s)")
        
        # start telemetry POST thread if enabled
        if self.telemetry_queue and self.telemetry_poster:
            self.telemetry_post_thread = threading.Thread(
                target=self._telemetry_post_loop,
                daemon=True,
                name='TelemetryPoster'
            )
            self.telemetry_post_thread.start()
            logger.info("[Daemon] Telemetry POST thread started")

    def stop(self):
        self._stop_flag.set()
        
        # Wait for all monitor threads
        for thread in self._monitor_threads:
            if thread:
                thread.join(timeout=2)
        
        # Stop heartbeat
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)
        
        # ensure live proc stopped
        self.stop_livelogs()
        self.stop_telemetry()
        # close database connection
        if self.db_connection:
            try:
                self.db_connection.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")

    def _read_last_lines(self, filepath, lines=200):
        try:
            with open(filepath, "r", errors="ignore") as f:
                return tail_lines_from_file(f, lines)
        except Exception:
            return []
    
    def _telemetry_post_loop(self):
        """
        Background thread to POST queued telemetry snapshots.
        Runs continuously while daemon is running.
        """
        logger.info("[TelemetryPoster] POST loop started")
        
        while not self._stop_flag.is_set():
            try:
                if not self.telemetry_queue or not self.telemetry_poster:
                    logger.warning("[TelemetryPoster] Queue or poster not initialized, sleeping...")
                    time.sleep(60)
                    continue
                
                # Get batch of snapshots to send
                snapshots = self.telemetry_queue.dequeue(limit=10)
                
                if not snapshots:
                    # Queue empty - wait before checking again
                    time.sleep(60)
                    continue
                
                logger.info(f"[TelemetryPoster] Processing {len(snapshots)} queued snapshots")
                
                # Process each snapshot
                for snapshot_id, payload, retry_count in snapshots:
                    try:
                        # POST with retry
                        success = self.telemetry_poster.post_with_retry(payload, retry_count)
                        
                        if success:
                            # Remove from queue
                            self.telemetry_queue.mark_sent(snapshot_id)
                        else:
                            # Mark as failed (will retry or drop based on retry count)
                            self.telemetry_queue.mark_failed(snapshot_id, max_retries=3)
                    
                    except Exception as e:
                        logger.error(f"[TelemetryPoster] Error processing snapshot {snapshot_id}: {e}")
                        self.telemetry_queue.mark_failed(snapshot_id, max_retries=3)
                
                # Log queue statistics every iteration
                queue_size = self.telemetry_queue.get_queue_size()
                if queue_size > 0:
                    logger.info(f"[TelemetryPoster] Queue size: {queue_size}")
                
                # Wait before next batch
                time.sleep(60)
            
            except Exception as e:
                logger.error(f"[TelemetryPoster] Error in POST loop: {e}")
                time.sleep(60)
        
        logger.info("[TelemetryPoster] POST loop stopped")

    def _heartbeat_loop(self):
        """Send periodic heartbeat to backend"""
        logger.info("Heartbeat loop started")
        
        # Extract base URL (remove /api/ticket if present)
        if self.api_url:
            base_url = self.api_url.replace('/api/ticket', '').replace('/api/logs', '')
            heartbeat_url = f"{base_url}/api/heartbeat"
        else:
            heartbeat_url = None
        
        while not self._stop_flag.is_set():
            try:
                if heartbeat_url:
                    payload = {
                        "node_id": self.node_id,
                        "status": "online",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                    try:
                        resp = requests.post(heartbeat_url, json=payload, timeout=5)
                        if resp.status_code >= 400:
                            logger.warning(f"Heartbeat failed: {resp.status_code}")
                    except Exception as e:
                        logger.error(f"Heartbeat error: {e}")
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
            
            # Wait for next heartbeat
            self._stop_flag.wait(timeout=self.heartbeat_interval)
    
    def _monitor_loop(self, log_file_config):
        """
        Monitor a single log file.
        This runs in its own thread.
        
        Args:
            log_file_config: Dict with 'path', 'label', 'priority'
        """
        log_file_path = log_file_config['path']
        label = log_file_config['label']
        priority = log_file_config['priority']
        
        # Wait until file exists; do not crash if missing.
        while not os.path.exists(log_file_path) and not self._stop_flag.is_set():
            logger.warning(f"Waiting for log file: {log_file_path}")
            time.sleep(5)
        
        if self._stop_flag.is_set():
            return

        logger.info(f"Log file found, starting monitoring: {log_file_path}")
        try:
            with open(log_file_path, "r", errors="ignore") as f:
                # go to EOF
                f.seek(0, os.SEEK_END)
                logger.info(f"Monitoring started [{label}]: {log_file_path}")
                
                while not self._stop_flag.is_set():
                    # Check if this file is still enabled
                    if not log_file_config.get('enabled', True):
                        time.sleep(5)  # Sleep longer when disabled
                        continue
                    line = f.readline()
                    if not line:
                        time.sleep(self.interval)
                        continue
                    
                    # Skip daemon's own operational messages to prevent recursive detection
                    # This prevents infinite log feedback loops
                    if any(marker in line for marker in [
                        'Issue detected',
                        '[SUPPRESSED]',
                        'Error checking suppression',
                        'Backend error reporting',
                        'Daemon initialization',
                        'Configuration store',
                        'Health check',
                        'Component',
                        'log_collector_daemon.py',
                        '[AlertManager]',
                        '[ProcessMonitor]',
                        '[TelemetryQueue]',
                        '[TelemetryPoster]',
                        '[Config]',
                        '[MachineUUID]',
                        '[Self-Monitoring]',
                        'Resolvix Daemon Starting',
                        'Log entry sent to RabbitMQ',
                        'sent to RabbitMQ',
                        'Control command received',
                        'Heartbeat',
                        'Livelogs',
                        'Telemetry'
                    ]):
                        continue
                    
                    if self._err_re.search(line):
                        severity = detect_severity(line)
                        ts = parse_timestamp(line)
                        
                        # Determine log_label from file path (override config label if smarter)
                        detected_label = get_log_label(log_file_path)
                        
                        # Determine priority dynamically from line content and severity
                        detected_priority = determine_priority(line, severity)
                        
                        payload = {
                            "timestamp": ts,
                            "system_ip": self.node_id,
                            "log_path": log_file_path,
                            "log_label": detected_label,
                            "application": detected_label,
                            "log_line": line.rstrip("\n"),
                            "severity": severity,
                            "priority": detected_priority
                        }
                        logger.debug(f"Issue detected [{severity}|{detected_priority}] in {detected_label}: {line.strip()[:100]}")
                        
                        # ============================================
                        # CHECK SUPPRESSION RULES BEFORE SENDING
                        # ============================================
                        if self.suppression_checker:
                            try:
                                should_suppress, matched_rule = self.suppression_checker.should_suppress(
                                    line.rstrip("\n"),
                                    self.node_id
                                )
                                
                                if should_suppress:
                                    logger.info(
                                        f"[SUPPRESSED] [{label}] Error suppressed by rule: {matched_rule['name']} (ID: {matched_rule['id']})"
                                    )
                                    logger.debug(f"[SUPPRESSED] [{label}] Match text: {matched_rule['match_text']}")
                                    logger.debug(f"[SUPPRESSED] [{label}] Error line: {line.strip()[:200]}")
                                    continue  # Skip sending to RabbitMQ
                            except Exception as e:
                                logger.error(f"[SUPPRESSED] [{label}] Error checking suppression rules: {e}")
                                # On error, proceed with sending (fail-open behavior)
                        
                        # best-effort post; don't crash daemon if fails
                        if self.api_url:
                            success = send_to_rabbitmq(payload)
                            if success:
                                logger.info(f"✅ [{label}] Log entry sent to RabbitMQ successfully")
                            else:
                                logger.error(f"❌ [{label}] Failed to send log to RabbitMQ")
                        else:
                            logger.info(f"[{label}] No API configured, logging locally: {json.dumps(payload)}")
        except Exception as e:
            logger.error(f"Monitor loop exception for {log_file_path}: {e}", exc_info=True)

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
                "--interval", str(self.telemetry_interval),
                "--machine-uuid", self.machine_uuid
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
        
        status = {
            "node_id": self.node_id,
            "log_file": self.log_file,  # Keep for backward compatibility (first file)
            "monitored_files": {
                "count": len(self.log_files),
                "files": [
                    {
                        "path": f["path"],
                        "label": f["label"],
                        "priority": f["priority"]
                    }
                    for f in self.log_files
                ]
            },
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
        
        # Add suppression statistics if available
        if self.suppression_checker:
            try:
                status["suppression_rules"] = {
                    "enabled": True,
                    "statistics": self.suppression_checker.get_statistics()
                }
            except Exception as e:
                logger.error(f"Error getting suppression statistics: {e}")
                status["suppression_rules"] = {"enabled": True, "error": str(e)}
        else:
            status["suppression_rules"] = {"enabled": False}
        
        return status

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

    @app.route("/api/control", methods=["POST"])
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
    def health_check():
        """Enhanced health check endpoint with component status"""
        uptime = time.time() - DAEMON_START_TIME
        
        # Check component health
        components = {
            'log_collector': 'running' if daemon._monitor_threads and any(t.is_alive() for t in daemon._monitor_threads) else 'stopped',
            'livelogs_ws': 'running' if daemon._live_proc and daemon._live_proc.poll() is None else 'stopped',
            'telemetry_ws': 'running' if daemon._telemetry_proc and daemon._telemetry_proc.poll() is None else 'stopped',
            'control_api': 'running'  # If we're responding, API is running
        }
        
        # Check optional components
        if daemon.process_monitor:
            components['process_monitor'] = 'running'
        if daemon.suppression_checker:
            components['suppression_checker'] = 'running'
        
        all_healthy = all(status == 'running' for status in components.values())
        status_code = HTTPStatus.OK if all_healthy else HTTPStatus.SERVICE_UNAVAILABLE
        
        response = {
            'status': 'healthy' if all_healthy else 'degraded',
            'service': 'resolvix',
            'version': DAEMON_VERSION,
            'uptime_seconds': int(uptime),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'node_id': daemon.node_id,
            'ports': {
                'control_api': daemon._control_port if hasattr(daemon, '_control_port') else DEFAULT_CONTROL_PORT,
                'livelogs_ws': daemon.ws_port,
                'telemetry_ws': daemon.telemetry_ws_port
            },
            'components': components,
            'monitoring': {
                'log_files': len(daemon.log_files),
                'log_sources': [f['path'] for f in daemon.log_files]
            }
        }
        
        if not all_healthy:
            response['errors'] = [
                f'{name} is {status}' 
                for name, status in components.items() 
                if status != 'running'
            ]
        
        return jsonify(response), status_code

    @app.route("/api/health", methods=["GET"])
    def api_health():
        """Legacy health endpoint - redirects to /health"""
        return health_check()
    
    @app.route("/api/status", methods=["GET"])
    def status():
        return jsonify(daemon.get_status()), HTTPStatus.OK
    
    # -------- Process Monitoring Endpoints --------
    @app.route("/api/processes", methods=["GET"])
    def get_processes():
        """GET /api/processes - Returns current top processes sorted by CPU or memory"""
        if not daemon.process_monitor:
            return jsonify({"error": "Process monitoring not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            # Get query parameters
            limit = request.args.get('limit', 30, type=int)
            sort_by = request.args.get('sortBy', 'cpu', type=str)
            
            # Validate parameters
            if limit < 1 or limit > 100:
                return jsonify({"error": "Limit must be between 1 and 100"}), HTTPStatus.BAD_REQUEST
            
            if sort_by not in ['cpu', 'memory']:
                sort_by = 'cpu'
            
            metrics = daemon.process_monitor.get_process_metrics(limit=limit, sort_by=sort_by)
            return jsonify(metrics), HTTPStatus.OK
        except Exception as e:
            logger.error(f"Failed to get process metrics: {e}")
            return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    @app.route("/api/processes/<int:pid>", methods=["GET"])
    def get_process_details(pid):
        """GET /api/processes/{pid} - Returns detailed info about specific process"""
        if not daemon.process_monitor:
            return jsonify({"error": "Process monitoring not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            details = daemon.process_monitor.get_process_details(pid)
            if details.get('success'):
                return jsonify(details), HTTPStatus.OK
            else:
                return jsonify(details), HTTPStatus.NOT_FOUND
        except Exception as e:
            logger.error(f"Failed to get process details for PID {pid}: {e}")
            return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    @app.route("/api/processes/<int:pid>/kill", methods=["POST"])
    def kill_process_endpoint(pid):
        """POST /api/processes/{pid}/kill - Kills a process"""
        if not daemon.process_monitor:
            return jsonify({"error": "Process monitoring not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            data = request.get_json() or {}
            force = data.get('force', False)
            
            result = daemon.process_monitor.kill_process(pid, force)
            
            if result['success']:
                return jsonify(result), HTTPStatus.OK
            else:
                return jsonify(result), HTTPStatus.BAD_REQUEST
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    @app.route("/api/processes/<int:pid>/history", methods=["GET"])
    def get_process_history_endpoint(pid):
        """GET /api/processes/{pid}/history?hours=24 - Returns historical metrics"""
        if not daemon.process_monitor:
            return jsonify({"error": "Process monitoring not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            hours = request.args.get('hours', 24, type=int)
            history = daemon.process_monitor.get_process_history(pid, hours)
            return jsonify(history), HTTPStatus.OK
        except Exception as e:
            logger.error(f"Failed to get process history for PID {pid}: {e}")
            return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    @app.route("/api/processes/<int:pid>/tree", methods=["GET"])
    def get_process_tree_endpoint(pid):
        """GET /api/processes/{pid}/tree - Returns process tree (parent and children)"""
        if not daemon.process_monitor:
            return jsonify({"error": "Process monitoring not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            tree = daemon.process_monitor.get_process_tree(pid)
            if tree.get('success'):
                return jsonify(tree), HTTPStatus.OK
            else:
                return jsonify(tree), HTTPStatus.NOT_FOUND
        except Exception as e:
            logger.error(f"Failed to get process tree for PID {pid}: {e}")
            return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    # -------- Configuration Management Endpoints --------
    # Simplified endpoints for frontend (matches documentation)
    @app.route("/config/get", methods=["GET"])
    def get_config_simplified():
        """GET /config/get - Simplified config endpoint for frontend"""
        if not CONFIG_STORE_AVAILABLE:
            return jsonify({"status": "error", "error": "Config store not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            config = get_config()
            
            # Format response to match frontend expectations
            response_config = {
                "logging": {
                    "level": config.get('logging.level', 'INFO').lower(),
                    "file": config.get('logging.path', '/var/log/resolvix.log'),
                    "max_size_mb": config.get('logging.max_bytes', 10485760) / (1024 * 1024),
                    "backup_count": config.get('logging.backup_count', 5)
                },
                "heartbeat_interval": config.get('intervals.heartbeat', 30),
                "telemetry_interval": config.get('intervals.telemetry', 3),
                "control_port": config.get('ports.control', 8754),
                "livelogs_port": config.get('ports.ws', 8755),
                "telemetry_port": config.get('ports.telemetry_ws', 8756),
                "monitored_files": config.get('monitoring.log_files', [])
            }
            
            return jsonify({
                "status": "success",
                "config": response_config
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Get config error: {e}")
            return jsonify({"status": "error", "error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    @app.route("/config/update", methods=["POST"])
    def update_config_simplified():
        """POST /config/update - Simplified config update endpoint for frontend"""
        if not CONFIG_STORE_AVAILABLE:
            return jsonify({"status": "error", "error": "Config store not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            updates = request.get_json()
            
            if not updates:
                return jsonify({
                    "status": "error",
                    "error": "No updates provided"
                }), HTTPStatus.BAD_REQUEST
            
            config = get_config()
            updated_fields = []
            restarted_services = []
            
            # Handle logging updates
            if 'logging' in updates:
                if 'level' in updates['logging']:
                    new_level = updates['logging']['level'].upper()
                    
                    # Validate log level
                    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
                    if new_level not in valid_levels:
                        return jsonify({
                            "status": "error",
                            "error": f"Invalid log level. Must be one of: {', '.join(valid_levels)}",
                            "field": "logging.level"
                        }), HTTPStatus.BAD_REQUEST
                    
                    # Update config
                    config.set('logging.level', new_level)
                    updated_fields.append('logging.level')
                    
                    # Apply immediately (hot reload)
                    level_map = {
                        'DEBUG': logging.DEBUG,
                        'INFO': logging.INFO,
                        'WARNING': logging.WARNING,
                        'ERROR': logging.ERROR,
                        'CRITICAL': logging.CRITICAL
                    }
                    logging.getLogger('resolvix').setLevel(level_map[new_level])
                    logger.info(f"[Config] Logging level changed to {new_level}")
            
            # Handle heartbeat interval
            if 'heartbeat_interval' in updates:
                config.set('intervals.heartbeat', updates['heartbeat_interval'])
                updated_fields.append('heartbeat_interval')
                restarted_services.append('heartbeat')
            
            # Handle telemetry interval
            if 'telemetry_interval' in updates:
                config.set('intervals.telemetry', updates['telemetry_interval'])
                updated_fields.append('telemetry_interval')
                restarted_services.append('telemetry')
            
            # Save to disk
            config.save()
            
            return jsonify({
                "status": "success",
                "message": "Configuration updated successfully",
                "updated_fields": updated_fields,
                "restarted_services": restarted_services
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Update config error: {e}")
            return jsonify({"status": "error", "error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    # Full-featured config endpoints (backward compatibility)
    @app.route("/api/config", methods=["GET"])
    def get_configuration():
        """GET /api/config - Return current daemon configuration (non-secrets)"""
        if not CONFIG_STORE_AVAILABLE:
            return jsonify({"error": "Config store not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            config = get_config()

            # Return config without secrets
            safe_config = {
                'connectivity': {
                    'api_url': config.get('connectivity.api_url'),
                    'telemetry_backend_url': config.get('connectivity.telemetry_backend_url')
                },
                'messaging': {
                    'rabbitmq': {
                        'queue': config.get('messaging.rabbitmq.queue')
                        # Don't expose URL (contains password)
                    }
                },
                'telemetry': config.get('telemetry'),
                'monitoring': config.get('monitoring'),
                'alerts': config.get('alerts'),
                'ports': config.get('ports'),
                'intervals': config.get('intervals'),
                'logging': config.get('logging'),
                'security': config.get('security')
            }

            return jsonify({
                'success': True,
                'config': safe_config,
                'last_sync': config.last_sync.isoformat() if config.last_sync else None
            }), HTTPStatus.OK

        except Exception as e:
            logger.error(f"Get config error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/config", methods=["POST"])
    def update_configuration():
        """POST /api/config - Update daemon configuration (admin only)"""
        if not CONFIG_STORE_AVAILABLE:
            return jsonify({"error": "Config store not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            data = request.json
            if not data or 'settings' not in data:
                return jsonify({'success': False, 'error': 'Settings required'}), HTTPStatus.BAD_REQUEST

            config = get_config()
            updated = []

            # Update each setting
            for key_path, value in data['settings'].items():
                config.set(key_path, value)
                updated.append(key_path)

            # Save to disk
            config.save()

            return jsonify({
                'success': True,
                'message': f'Updated {len(updated)} settings',
                'updated': updated
            }), HTTPStatus.OK

        except Exception as e:
            logger.error(f"Update config error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/config/reload", methods=["POST"])
    def reload_configuration():
        """POST /api/config/reload - Reload configuration from backend and apply changes"""
        if not CONFIG_STORE_AVAILABLE:
            return jsonify({"error": "Config store not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        
        try:
            config = get_config()

            # Reload and get changes
            changes = config.reload()

            # Apply runtime changes
            apply_config_changes(daemon, changes)

            return jsonify({
                'success': True,
                'message': 'Configuration reloaded',
                'changes': len(changes),
                'details': {k: {'old': v[0], 'new': v[1]} for k, v in changes.items()}
            }), HTTPStatus.OK

        except Exception as e:
            logger.error(f"Reload config error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/config/schema", methods=["GET"])
    def get_configuration_schema():
        """GET /api/config/schema - Return configuration schema for validation"""
        schema = {
            'alerts.thresholds.cpu_critical.threshold': {
                'type': 'number',
                'min': 50,
                'max': 100,
                'description': 'CPU usage % for critical alerts'
            },
            'alerts.thresholds.cpu_critical.duration': {
                'type': 'number',
                'min': 60,
                'max': 3600,
                'description': 'Seconds before triggering critical alert'
            },
            'intervals.telemetry': {
                'type': 'number',
                'min': 1,
                'max': 60,
                'description': 'Telemetry collection interval in seconds'
            },
            'intervals.heartbeat': {
                'type': 'number',
                'min': 10,
                'max': 300,
                'description': 'Heartbeat interval in seconds'
            },
            'ports.control': {
                'type': 'number',
                'min': 1024,
                'max': 65535,
                'description': 'Daemon control port'
            },
            'ports.ws': {
                'type': 'number',
                'min': 1024,
                'max': 65535,
                'description': 'WebSocket port for live logs'
            },
            'ports.telemetry_ws': {
                'type': 'number',
                'min': 1024,
                'max': 65535,
                'description': 'WebSocket port for telemetry'
            },
            'logging.level': {
                'type': 'string',
                'enum': ['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                'description': 'Logging level'
            },
            'logging.max_bytes': {
                'type': 'number',
                'min': 1048576,
                'max': 104857600,
                'description': 'Maximum log file size in bytes'
            },
            'logging.backup_count': {
                'type': 'number',
                'min': 1,
                'max': 20,
                'description': 'Number of log backup files'
            },
            'telemetry.queue_max_size': {
                'type': 'number',
                'min': 100,
                'max': 10000,
                'description': 'Maximum telemetry queue size'
            },
            'security.cors_allowed_origins': {
                'type': 'string',
                'description': 'CORS allowed origins (* for all)'
            }
        }

        return jsonify({'success': True, 'schema': schema}), HTTPStatus.OK

    # -------- Monitored Files Management Endpoints --------
    @app.route("/api/monitored-files", methods=["GET"])
    def get_monitored_files():
        """GET /api/monitored-files - Get list of monitored log files"""
        try:
            files_with_metadata = []
            for i, file_config in enumerate(daemon.log_files):
                files_with_metadata.append({
                    'id': file_config.get('id', f"file_{i+1:03d}"),
                    'path': file_config['path'],
                    'label': file_config.get('label', 'unknown'),
                    'priority': file_config.get('priority', 'medium'),
                    'enabled': file_config.get('enabled', True),
                    'created_at': file_config.get('created_at', ''),
                    'last_modified': file_config.get('last_modified', ''),
                    'auto_monitor': file_config.get('auto_monitor', False)
                })
            
            return jsonify({
                'success': True,
                'files': files_with_metadata,
                'count': len(files_with_metadata)
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Get monitored files error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/monitored-files", methods=["POST"])
    def add_monitored_files():
        """POST /api/monitored-files - Add new files to monitoring"""
        try:
            data = request.get_json()
            files_to_add = data.get('files', [])
            
            if not files_to_add:
                return jsonify({
                    'success': False,
                    'error': 'No files provided'
                }), HTTPStatus.BAD_REQUEST
            
            added = []
            failed = []
            
            for file_data in files_to_add:
                path = file_data.get('path')
                
                if not path:
                    failed.append({
                        'path': '',
                        'error': 'Path is required'
                    })
                    continue
                
                # Validate file exists
                if not os.path.exists(path):
                    failed.append({
                        'path': path,
                        'error': 'File not found'
                    })
                    continue
                
                # Check if already monitored
                abs_path = os.path.abspath(path)
                if any(f['path'] == abs_path for f in daemon.log_files):
                    failed.append({
                        'path': path,
                        'error': 'File already being monitored'
                    })
                    continue
                
                # Create file entry
                file_id = f"file_{len(daemon.log_files) + 1:03d}"
                new_file = {
                    'id': file_id,
                    'path': abs_path,
                    'label': file_data.get('label', os.path.basename(path).replace('.log', '').replace('.', '_')),
                    'priority': file_data.get('priority', 'medium'),
                    'enabled': True,
                    'created_at': datetime.now().isoformat(),
                    'last_modified': datetime.now().isoformat()
                }
                
                daemon.log_files.append(new_file)
                added.append(new_file)
                
                # Start monitoring thread for this file
                thread = threading.Thread(
                    target=daemon._monitor_loop,
                    args=(new_file,),
                    daemon=True,
                    name=f"Monitor-{new_file['label']}"
                )
                thread.start()
                daemon._monitor_threads.append(thread)
                logger.info(f"[MonitoredFiles] Started monitoring: {new_file['path']} [{new_file['label']}]")
            
            # Save configuration if config store available
            if CONFIG_STORE_AVAILABLE:
                try:
                    config = get_config()
                    config.set('monitoring.log_files', daemon.log_files)
                    config.save()
                except Exception as e:
                    logger.warning(f"[MonitoredFiles] Failed to save to config: {e}")
            
            if failed and not added:
                return jsonify({
                    'success': False,
                    'error': f'Failed to add all files',
                    'failed_files': failed
                }), HTTPStatus.BAD_REQUEST
            
            return jsonify({
                'success': True,
                'message': f'Added {len(added)} log file(s) to monitoring',
                'added': added,
                'failed_files': failed if failed else None,
                'monitoring_reloaded': True
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Add monitored files error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/monitored-files/<file_id>", methods=["PUT"])
    def update_monitored_file(file_id):
        """PUT /api/monitored-files/:id - Update file configuration"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No updates provided'
                }), HTTPStatus.BAD_REQUEST
            
            # Find file
            file_index = None
            for i, f in enumerate(daemon.log_files):
                if f.get('id') == file_id or f.get('id', f"file_{i+1:03d}") == file_id:
                    file_index = i
                    break
            
            if file_index is None:
                return jsonify({
                    'success': False,
                    'error': 'File not found'
                }), HTTPStatus.NOT_FOUND
            
            # Check if it's auto-monitored (cannot be disabled/modified)
            if daemon.log_files[file_index].get('auto_monitor') and 'enabled' in data:
                if not data['enabled']:
                    return jsonify({
                        'success': False,
                        'error': 'Cannot disable auto-monitored files'
                    }), HTTPStatus.BAD_REQUEST
            
            # Update fields
            if 'label' in data:
                daemon.log_files[file_index]['label'] = data['label']
            if 'priority' in data:
                valid_priorities = ['critical', 'high', 'medium', 'low']
                if data['priority'] not in valid_priorities:
                    return jsonify({
                        'success': False,
                        'error': f'Invalid priority. Must be one of: {", ".join(valid_priorities)}'
                    }), HTTPStatus.BAD_REQUEST
                daemon.log_files[file_index]['priority'] = data['priority']
            if 'enabled' in data:
                daemon.log_files[file_index]['enabled'] = data['enabled']
            
            daemon.log_files[file_index]['last_modified'] = datetime.now().isoformat()
            
            # Save configuration
            if CONFIG_STORE_AVAILABLE:
                try:
                    config = get_config()
                    config.set('monitoring.log_files', daemon.log_files)
                    config.save()
                except Exception as e:
                    logger.warning(f"[MonitoredFiles] Failed to save to config: {e}")
            
            logger.info(f"[MonitoredFiles] Updated file {file_id}: {data}")
            
            return jsonify({
                'success': True,
                'message': 'File configuration updated',
                'file': daemon.log_files[file_index],
                'monitoring_reloaded': True
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Update monitored file error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/monitored-files/<file_id>", methods=["DELETE"])
    def delete_monitored_file(file_id):
        """DELETE /api/monitored-files/:id - Delete monitored file"""
        try:
            # Find and remove file
            deleted_file = None
            file_index = None
            
            for i, f in enumerate(daemon.log_files):
                if f.get('id') == file_id or f.get('id', f"file_{i+1:03d}") == file_id:
                    # Check if it's auto-monitored (cannot be deleted)
                    if f.get('auto_monitor'):
                        return jsonify({
                            'success': False,
                            'error': 'Cannot delete auto-monitored files'
                        }), HTTPStatus.BAD_REQUEST
                    
                    deleted_file = f
                    file_index = i
                    break
            
            if deleted_file is None:
                return jsonify({
                    'success': False,
                    'error': 'File not found'
                }), HTTPStatus.NOT_FOUND
            
            # Remove from list
            daemon.log_files.pop(file_index)
            
            # Note: We don't stop the monitoring thread as it's daemon thread
            # It will detect the file is no longer in the list and stop naturally
            # Or we can implement thread stopping if needed
            
            # Save configuration
            if CONFIG_STORE_AVAILABLE:
                try:
                    config = get_config()
                    config.set('monitoring.log_files', daemon.log_files)
                    config.save()
                except Exception as e:
                    logger.warning(f"[MonitoredFiles] Failed to save to config: {e}")
            
            logger.info(f"[MonitoredFiles] Deleted file {file_id}: {deleted_file['path']}")
            
            return jsonify({
                'success': True,
                'message': 'File removed from monitoring',
                'deleted_file': deleted_file,
                'monitoring_reloaded': True
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Delete monitored file error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    @app.route("/api/monitored-files/reload", methods=["POST"])
    def reload_monitoring():
        """POST /api/monitored-files/reload - Force reload monitoring configuration"""
        try:
            # Count active monitoring threads
            active_threads = sum(1 for t in daemon._monitor_threads if t.is_alive())
            
            # Get count of enabled files
            active_files = sum(1 for f in daemon.log_files if f.get('enabled', True))
            
            logger.info(f"[MonitoredFiles] Monitoring reload requested. Active files: {active_files}, Threads: {active_threads}")
            
            return jsonify({
                'success': True,
                'message': 'Monitoring configuration reloaded',
                'active_files': active_files,
                'threads_running': active_threads,
                'timestamp': datetime.now().isoformat()
            }), HTTPStatus.OK
            
        except Exception as e:
            logger.error(f"Reload monitoring error: {e}")
            return jsonify({'success': False, 'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    return app


def apply_config_changes(daemon: LogCollectorDaemon, changes: Dict[str, tuple]):
    """Apply configuration changes at runtime"""
    if not CONFIG_STORE_AVAILABLE:
        return
    
    config = get_config()

    for key_path, (old_value, new_value) in changes.items():
        logger.info(f"[Config] Applying change: {key_path} = {new_value} (was {old_value})")

        # Update alert thresholds (hot-reload)
        if key_path.startswith('alerts.thresholds'):
            # Alert system will read from config on next check
            logger.info(f"[Config] Alert threshold updated: {key_path}")

        # Update telemetry interval (requires restart of telemetry thread)
        elif key_path == 'intervals.telemetry':
            # Signal telemetry poster to restart with new interval
            logger.info(f"[Config] Telemetry interval changed to {new_value}s (restart required)")
            # TODO: Implement telemetry poster restart

        # Update logging level
        elif key_path == 'logging.level':
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR
            }
            new_level = level_map.get(new_value.upper(), logging.INFO)
            logging.getLogger('resolvix').setLevel(new_level)
            logger.info(f"[Config] Logging level changed to {new_value}")
        
        # Update monitoring keywords
        elif key_path == 'monitoring.error_keywords':
            # Rebuild error regex
            kw = "|".join(re.escape(k) for k in new_value)
            daemon._err_re = re.compile(rf"\b({kw})\b", re.IGNORECASE)
            logger.info(f"[Config] Error keywords updated: {len(new_value)} keywords")


# -------- CLI / Entrypoint --------
def parse_args():
    parser = argparse.ArgumentParser(description="Log Collector Daemon (error monitoring + telemetry + control endpoint)")
    parser.add_argument("--log-file", "-l", action='append', dest='log_files',
                       help="Path to log file to monitor (can be specified multiple times)")
    parser.add_argument("--api-url", "-a", required=True, help="Central API URL to send logs")
    parser.add_argument("--control-port", "-p", type=int, default=DEFAULT_CONTROL_PORT, help="Port for control HTTP server")
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="Port where livelogs will host websocket")
    parser.add_argument("--telemetry-ws-port", type=int, default=DEFAULT_TELEMETRY_WS_PORT, help="Port where telemetry websocket will be hosted")
    parser.add_argument("--node-id", "-n", help="optional node identifier")
    parser.add_argument("--telemetry-interval", "-t", type=int, default=DEFAULT_TELEMETRY_INTERVAL, 
                        help="Telemetry collection interval in seconds (default: 3)")
    parser.add_argument("--heartbeat-interval", type=int, default=DEFAULT_HEARTBEAT_INTERVAL, 
                        help="Heartbeat interval in seconds (default: 30)")
    # Telemetry backend configuration
    parser.add_argument("--telemetry-backend-url", help="Backend URL for telemetry POST (e.g., http://localhost:3000)")
    parser.add_argument("--telemetry-jwt-token", help="JWT token for telemetry authentication")
    # Database configuration for suppression rules
    parser.add_argument("--db-host", help="Database host for suppression rules")
    parser.add_argument("--db-name", help="Database name for suppression rules")
    parser.add_argument("--db-user", help="Database user for suppression rules")
    parser.add_argument("--db-password", help="Database password for suppression rules")
    parser.add_argument("--db-port", type=int, default=5432, help="Database port (default: 5432)")
    
    args = parser.parse_args()
    
    # Validate at least one log file
    if not args.log_files:
        parser.error("At least one --log-file must be specified")
    
    return args

# ============================================================================
# MAIN EXECUTION WITH STARTUP ERROR HANDLING
# ============================================================================
if __name__ == "__main__":
    try:
        args = parse_args()
        logger.info("="*60)
        logger.info(f"Resolvix Daemon Starting - Version {DAEMON_VERSION}")
        logger.info("="*60)
        
        # ✅ Initialize configuration store
        if CONFIG_STORE_AVAILABLE:
            logger.info("[Config] Initializing configuration store...")
            node_id = args.node_id or get_node_id()
            config = init_config(
                node_id=node_id,
                backend_url=args.api_url
            )
            logger.info("[Config] Configuration store initialized")
            
            # Use config values (with CLI args as override)
            log_files = args.log_files or config.get('monitoring.log_files', [])
            control_port = args.control_port if args.control_port != DEFAULT_CONTROL_PORT else config.get('ports.control', DEFAULT_CONTROL_PORT)
            ws_port = args.ws_port if args.ws_port != DEFAULT_WS_PORT else config.get('ports.ws', DEFAULT_WS_PORT)
            telemetry_ws_port = args.telemetry_ws_port if args.telemetry_ws_port != DEFAULT_TELEMETRY_WS_PORT else config.get('ports.telemetry_ws', DEFAULT_TELEMETRY_WS_PORT)
            telemetry_interval = args.telemetry_interval if args.telemetry_interval != DEFAULT_TELEMETRY_INTERVAL else config.get('intervals.telemetry', DEFAULT_TELEMETRY_INTERVAL)
            heartbeat_interval = args.heartbeat_interval if args.heartbeat_interval != DEFAULT_HEARTBEAT_INTERVAL else config.get('intervals.heartbeat', DEFAULT_HEARTBEAT_INTERVAL)
            
            # Get DB config from ConfigStore
            db_host = args.db_host or config.get('suppression.db.host')
            db_name = args.db_name or config.get('suppression.db.name')
            db_user = args.db_user or config.get('suppression.db.user')
            db_password = args.db_password or config.get_secret('db_password') or config.get('suppression.db.password')
            db_port = args.db_port or config.get('suppression.db.port', 5432)
            
            # Get telemetry config
            telemetry_backend_url = args.telemetry_backend_url or config.get('connectivity.telemetry_backend_url')
            telemetry_jwt_token = args.telemetry_jwt_token or config.get_secret('telemetry_jwt_token')
            
            logger.info(f"[Config] Loaded configuration from store")
        else:
            logger.warning("[Config] Config store not available, using CLI arguments only")
            log_files = args.log_files
            control_port = args.control_port
            ws_port = args.ws_port
            telemetry_ws_port = args.telemetry_ws_port
            telemetry_interval = args.telemetry_interval
            heartbeat_interval = args.heartbeat_interval
            db_host = args.db_host
            db_name = args.db_name
            db_user = args.db_user
            db_password = args.db_password
            db_port = args.db_port
            telemetry_backend_url = args.telemetry_backend_url
            telemetry_jwt_token = args.telemetry_jwt_token
        
        # Initialize backend log handler for real-time error reporting
        backend_log_handler = BackendLogHandler(
            backend_url=args.api_url or telemetry_backend_url,
            node_id=args.node_id or get_node_id()
        )
        logger.addHandler(backend_log_handler)
        logger.info("[Config] Backend error reporting enabled")
        
        daemon = LogCollectorDaemon(
            log_files=log_files,
            api_url=args.api_url, 
            ws_port=ws_port,
            telemetry_ws_port=telemetry_ws_port,
            node_id=args.node_id,
            telemetry_interval=telemetry_interval,
            heartbeat_interval=heartbeat_interval,
            db_host=db_host,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
            db_port=db_port,
            telemetry_backend_url=telemetry_backend_url,
            telemetry_jwt_token=telemetry_jwt_token
        )
        
        # Store control port for health endpoint
        daemon._control_port = control_port
        
        daemon.start()
        app = make_app(daemon)
        # run flask on specified control port
        logger.info(f"Control HTTP endpoint: http://0.0.0.0:{control_port}")
        logger.info(f"Monitoring {len(log_files)} log file(s):")
        for log_file in log_files:
            logger.info(f"  - {log_file}")
        logger.info(f"Livelogs WebSocket port: {ws_port}")
        logger.info(f"Telemetry WebSocket port: {telemetry_ws_port}")
        logger.info(f"Telemetry interval: {telemetry_interval}s")
        logger.info(f"Heartbeat interval: {heartbeat_interval}s")
        logger.info(f"Daemon log file: /var/log/resolvix.log")
        if daemon.suppression_checker:
            logger.info(f"Suppression rules: ENABLED")
        else:
            logger.info(f"Suppression rules: DISABLED")
        
        logger.info("="*60)
        logger.info("✅ Daemon initialization complete")
        logger.info("="*60)
        
    except Exception as e:
        logger.critical("="*60)
        logger.critical("❌ FATAL: Daemon failed to initialize")
        logger.critical("="*60)
        logger.critical(f"Error: {e}")
        logger.critical(f"Type: {type(e).__name__}")
        import traceback
        logger.critical("Stack trace:")
        for line in traceback.format_exc().split('\n'):
            if line:
                logger.critical(line)
        logger.critical("="*60)
        sys.exit(1)
    
    # Run the daemon
    try:
        # do not use debug in production
        app.run(host="0.0.0.0", port=control_port)
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    except Exception as e:
        logger.critical("="*60)
        logger.critical("❌ FATAL: Daemon crashed during runtime")
        logger.critical("="*60)
        logger.critical(f"Error: {e}")
        import traceback
        logger.critical("Stack trace:")
        for line in traceback.format_exc().split('\n'):
            if line:
                logger.critical(line)
        logger.critical("="*60)
        sys.exit(1)
    finally:
        logger.info("Shutting down daemon...")
        daemon.stop()
        logger.info("Daemon stopped")
