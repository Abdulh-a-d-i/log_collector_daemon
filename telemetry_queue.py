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
