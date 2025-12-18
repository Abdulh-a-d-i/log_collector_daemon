#!/usr/bin/env python3
"""
Configuration Store Module
Centralized configuration management with backend sync, caching, and secrets handling
"""

import json
import os
import requests
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Config file paths
CONFIG_DIR = Path('/etc/resolvix')
CONFIG_FILE = CONFIG_DIR / 'config.json'
SECRETS_FILE = CONFIG_DIR / 'secrets.json'
CACHE_FILE = CONFIG_DIR / 'config_cache.json'

# Default configuration (fallback if backend unreachable)
DEFAULT_CONFIG = {
    'connectivity': {
        'api_url': 'http://localhost:3000/api',
        'telemetry_backend_url': 'http://localhost:3000',
    },
    'messaging': {
        'rabbitmq': {
            'url': 'amqp://resolvix_user:resolvix4321@140.238.255.110:5672',
            'queue': 'error_logs_queue'
        }
    },
    'telemetry': {
        'interval': 3,
        'retry_backoff': [5, 15, 60],
        'timeout': 10,
        'queue_db_path': '/var/lib/resolvix/telemetry_queue.db',
        'queue_max_size': 1000
    },
    'monitoring': {
        'log_files': [],
        'error_keywords': [
            'emerg', 'emergency', 'alert', 'crit', 'critical',
            'err', 'error', 'fail', 'failed', 'failure', 'panic', 'fatal'
        ],
    },
    'alerts': {
        'thresholds': {
            'cpu_critical': {
                'threshold': 90,
                'duration': 300,
                'priority': 'critical',
                'cooldown': 1800
            },
            'cpu_high': {
                'threshold': 75,
                'duration': 600,
                'priority': 'high',
                'cooldown': 3600
            },
            'memory_critical': {
                'threshold': 95,
                'duration': 300,
                'priority': 'critical',
                'cooldown': 1800
            },
            'memory_high': {
                'threshold': 85,
                'duration': 600,
                'priority': 'high',
                'cooldown': 3600
            },
            'disk_critical': {
                'threshold': 90,
                'duration': 0,
                'priority': 'critical',
                'cooldown': 7200
            },
            'disk_high': {
                'threshold': 80,
                'duration': 0,
                'priority': 'high',
                'cooldown': 14400
            },
            'network_spike': {
                'threshold_multiplier': 5,
                'duration': 60,
                'priority': 'medium',
                'cooldown': 1800
            },
            'high_process_count': {
                'threshold': 500,
                'duration': 300,
                'priority': 'medium',
                'cooldown': 3600
            }
        }
    },
    'ports': {
        'control': 8754,
        'ws': 8755,
        'telemetry_ws': 8756
    },
    'intervals': {
        'telemetry': 3,
        'heartbeat': 30
    },
    'logging': {
        'level': 'INFO',
        'path': '/var/log/resolvix.log',
        'max_bytes': 10485760,  # 10MB
        'backup_count': 5
    },
    'suppression': {
        'db': {
            'host': None,
            'port': 5432,
            'name': None,
            'user': None,
            'password': None  # Will be in secrets
        },
        'cache_ttl': 60
    },
    'security': {
        'cors_allowed_origins': '*'
    }
}


class ConfigStore:
    """Centralized configuration management with backend sync"""

    def __init__(self, node_id: Optional[str] = None, backend_url: Optional[str] = None):
        self.node_id = node_id
        self.backend_url = backend_url or 'http://localhost:3000'
        self.config = self._deep_copy(DEFAULT_CONFIG)
        self.secrets = {}
        self.last_sync = None
        self.cache_ttl = timedelta(hours=1)

        # Ensure config directory exists
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            os.chmod(CONFIG_DIR, 0o755)
        except Exception as e:
            logger.warning(f"Could not create config directory: {e}")

        # Load configuration
        self.load()

    def load(self):
        """Load configuration from local files and backend"""
        # 1. Load from local config file (persistent overrides)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    local_config = json.load(f)
                    self._deep_merge(self.config, local_config)
                logger.info(f"[Config] Loaded local config from {CONFIG_FILE}")
            except Exception as e:
                logger.error(f"[Config] Failed to load local config: {e}")

        # 2. Load secrets
        if SECRETS_FILE.exists():
            try:
                with open(SECRETS_FILE, 'r') as f:
                    self.secrets = json.load(f)
                # Restrict permissions
                try:
                    os.chmod(SECRETS_FILE, 0o600)
                except:
                    pass
                logger.info(f"[Config] Loaded secrets from {SECRETS_FILE}")
            except Exception as e:
                logger.error(f"[Config] Failed to load secrets: {e}")

        # 3. Try to sync from backend
        if self.node_id:
            try:
                self.sync_from_backend()
            except Exception as e:
                logger.warning(f"[Config] Failed to sync from backend: {e}")
                # Load from cache as fallback
                self._load_cache()
        else:
            logger.info("[Config] No node_id provided, skipping backend sync")

    def sync_from_backend(self):
        """Fetch configuration from backend"""
        if not self.node_id:
            logger.warning("[Config] No node_id set, skipping backend sync")
            return

        url = f"{self.backend_url}/api/settings/daemon/{self.node_id}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data.get('success'):
                backend_config = data.get('config', {})

                # Merge backend config with local
                self._deep_merge(self.config, backend_config)

                self.last_sync = datetime.now()
                logger.info(f"[Config] Synced configuration from backend at {self.last_sync}")

                # Save to cache
                self._save_cache()
            else:
                logger.error(f"[Config] Backend returned error: {data.get('error')}")

        except requests.RequestException as e:
            logger.warning(f"[Config] Failed to fetch config from backend: {e}")
            raise

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation path
        Example: get('alerts.thresholds.cpu_critical.threshold')
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any):
        """
        Set configuration value by dot-notation path
        Example: set('alerts.thresholds.cpu_critical.threshold', 85)
        """
        keys = key_path.split('.')
        config = self.config

        # Navigate to parent
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        # Set value
        config[keys[-1]] = value
        logger.info(f"[Config] Updated: {key_path} = {value}")

    def get_secret(self, key_name: str) -> Optional[str]:
        """Get secret value"""
        return self.secrets.get(key_name)

    def set_secret(self, key_name: str, value: str):
        """Set secret value and save to file"""
        self.secrets[key_name] = value

        # Save secrets file with restricted permissions
        try:
            with open(SECRETS_FILE, 'w') as f:
                json.dump(self.secrets, f, indent=2)
            os.chmod(SECRETS_FILE, 0o600)
            logger.info(f"[Config] Updated secret: {key_name}")
        except Exception as e:
            logger.error(f"[Config] Failed to save secret: {e}")

    def save(self):
        """Save current configuration to local file"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"[Config] Saved configuration to {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"[Config] Failed to save config: {e}")

    def reload(self) -> Dict[str, Any]:
        """Reload configuration and return changes"""
        old_config = self._deep_copy(self.config)

        self.load()

        # Calculate diff
        changes = self._calculate_diff(old_config, self.config)

        logger.info(f"[Config] Reloaded configuration, {len(changes)} changes detected")
        return changes

    def _deep_merge(self, base: dict, updates: dict):
        """Deep merge updates into base dictionary"""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _deep_copy(self, obj):
        """Deep copy a dictionary"""
        return json.loads(json.dumps(obj))

    def _calculate_diff(self, old: dict, new: dict, path: str = '') -> Dict[str, tuple]:
        """Calculate differences between two config dictionaries"""
        changes = {}

        # Check for changed/new keys
        for key, new_value in new.items():
            current_path = f"{path}.{key}" if path else key

            if key not in old:
                changes[current_path] = (None, new_value)
            elif old[key] != new_value:
                if isinstance(old[key], dict) and isinstance(new_value, dict):
                    changes.update(self._calculate_diff(old[key], new_value, current_path))
                else:
                    changes[current_path] = (old[key], new_value)

        # Check for removed keys
        for key in old:
            if key not in new:
                current_path = f"{path}.{key}" if path else key
                changes[current_path] = (old[key], None)

        return changes

    def _save_cache(self):
        """Save config to cache file"""
        try:
            cache_data = {
                'config': self.config,
                'timestamp': self.last_sync.isoformat() if self.last_sync else None
            }
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f, indent=2)
            logger.debug("[Config] Saved to cache")
        except Exception as e:
            logger.error(f"[Config] Failed to save cache: {e}")

    def _load_cache(self):
        """Load config from cache file"""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)
                    cached_config = cache_data.get('config', {})
                    self._deep_merge(self.config, cached_config)
                    logger.info("[Config] Loaded configuration from cache")
            except Exception as e:
                logger.error(f"[Config] Failed to load cache: {e}")

    def should_sync(self) -> bool:
        """Check if config should be synced from backend"""
        if not self.last_sync:
            return True
        return datetime.now() - self.last_sync > self.cache_ttl

    def get_all(self) -> dict:
        """Get entire configuration (for debugging/display)"""
        return self._deep_copy(self.config)


# Global config instance
_config_store: Optional[ConfigStore] = None


def init_config(node_id: Optional[str] = None, backend_url: Optional[str] = None) -> ConfigStore:
    """Initialize global configuration store"""
    global _config_store
    _config_store = ConfigStore(node_id=node_id, backend_url=backend_url)
    return _config_store


def get_config() -> ConfigStore:
    """Get global configuration store"""
    if _config_store is None:
        raise RuntimeError("Config store not initialized. Call init_config() first.")
    return _config_store
