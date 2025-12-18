# Multi-File Monitoring - Quick Reference

**Version:** 2.0 (Option B)  
**Date:** December 18, 2025

---

## 🚀 Quick Start

### Monitor Multiple Files
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/nginx/error.log \
  --api-url http://backend:3000/api/ticket
```

### Check Status
```bash
curl http://localhost:8754/api/status | jq .monitored_files
```

---

## 📖 Common Commands

### Start Daemon (Multiple Files)
```bash
# System + Web server logs
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --api-url http://13.235.113.192:3000/api/ticket
```

### With Suppression Rules
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --api-url http://13.235.113.192:3000/api/ticket \
  --db-host 140.238.255.110 \
  --db-name resolvix_db \
  --db-user resolvix_user \
  --db-password resolvix4321
```

### Check Monitored Files
```bash
# Full status
curl http://localhost:8754/api/status | jq

# Just file count
curl -s http://localhost:8754/api/status | jq -r '.monitored_files.count'

# List all files
curl -s http://localhost:8754/api/status | jq '.monitored_files.files'
```

### Watch Daemon Logs
```bash
# Follow daemon logs
tail -f /var/log/resolvix.log

# Watch for errors
tail -f /var/log/resolvix.log | grep "Issue detected"

# Watch specific file
tail -f /var/log/resolvix.log | grep "\[syslog\]"
```

---

## 📋 Command Line Arguments

| Argument | Required | Example | Notes |
|----------|----------|---------|-------|
| `--log-file` | ✅ Yes (1+) | `/var/log/syslog` | Can specify multiple times |
| `--api-url` | ✅ Yes | `http://backend:3000/api/ticket` | Central API endpoint |
| `--control-port` | ❌ No | `8754` | Default: 8754 |
| `--ws-port` | ❌ No | `8755` | Default: 8755 |
| `--telemetry-ws-port` | ❌ No | `8756` | Default: 8756 |
| `--node-id` | ❌ No | `server-01` | Auto-detected if not set |
| `--db-host` | ❌ No | `140.238.255.110` | For suppression rules |
| `--db-name` | ❌ No | `resolvix_db` | Database name |
| `--db-user` | ❌ No | `resolvix_user` | Database user |
| `--db-password` | ❌ No | `secret` | Database password |

---

## 🎯 Common Scenarios

### Scenario 1: Web Server
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/nginx/error.log \
  --api-url http://backend:3000/api/ticket
```

### Scenario 2: Database Server
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/mysql/error.log \
  --log-file /var/log/postgresql/postgresql.log \
  --api-url http://backend:3000/api/ticket
```

### Scenario 3: Application Server
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/application/app.log \
  --log-file /var/log/application/errors.log \
  --api-url http://backend:3000/api/ticket
```

### Scenario 4: Full Stack
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/mysql/error.log \
  --log-file /var/log/application/app.log \
  --api-url http://backend:3000/api/ticket
```

---

## 🔧 Systemd Service

### Update Service File
```bash
sudo nano /etc/systemd/system/resolvix-daemon.service
```

Add multiple `--log-file` arguments:
```ini
[Service]
ExecStart=/opt/resolvix/venv/bin/python3 /opt/resolvix/log_collector_daemon.py \
  --log-file "/var/log/syslog" \
  --log-file "/var/log/apache2/error.log" \
  --log-file "/var/log/nginx/error.log" \
  --api-url "http://13.235.113.192:3000/api/ticket"
```

### Reload and Restart
```bash
sudo systemctl daemon-reload
sudo systemctl restart resolvix-daemon
sudo systemctl status resolvix-daemon
```

---

## 📊 Status Endpoint Response

### Example Response
```json
{
  "node_id": "192.168.1.100",
  "monitored_files": {
    "count": 3,
    "files": [
      {
        "path": "/var/log/syslog",
        "label": "syslog",
        "priority": "high"
      },
      {
        "path": "/var/log/apache2/error.log",
        "label": "apache2_error",
        "priority": "high"
      },
      {
        "path": "/var/log/nginx/error.log",
        "label": "nginx_error",
        "priority": "high"
      }
    ]
  },
  "livelogs": {
    "running": false,
    "pid": null,
    "ws_port": 8755
  },
  "telemetry": {
    "running": true,
    "pid": 12345,
    "ws_port": 8756
  }
}
```

---

## 🐛 Troubleshooting

### Problem: "At least one --log-file must be specified"
**Solution:** Add at least one `--log-file` argument
```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://backend:3000/api/ticket
```

### Problem: Files not being monitored
**Check:**
1. File paths are correct
2. Files exist and are readable
3. Daemon has permissions
```bash
# Check file exists
ls -lh /var/log/syslog

# Check permissions
sudo chmod 644 /var/log/syslog

# Check daemon logs
tail -f /var/log/resolvix.log | grep "Started monitoring"
```

### Problem: Can't see monitored files in status
**Check daemon is running:**
```bash
# Check process
ps aux | grep log_collector_daemon

# Check port
netstat -tlnp | grep 8754

# Test status endpoint
curl -v http://localhost:8754/api/status
```

### Problem: Errors not being sent
**Check logs:**
```bash
# Watch for error detection
tail -f /var/log/resolvix.log | grep -E "(Issue detected|RabbitMQ)"

# Generate test error
echo "ERROR: Test error message" | sudo tee -a /var/log/syslog

# Check if error was detected
grep "Issue detected" /var/log/resolvix.log | tail -1
```

---

## 📈 Performance Tips

### Optimal File Count
- ✅ **1-5 files:** Excellent performance
- ✅ **6-10 files:** Good performance
- ⚠️ **11+ files:** Consider Option A (config file)

### Monitor Resource Usage
```bash
# Check CPU and memory
top -p $(pgrep -f log_collector_daemon)

# Check thread count
ps -eL | grep log_collector_daemon | wc -l
```

---

## 📚 More Information

- **Full Guide:** [MULTI_FILE_MONITORING_GUIDE.md](MULTI_FILE_MONITORING_GUIDE.md)
- **Implementation:** [OPTION_B_IMPLEMENTATION.md](OPTION_B_IMPLEMENTATION.md)
- **Summary:** [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Examples:** [multi_file_examples.sh](multi_file_examples.sh)

---

## 🎯 Key Points

1. ✅ Use multiple `--log-file` arguments for multiple files
2. ✅ Each file gets automatic label (from filename)
3. ✅ Status endpoint shows all monitored files
4. ✅ Backward compatible with single file
5. ✅ Works with suppression rules
6. ✅ Recommended: 1-10 files per daemon

---

**Need help?** Check the full documentation or run:
```bash
python3 log_collector_daemon.py --help
```
