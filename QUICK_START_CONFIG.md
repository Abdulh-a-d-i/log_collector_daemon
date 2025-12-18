# Quick Start Guide - Configuration Centralization

## 🚀 Quick Start (5 Minutes)

### 1. Test the Implementation

```bash
# Run all tests
python3 test_config.py
```

### 2. Start Daemon with Config Support

```bash
sudo python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://localhost:3000/api \
  --node-id server-01
```

### 3. Test API Endpoints

```bash
# Check daemon health
curl http://localhost:8754/api/health

# Get current config
curl http://localhost:8754/api/config | jq

# Get config schema
curl http://localhost:8754/api/config/schema | jq

# Update a setting
curl -X POST http://localhost:8754/api/config \
  -H "Content-Type: application/json" \
  -d '{"settings": {"logging.level": "DEBUG"}}'

# Reload config from backend
curl -X POST http://localhost:8754/api/config/reload | jq
```

---

## 📋 Key Features at a Glance

### New Message Fields

Every error log now includes:
- **`log_label`**: Auto-detected category (`apache_errors`, `mysql_errors`, `system`, etc.)
- **`priority`**: Dynamic priority (`critical`, `high`, `medium`, `low`)

### Config Management

- **Central config**: `/etc/resolvix/config.json`
- **Secrets**: `/etc/resolvix/secrets.json` (600 permissions)
- **Cache**: `/etc/resolvix/config_cache.json` (offline resilience)

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/config` | GET | Get current configuration |
| `/api/config` | POST | Update settings |
| `/api/config/reload` | POST | Reload from backend |
| `/api/config/schema` | GET | Get validation schema |

---

## 🎯 Common Tasks

### Change Telemetry Interval

**Option 1: Via API**
```bash
curl -X POST http://localhost:8754/api/config \
  -H "Content-Type: application/json" \
  -d '{"settings": {"intervals.telemetry": 10}}'
```

**Option 2: Edit config file**
```bash
sudo nano /etc/resolvix/config.json
# Change "telemetry": 3 to "telemetry": 10
# Then reload:
curl -X POST http://localhost:8754/api/config/reload
```

### Update Alert Thresholds

```bash
curl -X POST http://localhost:8754/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "alerts.thresholds.cpu_critical.threshold": 85,
      "alerts.thresholds.memory_critical.threshold": 90
    }
  }'
```

### Change Logging Level

```bash
# To DEBUG
curl -X POST http://localhost:8754/api/config \
  -d '{"settings": {"logging.level": "DEBUG"}}'

# To INFO
curl -X POST http://localhost:8754/api/config \
  -d '{"settings": {"logging.level": "INFO"}}'
```

### Add Monitored Log File

```bash
# Edit config
sudo nano /etc/resolvix/config.json
# Add to "monitoring.log_files": ["/var/log/newapp.log"]
# Restart daemon (hot-reload not supported for this yet)
sudo systemctl restart resolvix
```

---

## 🧪 Testing Individual Functions

### Test Log Label Detection

```bash
python3 << 'EOF'
from log_collector_daemon import get_log_label

tests = [
    '/var/log/apache2/error.log',
    '/var/log/nginx/error.log',
    '/var/log/mysql/error.log',
    '/var/log/syslog',
    '/var/log/kern.log'
]

for path in tests:
    label = get_log_label(path)
    print(f"{path:40s} -> {label}")
EOF
```

Expected output:
```
/var/log/apache2/error.log              -> apache_errors
/var/log/nginx/error.log                -> nginx_errors
/var/log/mysql/error.log                -> mysql_errors
/var/log/syslog                         -> system
/var/log/kern.log                       -> kernel
```

### Test Priority Detection

```bash
python3 << 'EOF'
from log_collector_daemon import determine_priority

tests = [
    ('FATAL: System crash', 'fatal'),
    ('ERROR: Connection failed', 'error'),
    ('WARNING: Disk space low', 'warning'),
    ('INFO: Service started', 'info')
]

for line, severity in tests:
    priority = determine_priority(line, severity)
    print(f"{priority:10s} | {line}")
EOF
```

Expected output:
```
critical   | FATAL: System crash
high       | ERROR: Connection failed
medium     | WARNING: Disk space low
low        | INFO: Service started
```

### Test Config Store

```bash
python3 << 'EOF'
from config_store import init_config

# Initialize
config = init_config(node_id='test', backend_url='http://localhost:3000')

# Get values
print("Telemetry interval:", config.get('intervals.telemetry'))
print("CPU threshold:", config.get('alerts.thresholds.cpu_critical.threshold'))
print("Log files:", config.get('monitoring.log_files'))

# Set value
config.set('intervals.telemetry', 10)
print("New interval:", config.get('intervals.telemetry'))
EOF
```

---

## 🔧 Configuration File Examples

### Minimal Config (`/etc/resolvix/config.json`)

```json
{
  "connectivity": {
    "api_url": "http://backend:3000/api",
    "telemetry_backend_url": "http://backend:3000"
  },
  "monitoring": {
    "log_files": ["/var/log/syslog"]
  }
}
```

### Full Config Example

```json
{
  "connectivity": {
    "api_url": "http://backend:3000/api",
    "telemetry_backend_url": "http://backend:3000"
  },
  "messaging": {
    "rabbitmq": {
      "queue": "error_logs_queue"
    }
  },
  "telemetry": {
    "interval": 5,
    "retry_backoff": [5, 15, 60],
    "timeout": 10,
    "queue_max_size": 1000
  },
  "monitoring": {
    "log_files": [
      "/var/log/syslog",
      "/var/log/apache2/error.log",
      "/var/log/mysql/error.log"
    ],
    "error_keywords": [
      "error", "fail", "critical", "fatal", "panic"
    ]
  },
  "alerts": {
    "thresholds": {
      "cpu_critical": {
        "threshold": 85,
        "duration": 300,
        "cooldown": 1800
      },
      "memory_critical": {
        "threshold": 90,
        "duration": 300,
        "cooldown": 1800
      }
    }
  },
  "ports": {
    "control": 8754,
    "ws": 8755,
    "telemetry_ws": 8756
  },
  "intervals": {
    "telemetry": 5,
    "heartbeat": 30
  },
  "logging": {
    "level": "INFO",
    "max_bytes": 10485760,
    "backup_count": 5
  }
}
```

### Secrets File (`/etc/resolvix/secrets.json`)

```json
{
  "db_password": "your_db_password_here",
  "telemetry_jwt_token": "your_jwt_token_here",
  "auth_token": "install_auth_token"
}
```

**Important:** Set permissions to 600:
```bash
sudo chmod 600 /etc/resolvix/secrets.json
```

---

## 🔍 Monitoring & Debugging

### Check Daemon Logs

```bash
# Live tail
tail -f /var/log/resolvix.log

# Search for config-related logs
grep -i config /var/log/resolvix.log

# Check last 50 config operations
grep "\[Config\]" /var/log/resolvix.log | tail -50
```

### Verify Config Loaded

```bash
# Check config via API
curl -s http://localhost:8754/api/config | jq '.config.intervals'

# Check cache file
cat /etc/resolvix/config_cache.json | jq
```

### Test Backend Connection

```bash
# Test backend settings endpoint
curl http://localhost:3000/api/settings/daemon/server-01

# Force config reload
curl -X POST http://localhost:8754/api/config/reload
```

---

## 📊 Message Format Examples

### Before (Old Format)

```json
{
  "timestamp": "2025-12-18T10:30:45Z",
  "system_ip": "192.168.1.100",
  "log_path": "/var/log/nginx/error.log",
  "application": "nginx",
  "log_line": "2025/12/18 10:30:45 [error] connection refused",
  "severity": "error"
}
```

### After (New Format)

```json
{
  "timestamp": "2025-12-18T10:30:45Z",
  "system_ip": "192.168.1.100",
  "log_path": "/var/log/nginx/error.log",
  "log_label": "nginx_errors",      // ✅ Auto-detected
  "application": "nginx_errors",
  "log_line": "2025/12/18 10:30:45 [error] connection refused",
  "severity": "error",
  "priority": "high"                 // ✅ Dynamic based on keywords
}
```

---

## 🎯 Frontend Integration Examples

### Display Config in UI

```javascript
// Fetch config
const response = await fetch('http://daemon-ip:8754/api/config');
const data = await response.json();

console.log('Telemetry interval:', data.config.intervals.telemetry);
console.log('CPU threshold:', data.config.alerts.thresholds.cpu_critical.threshold);
```

### Update Settings from UI

```javascript
// Update settings
await fetch('http://daemon-ip:8754/api/config', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    settings: {
      'intervals.telemetry': 10,
      'alerts.thresholds.cpu_critical.threshold': 85
    }
  })
});

// Reload to apply
await fetch('http://daemon-ip:8754/api/config/reload', {
  method: 'POST'
});
```

### Build Config Form

```javascript
// Get schema for validation
const schema = await fetch('http://daemon-ip:8754/api/config/schema')
  .then(r => r.json());

// Use schema to build form with validation
Object.entries(schema.schema).forEach(([key, def]) => {
  console.log(`${key}: ${def.type} (${def.min}-${def.max})`);
  console.log(`  ${def.description}`);
});
```

---

## ⚡ Performance Tips

1. **Cache Locally**: Config syncs every 1 hour by default
2. **Batch Updates**: Use single POST with multiple settings
3. **Hot Reload**: Most settings apply without restart
4. **Monitor Logs**: Watch for config-related warnings

---

## 🔐 Security Best Practices

1. **Protect Secrets File**:
   ```bash
   sudo chmod 600 /etc/resolvix/secrets.json
   sudo chown resolvix:resolvix /etc/resolvix/secrets.json
   ```

2. **Restrict API Access**: Add authentication to config endpoints

3. **Audit Changes**: Log all config modifications with timestamps

4. **Backup Configs**: Keep versioned backups of config files

---

## 📞 Support

**Check Logs**: `/var/log/resolvix.log`  
**Config Files**: `/etc/resolvix/`  
**API Docs**: `CONFIG_IMPLEMENTATION.md`  
**Tests**: `python3 test_config.py`

---

**Last Updated:** December 18, 2025  
**Version:** 1.0.0
