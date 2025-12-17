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
    
    def __init__(self, backend_url, jwt_token=None, retry_backoff=[5, 15, 60], timeout=10):
        """
        Initialize HTTP poster.
        
        Args:
            backend_url: Backend base URL (e.g., http://backend:5001)
            jwt_token: JWT authentication token (optional)
            retry_backoff: List of wait times between retries (seconds)
            timeout: Request timeout (seconds)
        """
        self.backend_url = backend_url.rstrip('/')
        self.jwt_token = jwt_token
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        
        # Create session for connection pooling
        self.session = requests.Session()
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ResolvixDaemon/1.0'
        }
        if jwt_token:
            headers['Authorization'] = f'Bearer {jwt_token}'
        self.session.headers.update(headers)
        
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
