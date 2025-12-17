# 🔧 LINUX DAEMON DEVELOPER - Historical Telemetry Implementation
**Date:** December 17, 2025  
**Priority:** HIGH - Complete Today  
**Estimated Time:** 4-6 hours  

---

## ⚠️ CRITICAL: DO NOT BREAK EXISTING FUNCTIONALITY

**Before starting any task:**
- ✅ Backup daemon files before editing
- ✅ Test existing WebSocket streaming - must continue working
- ✅ Test existing heartbeat - must continue working
- ✅ All new code is ADDITIVE - we're adding HTTP POST alongside WebSocket, not replacing it

**Rollback Plan:**
If anything breaks, you can revert to backup:
```bash
# Backup command
cp log_collector_daemon.py log_collector_daemon.py.backup.$(date +%Y%m%d_%H%M%S)
cp telemetry_ws.py telemetry_ws.py.backup.$(date +%Y%m%d_%H%M%S)
```

**Architecture:**
```
Current (KEEP):
  Daemon → WebSocket (8756) → Frontend (Real-time)
  Daemon → HTTP POST (/api/heartbeat) → Backend

New (ADD):
  Daemon → HTTP POST (/api/telemetry/snapshot) → Backend → PostgreSQL
           └─ With SQLite queue for reliability
```

---

## 📋 TASK CHECKLIST

- [ ] Task 1: Create Telemetry Queue Manager (60 min)
- [ ] Task 2: Create HTTP Poster with Retry (45 min)
- [ ] Task 3: Integrate into Main Daemon (60 min)
- [ ] Task 4: Update Telemetry Collector (45 min)
- [ ] Task 5: Testing (60 min)
- [ ] Task 6: Deployment (30 min)

**Total Estimated Time:** 5 hours

---

## TASK 1: CREATE TELEMETRY QUEUE MANAGER (60 minutes)

### Objective:
Create SQLite-based persistent queue to store telemetry snapshots when backend is unavailable.

### Step 1.1: Create Queue Manager File

**Location:** `/home/bitnami/log-horizon-daemon/telemetry_queue.py`

```python
#!/usr/bin/env python3
"""
Telemetry Queue Manager
SQLite-based persistent queue for telemetry snapshots
Ensures no data loss during network outages
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class TelemetryQueue:
    """
    SQLite-based persistent queue for telemetry snapshots.
    
    Features:
    - Persistent storage (survives daemon restarts)
    - FIFO ordering (oldest first)
    - Automatic size management (drops oldest when full)
    - Retry tracking
    """
    
    def __init__(self, db_path='/var/lib/resolvix/telemetry_queue.db', max_size=1000):
        """
        Initialize queue manager.
        
        Args:
            db_path: Path to SQLite database file
            max_size: Maximum queue size (drops oldest when exceeded)
        """
        self.db_path = db_path
        self.max_size = max_size
        self._init_db()
        logger.info(f"[TelemetryQueue] Initialized (max_size={max_size}, db={db_path})")
    
    def _init_db(self):
        """Initialize SQLite database with schema"""
        # Create directory if doesn't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telemetry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_attempt_at TEXT
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON telemetry_queue(timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_retry_count 
            ON telemetry_queue(retry_count)
        ''')
        
        conn.commit()
        conn.close()
        
        logger.debug("[TelemetryQueue] Database schema initialized")
    
    def enqueue(self, payload):
        """
        Add telemetry snapshot to queue.
        
        Args:
            payload: Dict containing telemetry data
            
        Returns:
            int: Queue entry ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Check queue size
            cursor.execute('SELECT COUNT(*) FROM telemetry_queue')
            count = cursor.fetchone()[0]
            
            # Drop oldest if queue is full
            if count >= self.max_size:
                cursor.execute('''
                    DELETE FROM telemetry_queue 
                    WHERE id IN (
                        SELECT id FROM telemetry_queue 
                        ORDER BY timestamp ASC 
                        LIMIT 1
                    )
                ''')
                logger.warning(f"[TelemetryQueue] Queue full ({count}), dropped oldest entry")
            
            # Insert new entry
            timestamp = payload.get('timestamp', datetime.utcnow().isoformat())
            created_at = datetime.utcnow().isoformat()
            
            cursor.execute('''
                INSERT INTO telemetry_queue (timestamp, payload, created_at)
                VALUES (?, ?, ?)
            ''', (timestamp, json.dumps(payload), created_at))
            
            entry_id = cursor.lastrowid
            conn.commit()
            
            logger.debug(f"[TelemetryQueue] Enqueued snapshot (id={entry_id})")
            return entry_id
            
        except Exception as e:
            logger.error(f"[TelemetryQueue] Error enqueueing: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def dequeue(self, limit=10):
        """
        Get next batch of snapshots to send (oldest first).
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of tuples: (id, payload_dict, retry_count)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, payload, retry_count
                FROM telemetry_queue
                ORDER BY timestamp ASC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            
            # Parse JSON payloads
            results = []
            for row in rows:
                try:
                    payload = json.loads(row[1])
                    results.append((row[0], payload, row[2]))
                except json.JSONDecodeError as e:
                    logger.error(f"[TelemetryQueue] Invalid JSON in queue (id={row[0]}): {e}")
                    # Remove corrupted entry
                    cursor.execute('DELETE FROM telemetry_queue WHERE id = ?', (row[0],))
                    conn.commit()
            
            return results
            
        except Exception as e:
            logger.error(f"[TelemetryQueue] Error dequeuing: {e}")
            return []
        finally:
            conn.close()
    
    def mark_sent(self, snapshot_id):
        """
        Remove successfully sent snapshot from queue.
        
        Args:
            snapshot_id: Queue entry ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM telemetry_queue WHERE id = ?', (snapshot_id,))
            conn.commit()
            logger.debug(f"[TelemetryQueue] Marked sent (id={snapshot_id})")
        except Exception as e:
            logger.error(f"[TelemetryQueue] Error marking sent: {e}")
        finally:
            conn.close()
    
    def mark_failed(self, snapshot_id, max_retries=3):
        """
        Increment retry count or drop if max retries reached.
        
        Args:
            snapshot_id: Queue entry ID
            max_retries: Maximum retry attempts before dropping
            
        Returns:
            bool: True if entry still in queue, False if dropped
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Update retry count
            cursor.execute('''
                UPDATE telemetry_queue
                SET retry_count = retry_count + 1,
                    last_attempt_at = ?
                WHERE id = ?
            ''', (datetime.utcnow().isoformat(), snapshot_id))
            
            # Check if max retries reached
            cursor.execute('''
                SELECT retry_count FROM telemetry_queue WHERE id = ?
            ''', (snapshot_id,))
            
            row = cursor.fetchone()
            
            if row and row[0] >= max_retries:
                # Drop after max retries
                cursor.execute('DELETE FROM telemetry_queue WHERE id = ?', (snapshot_id,))
                logger.warning(f"[TelemetryQueue] Dropped after {max_retries} retries (id={snapshot_id})")
                conn.commit()
                return False
            else:
                conn.commit()
                logger.debug(f"[TelemetryQueue] Marked failed (id={snapshot_id}, retries={row[0] if row else 0})")
                return True
                
        except Exception as e:
            logger.error(f"[TelemetryQueue] Error marking failed: {e}")
            return False
        finally:
            conn.close()
    
    def get_queue_size(self):
        """
        Get current queue size.
        
        Returns:
            int: Number of entries in queue
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT COUNT(*) FROM telemetry_queue')
            count = cursor.fetchone()[0]
            return count
        except Exception as e:
            logger.error(f"[TelemetryQueue] Error getting queue size: {e}")
            return 0
        finally:
            conn.close()
    
    def get_stats(self):
        """
        Get queue statistics.
        
        Returns:
            dict: Statistics including total, by retry count, oldest entry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Total count
            cursor.execute('SELECT COUNT(*) FROM telemetry_queue')
            total = cursor.fetchone()[0]
            
            # By retry count
            cursor.execute('''
                SELECT retry_count, COUNT(*) 
                FROM telemetry_queue 
                GROUP BY retry_count 
                ORDER BY retry_count
            ''')
            by_retry = dict(cursor.fetchall())
            
            # Oldest entry
            cursor.execute('''
                SELECT timestamp FROM telemetry_queue 
                ORDER BY timestamp ASC 
                LIMIT 1
            ''')
            oldest_row = cursor.fetchone()
            oldest = oldest_row[0] if oldest_row else None
            
            return {
                'total': total,
                'by_retry_count': by_retry,
                'oldest_timestamp': oldest
            }
            
        except Exception as e:
            logger.error(f"[TelemetryQueue] Error getting stats: {e}")
            return {'total': 0, 'by_retry_count': {}, 'oldest_timestamp': None}
        finally:
            conn.close()
```

### ✅ Success Criteria:
- [ ] File created at `/home/bitnami/log-horizon-daemon/telemetry_queue.py`
- [ ] Test imports: `python3 -c "from telemetry_queue import TelemetryQueue"`
- [ ] Database created: `ls -lh /var/lib/resolvix/telemetry_queue.db`

### Testing:
```python
# Test script
from telemetry_queue import TelemetryQueue
import json

queue = TelemetryQueue()
print(f"Queue size: {queue.get_queue_size()}")

# Test enqueue
test_payload = {'node_id': 'test', 'cpu_percent': 50}
queue.enqueue(test_payload)

# Test dequeue
items = queue.dequeue(limit=1)
print(f"Dequeued: {items}")

# Get stats
stats = queue.get_stats()
print(f"Stats: {json.dumps(stats, indent=2)}")
```

---

## TASK 2: CREATE HTTP POSTER WITH RETRY (45 minutes)

### Objective:
Create HTTP client to POST telemetry snapshots with exponential backoff retry logic.

### Step 2.1: Create HTTP Poster File

**Location:** `/home/bitnami/log-horizon-daemon/telemetry_poster.py`

```python
#!/usr/bin/env python3
"""
Telemetry HTTP Poster
POST client with exponential backoff retry logic
Handles network failures gracefully
"""

import requests
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class TelemetryPoster:
    """
    HTTP POST client with retry logic for telemetry snapshots.
    
    Features:
    - Exponential backoff retry
    - Connection pooling (reuses TCP connections)
    - Timeout handling
    - Error classification (retry vs drop)
    """
    
    def __init__(self, backend_url, jwt_token, retry_backoff=[5, 15, 60], timeout=10):
        """
        Initialize HTTP poster.
        
        Args:
            backend_url: Backend base URL (e.g., http://backend:5001)
            jwt_token: JWT authentication token
            retry_backoff: List of wait times between retries (seconds)
            timeout: Request timeout (seconds)
        """
        self.backend_url = backend_url.rstrip('/')
        self.jwt_token = jwt_token
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        
        # Create session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'ResolvixDaemon/1.0'
        })
        
        logger.info(f"[TelemetryPoster] Initialized (backend={backend_url}, timeout={timeout}s)")
    
    def post_snapshot(self, payload):
        """
        POST telemetry snapshot to backend.
        
        Args:
            payload: Dict containing telemetry data
            
        Returns:
            tuple: (success: bool, error_type: str or None)
        """
        endpoint = f"{self.backend_url}/api/telemetry/snapshot"
        
        try:
            response = self.session.post(
                endpoint,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                logger.debug(f"[TelemetryPoster] Successfully posted snapshot")
                return True, None
            
            elif 400 <= response.status_code < 500:
                # Client error - don't retry
                error_msg = f"Client error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = f"{error_msg} - {error_data.get('error', 'Unknown')}"
                except:
                    error_msg = f"{error_msg} - {response.text[:100]}"
                
                logger.error(f"[TelemetryPoster] {error_msg}")
                return False, 'client_error'
            
            else:
                # Server error - retry
                logger.warning(f"[TelemetryPoster] Server error: {response.status_code}")
                return False, 'server_error'
        
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"[TelemetryPoster] Connection error (backend unavailable)")
            return False, 'connection_error'
        
        except requests.exceptions.Timeout:
            logger.warning(f"[TelemetryPoster] Request timeout ({self.timeout}s)")
            return False, 'timeout'
        
        except requests.exceptions.RequestException as e:
            logger.error(f"[TelemetryPoster] Request exception: {e}")
            return False, 'request_error'
        
        except Exception as e:
            logger.error(f"[TelemetryPoster] Unexpected error: {e}")
            return False, 'unknown_error'
    
    def post_with_retry(self, payload, retry_count=0):
        """
        POST with exponential backoff retry.
        
        Args:
            payload: Dict containing telemetry data
            retry_count: Current retry attempt (0-indexed)
            
        Returns:
            bool: True if successful, False if all retries exhausted
        """
        success, error_type = self.post_snapshot(payload)
        
        if success:
            return True
        
        # Don't retry on client errors (bad data)
        if error_type == 'client_error':
            logger.error(f"[TelemetryPoster] Dropping snapshot (client error)")
            return False
        
        # Retry with backoff on transient errors
        if retry_count < len(self.retry_backoff):
            wait_seconds = self.retry_backoff[retry_count]
            logger.info(f"[TelemetryPoster] Retrying in {wait_seconds}s (attempt {retry_count + 1}/{len(self.retry_backoff)})")
            time.sleep(wait_seconds)
            return self.post_with_retry(payload, retry_count + 1)
        
        logger.error(f"[TelemetryPoster] All retries exhausted")
        return False
    
    def close(self):
        """Close HTTP session"""
        try:
            self.session.close()
            logger.debug("[TelemetryPoster] Session closed")
        except Exception as e:
            logger.error(f"[TelemetryPoster] Error closing session: {e}")
```

### ✅ Success Criteria:
- [ ] File created at `/home/bitnami/log-horizon-daemon/telemetry_poster.py`
- [ ] Test imports: `python3 -c "from telemetry_poster import TelemetryPoster"`
- [ ] No syntax errors

### Testing:
```python
# Test script
from telemetry_poster import TelemetryPoster

poster = TelemetryPoster(
    backend_url='http://localhost:5001',
    jwt_token='your-test-token'
)

# Test POST (will fail without valid token, but tests connectivity)
test_payload = {
    'node_id': 'test-node',
    'timestamp': '2025-12-17T10:00:00Z',
    'cpu_percent': 50.0,
    'memory_percent': 60.0
}

success, error = poster.post_snapshot(test_payload)
print(f"POST result: success={success}, error={error}")

poster.close()
```

---

## TASK 3: INTEGRATE INTO MAIN DAEMON (60 minutes)

### Objective:
Integrate queue and poster into existing daemon without breaking WebSocket or heartbeat.

### Step 3.1: Update Main Daemon File

**Location:** `/home/bitnami/log-horizon-daemon/log_collector_daemon.py`

**⚠️ BACKUP FIRST:**
```bash
cp log_collector_daemon.py log_collector_daemon.py.backup.$(date +%Y%m%d_%H%M%S)
```

**Add imports at the top:**
```python
# ADD these imports near the top of the file
from telemetry_queue import TelemetryQueue
from telemetry_poster import TelemetryPoster
```

**Find the `__init__` method of `LogCollectorDaemon` class and add:**

```python
def __init__(self, ...existing parameters...):
    # ... existing initialization code ...
    
    # ADD THESE LINES at the end of __init__:
    
    # Initialize telemetry queue and poster
    try:
        self.telemetry_queue = TelemetryQueue(
            db_path='/var/lib/resolvix/telemetry_queue.db',
            max_size=1000
        )
        logger.info("[Daemon] Telemetry queue initialized")
        
        self.telemetry_poster = TelemetryPoster(
            backend_url=self.backend_url,
            jwt_token=self.auth_token,
            retry_backoff=[5, 15, 60],
            timeout=10
        )
        logger.info("[Daemon] Telemetry poster initialized")
        
        # Start telemetry POST thread
        self.telemetry_post_thread = threading.Thread(
            target=self._telemetry_post_loop,
            daemon=True,
            name='TelemetryPoster'
        )
        self.telemetry_post_thread.start()
        logger.info("[Daemon] Telemetry POST thread started")
        
    except Exception as e:
        logger.error(f"[Daemon] Failed to initialize telemetry system: {e}")
        # Don't fail - daemon can still run without telemetry POST
        self.telemetry_queue = None
        self.telemetry_poster = None
```

**Add new method to the class:**

```python
def _telemetry_post_loop(self):
    """
    Background thread to POST queued telemetry snapshots.
    Runs continuously while daemon is running.
    """
    logger.info("[TelemetryPoster] POST loop started")
    
    while self.running:
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
```

### ✅ Success Criteria:
- [ ] Daemon file updated
- [ ] No syntax errors: `python3 -m py_compile log_collector_daemon.py`
- [ ] Backup created

---

## TASK 4: UPDATE TELEMETRY COLLECTOR (45 minutes)

### Objective:
Modify telemetry collector to enqueue snapshots for HTTP POST (alongside existing WebSocket).

### Step 4.1: Update Telemetry WebSocket File

**Location:** `/home/bitnami/log-horizon-daemon/telemetry_ws.py`

**⚠️ BACKUP FIRST:**
```bash
cp telemetry_ws.py telemetry_ws.py.backup.$(date +%Y%m%d_%H%M%S)
```

**Find the `TelemetryCollector` class and add method to transform metrics:**

```python
# ADD this method to TelemetryCollector class

def _transform_to_api_format(self, ws_metrics):
    """
    Transform WebSocket format to API POST format.
    
    Args:
        ws_metrics: Metrics in WebSocket format
        
    Returns:
        dict: Metrics in API format
    """
    metrics = ws_metrics.get('metrics', {})
    
    # Get primary disk usage (usually "/")
    disk_usage = metrics.get('disk', {}).get('disk_usage', {})
    primary_disk = disk_usage.get('/', disk_usage.get(list(disk_usage.keys())[0] if disk_usage else '/'))
    
    # Calculate uptime
    try:
        import psutil
        uptime_seconds = int(time.time() - psutil.boot_time())
    except:
        uptime_seconds = 0
    
    return {
        'node_id': ws_metrics.get('node_id', 'unknown'),
        'timestamp': ws_metrics.get('timestamp', datetime.datetime.utcnow().isoformat() + 'Z'),
        'cpu_percent': float(metrics.get('cpu', {}).get('cpu_usage_percent', 0)),
        'memory_percent': float(metrics.get('memory', {}).get('memory_usage_percent', 0)),
        'memory_used_mb': int(metrics.get('memory', {}).get('memory_used_gb', 0) * 1024),
        'memory_total_mb': int(metrics.get('memory', {}).get('memory_total_gb', 0) * 1024),
        'disk_percent': float(primary_disk.get('usage_percent', 0) if primary_disk else 0),
        'disk_used_gb': float(primary_disk.get('used_gb', 0) if primary_disk else 0),
        'disk_total_gb': float(primary_disk.get('total_gb', 0) if primary_disk else 0),
        'network_rx_bytes': int(metrics.get('network', {}).get('packets_recv', 0)),
        'network_tx_bytes': int(metrics.get('network', {}).get('packets_sent', 0)),
        'network_rx_rate_mbps': float(metrics.get('network', {}).get('bytes_recv_mb_per_sec', 0)),
        'network_tx_rate_mbps': float(metrics.get('network', {}).get('bytes_sent_mb_per_sec', 0)),
        'uptime_seconds': uptime_seconds,
        'process_count': int(metrics.get('processes', {}).get('process_count', 0)),
        'active_connections': int(metrics.get('network', {}).get('active_connections', 0)),
        'load_avg_1m': float(metrics.get('cpu', {}).get('load_avg_1min', 0)),
        'load_avg_5m': float(metrics.get('cpu', {}).get('load_avg_5min', 0)),
        'load_avg_15m': float(metrics.get('cpu', {}).get('load_avg_15min', 0))
    }
```

**Find the method that broadcasts metrics (usually `broadcast` or similar) and add:**

```python
# MODIFY the broadcast/send method to also enqueue for HTTP POST

async def broadcast(self, message):
    """
    Broadcast metrics to all WebSocket clients AND enqueue for HTTP POST.
    
    Args:
        message: Metrics data (string or dict)
    """
    # Parse message if string
    if isinstance(message, str):
        import json
        try:
            metrics_data = json.loads(message)
        except:
            metrics_data = None
    else:
        metrics_data = message
    
    # Existing WebSocket broadcast code (DON'T REMOVE)
    if self.clients:
        message_str = message if isinstance(message, str) else json.dumps(message)
        for client in self.clients.copy():
            try:
                await client.send(message_str)
            except Exception as e:
                logger.error(f"[telemetry-ws] Error sending to client: {e}")
                self.clients.discard(client)
    
    # NEW: Enqueue for HTTP POST
    if metrics_data and hasattr(self, 'daemon_ref') and self.daemon_ref:
        try:
            # Check if daemon has telemetry queue
            if hasattr(self.daemon_ref, 'telemetry_queue') and self.daemon_ref.telemetry_queue:
                # Transform to API format
                api_payload = self._transform_to_api_format(metrics_data)
                
                # Enqueue for HTTP POST
                self.daemon_ref.telemetry_queue.enqueue(api_payload)
                logger.debug("[telemetry-ws] Enqueued snapshot for HTTP POST")
        except Exception as e:
            logger.error(f"[telemetry-ws] Error enqueueing for HTTP POST: {e}")
            # Don't fail - WebSocket should continue working
```

**Find where TelemetryCollector is initialized and pass daemon reference:**

```python
# In the function that starts the telemetry WebSocket server,
# ADD daemon reference when creating TelemetryCollector

# Example:
collector = TelemetryCollector(interval=60)
collector.daemon_ref = daemon_instance  # ADD this line
```

### ✅ Success Criteria:
- [ ] Telemetry WebSocket file updated
- [ ] No syntax errors: `python3 -m py_compile telemetry_ws.py`
- [ ] Backup created

---

## TASK 5: TESTING (60 minutes)

### Test 5.1: Start Daemon and Verify Initialization

```bash
# Start daemon
sudo systemctl restart resolvix-daemon

# Check logs
sudo journalctl -u resolvix-daemon -f

# Look for these log messages:
# ✅ "[Daemon] Telemetry queue initialized"
# ✅ "[Daemon] Telemetry poster initialized"
# ✅ "[Daemon] Telemetry POST thread started"
# ✅ "[TelemetryPoster] POST loop started"
```

### Test 5.2: Verify WebSocket Still Works

```bash
# Test WebSocket connection (from another terminal)
wscat -c ws://localhost:8756

# Should see:
# ✅ Connection established
# ✅ Welcome message
# ✅ Metrics every 60 seconds
```

### Test 5.3: Verify Queue is Working

```bash
# Check queue database exists
ls -lh /var/lib/resolvix/telemetry_queue.db

# Check queue size
python3 << 'EOF'
from telemetry_queue import TelemetryQueue
queue = TelemetryQueue()
print(f"Queue size: {queue.get_queue_size()}")
print(f"Stats: {queue.get_stats()}")
EOF
```

### Test 5.4: Verify HTTP POST is Working

```bash
# Check backend logs for telemetry POST requests
# On backend server:
pm2 logs log-horizon-server | grep -i telemetry

# Should see:
# ✅ "[Telemetry] Telemetry stored successfully"
```

### Test 5.5: Test Network Failure Recovery

```bash
# Simulate network outage
# Option 1: Stop backend temporarily
pm2 stop log-horizon-server

# Wait 2-3 minutes
# Check queue is growing
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_queue_size())"

# Restart backend
pm2 start log-horizon-server

# Wait 2-3 minutes
# Verify queue is draining
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_queue_size())"
```

### Test 5.6: Verify Existing Functionality

```bash
# Test heartbeat still works
curl http://localhost:8080/health  # Should return OK

# Test WebSocket still streams
wscat -c ws://localhost:8756  # Should see metrics

# Check daemon logs for errors
sudo journalctl -u resolvix-daemon --since "5 minutes ago" | grep -i error
```

### ✅ Success Criteria:
- [ ] Daemon starts without errors
- [ ] WebSocket still streams metrics
- [ ] Queue database created
- [ ] HTTP POST attempts visible in logs
- [ ] Queue grows during network outage
- [ ] Queue drains when network recovers
- [ ] Heartbeat still functional

---

## TASK 6: DEPLOYMENT (30 minutes)

### Step 6.1: Deploy to All Nodes

**Create deployment script:** `/tmp/deploy_telemetry.sh`

```bash
#!/bin/bash
# Deploy telemetry updates to all nodes

NODES=(
  "192.168.100.27"
  "192.168.100.28"
  # Add all your nodes
)

for node in "${NODES[@]}"; do
  echo "=== Deploying to $node ==="
  
  # Copy new files
  scp telemetry_queue.py bitnami@$node:/home/bitnami/log-horizon-daemon/
  scp telemetry_poster.py bitnami@$node:/home/bitnami/log-horizon-daemon/
  scp log_collector_daemon.py bitnami@$node:/home/bitnami/log-horizon-daemon/
  scp telemetry_ws.py bitnami@$node:/home/bitnami/log-horizon-daemon/
  
  # Restart daemon
  ssh bitnami@$node "sudo systemctl restart resolvix-daemon"
  
  # Check status
  ssh bitnami@$node "sudo systemctl status resolvix-daemon --no-pager"
  
  echo "✅ $node deployed"
  echo ""
done

echo "=== Deployment Complete ==="
```

### Step 6.2: Verify All Nodes

```bash
# Check all nodes are sending telemetry
# On backend server:
psql -d log_collector -c "
  SELECT 
    node_id, 
    COUNT(*) as snapshots,
    MAX(timestamp) as latest
  FROM telemetry_history
  WHERE timestamp >= NOW() - INTERVAL '10 minutes'
  GROUP BY node_id;
"
```

### ✅ Success Criteria:
- [ ] All nodes deployed successfully
- [ ] All daemons running
- [ ] Backend receiving telemetry from all nodes
- [ ] No errors in logs

---

## 🎯 FINAL CHECKLIST

### Pre-Deployment:
- [ ] All Python files backed up
- [ ] Test imports successful
- [ ] No syntax errors

### Deployment:
- [ ] telemetry_queue.py created
- [ ] telemetry_poster.py created
- [ ] log_collector_daemon.py updated
- [ ] telemetry_ws.py updated
- [ ] Daemon restarted successfully

### Post-Deployment Testing:
- [ ] WebSocket still streaming
- [ ] Heartbeat still working
- [ ] Queue database created
- [ ] HTTP POST working
- [ ] Backend receiving data
- [ ] Network failure recovery working

### Monitoring (First 24 Hours):
- [ ] Check logs every 2 hours
- [ ] Monitor queue size
- [ ] Verify all nodes sending data
- [ ] Check for any errors

---

## 🚨 TROUBLESHOOTING

### Issue: Daemon won't start
**Solution:**
```bash
# Check syntax errors
python3 -m py_compile log_collector_daemon.py
python3 -m py_compile telemetry_queue.py
python3 -m py_compile telemetry_poster.py

# Check logs
sudo journalctl -u resolvix-daemon -n 100

# Restore backup if needed
cp log_collector_daemon.py.backup.YYYYMMDD_HHMMSS log_collector_daemon.py
sudo systemctl restart resolvix-daemon
```

### Issue: WebSocket not working
**Solution:**
```bash
# Check if telemetry WebSocket process is running
ps aux | grep telemetry_ws

# Test WebSocket
wscat -c ws://localhost:8756

# Check telemetry logs
sudo journalctl -u resolvix-daemon | grep telemetry-ws
```

### Issue: Queue growing too large
**Solution:**
```python
# Check queue stats
from telemetry_queue import TelemetryQueue
queue = TelemetryQueue()
print(queue.get_stats())

# Clear queue if needed (emergency only)
import sqlite3
conn = sqlite3.connect('/var/lib/resolvix/telemetry_queue.db')
conn.execute('DELETE FROM telemetry_queue')
conn.commit()
conn.close()
```

### Issue: HTTP POST failing
**Solution:**
```bash
# Test backend endpoint manually
curl -X POST http://backend:5001/api/telemetry/snapshot \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"test","cpu_percent":50,"memory_percent":60}'

# Check backend logs
pm2 logs log-horizon-server | grep telemetry
```

---

## 📞 SUPPORT

If you encounter issues:
1. Check daemon logs: `sudo journalctl -u resolvix-daemon -f`
2. Check queue: `python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_stats())"`
3. Contact backend team if API endpoint not working
4. Restore backups if system is broken

---

**END OF DAEMON TASKS**
**Estimated Completion Time: 4-5 hours**
**Status: Ready to start**
