# Suppression Rules - Quick Start Guide

## ⚡ 5-Minute Setup

### Step 1: Install psycopg2

```bash
cd /path/to/log_collector_daemon
source venv/bin/activate
pip install psycopg2-binary
```

### Step 2: Create Database Table

```sql
CREATE TABLE suppression_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    match_text TEXT NOT NULL,
    node_ip VARCHAR(50),
    duration_type VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP,
    enabled BOOLEAN DEFAULT true,
    match_count INTEGER DEFAULT 0,
    last_matched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_suppression_enabled ON suppression_rules(enabled);
CREATE INDEX idx_suppression_expires ON suppression_rules(expires_at);
```

### Step 3: Create a Test Rule

```sql
INSERT INTO suppression_rules (name, match_text, node_ip, duration_type, enabled)
VALUES ('Test Suppression', 'test error', NULL, 'forever', true);
```

### Step 4: Start Daemon with Database

```bash
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://your-backend:3000/api/ticket \
  --db-host your-db-host \
  --db-name your_database \
  --db-user your_user \
  --db-password your_password
```

### Step 5: Verify It's Working

**Check logs:**

```bash
tail -f /var/log/resolvix.log | grep SuppressionChecker
```

Expected output:

```
[INFO] [SuppressionChecker] Enabled with database connection
[INFO] SuppressionRuleChecker initialized with cache TTL: 60 seconds
[INFO] Loaded 1 active suppression rules
```

**Check status:**

```bash
curl http://localhost:8754/api/status | jq .suppression_rules
```

Expected output:

```json
{
  "enabled": true,
  "statistics": {
    "total_checks": 0,
    "total_suppressed": 0,
    "suppression_rate": 0.0,
    "cached_rules": 1
  }
}
```

### Step 6: Test Suppression

**Generate a test error:**

```bash
echo "ERROR: This is a test error in the logs" | sudo tee -a /var/log/syslog
```

**Watch the logs:**

```bash
tail -f /var/log/resolvix.log | grep -E "test error|SUPPRESSED"
```

Expected output:

```
[INFO] Issue detected [error]: ERROR: This is a test error in the logs
[INFO] [SUPPRESSED] Error suppressed by rule: Test Suppression (ID: 1)
```

**Check statistics updated:**

```sql
SELECT name, match_count, last_matched_at FROM suppression_rules WHERE name = 'Test Suppression';
```

---

## 🎯 Common Use Cases

### Use Case 1: Suppress Known Maintenance Issue

```sql
-- During planned maintenance window
INSERT INTO suppression_rules (
    name,
    match_text,
    node_ip,
    duration_type,
    expires_at,
    enabled
)
VALUES (
    'Maintenance - DB Upgrade',
    'database connection refused',
    NULL,
    'custom',
    NOW() + INTERVAL '4 hours',
    true
);
```

### Use Case 2: Suppress Noisy Node

```sql
-- Specific node has known issue
INSERT INTO suppression_rules (
    name,
    match_text,
    node_ip,
    duration_type,
    enabled
)
VALUES (
    'Node 5 - Known Network Issue',
    'network timeout',
    '192.168.1.5',
    'forever',
    true
);
```

### Use Case 3: Suppress Pattern Across All Nodes

```sql
-- Common error that doesn't need tickets
INSERT INTO suppression_rules (
    name,
    match_text,
    node_ip,
    duration_type,
    enabled
)
VALUES (
    'Disk Space Warnings',
    'disk space low',
    NULL,
    'forever',
    true
);
```

---

## 🔧 Systemd Service Configuration

**Edit service file:**

```bash
sudo nano /etc/systemd/system/resolvix.service
```

**Add database parameters to ExecStart:**

```ini
[Unit]
Description=Resolvix
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/log_collector_daemon
ExecStart=/home/ubuntu/log_collector_daemon/venv/bin/python3 \
  /home/ubuntu/log_collector_daemon/log_collector_daemon.py \
  --log-file "/var/log/syslog" \
  --api-url "http://13.235.113.192:3000/api/ticket" \
  --db-host "140.238.255.110" \
  --db-name "resolvix_db" \
  --db-user "resolvix_user" \
  --db-password "your_password" \
  --db-port 5432
Restart=always
RestartSec=10
Environment=PATH=/home/ubuntu/log_collector_daemon/venv/bin
StandardOutput=append:/var/log/resolvix.log
StandardError=append:/var/log/resolvix.log

[Install]
WantedBy=multi-user.target
```

**Reload and restart:**

```bash
sudo systemctl daemon-reload
sudo systemctl restart resolvix
sudo systemctl status resolvix
```

---

## 📊 Monitoring Dashboard Queries

### Get Suppression Statistics

```sql
-- Overall statistics
SELECT
    COUNT(*) as total_rules,
    COUNT(*) FILTER (WHERE enabled = true) as active_rules,
    SUM(match_count) as total_suppressions,
    MAX(last_matched_at) as last_activity
FROM suppression_rules;
```

### Top Suppression Rules

```sql
-- Rules that suppressed the most errors
SELECT
    name,
    match_count,
    last_matched_at,
    node_ip,
    CASE WHEN node_ip IS NULL THEN 'All Nodes' ELSE node_ip END as scope
FROM suppression_rules
WHERE enabled = true
ORDER BY match_count DESC
LIMIT 10;
```

### Recently Active Rules

```sql
-- Rules that matched in last 24 hours
SELECT
    name,
    match_text,
    match_count,
    last_matched_at,
    NOW() - last_matched_at as time_since_match
FROM suppression_rules
WHERE last_matched_at > NOW() - INTERVAL '24 hours'
ORDER BY last_matched_at DESC;
```

### Unused Rules

```sql
-- Rules that never matched (consider removing)
SELECT
    name,
    match_text,
    created_at,
    NOW() - created_at as age
FROM suppression_rules
WHERE match_count = 0
  AND enabled = true
ORDER BY created_at;
```

---

## ❓ Troubleshooting

### Problem: Daemon says "Suppression rules: DISABLED"

**Solution 1:** Check database credentials

```bash
psql -h YOUR_HOST -U YOUR_USER -d YOUR_DB -c "SELECT 1"
```

**Solution 2:** Check psycopg2 installation

```bash
python3 -c "import psycopg2; print('OK')"
```

**Solution 3:** Check daemon startup arguments

```bash
ps aux | grep log_collector_daemon.py
# Should show --db-host, --db-name, etc.
```

### Problem: Rules not suppressing errors

**Solution 1:** Check rule is active

```sql
SELECT * FROM suppression_rules WHERE name = 'Your Rule Name';
-- Verify: enabled = true, expires_at is NULL or in future
```

**Solution 2:** Check match_text is correct

```sql
-- Test your pattern
SELECT 'Your actual error message' ILIKE '%your match text%';
-- Should return true
```

**Solution 3:** Force cache reload

```python
# SSH to server, activate venv, run Python
from suppression_checker import SuppressionRuleChecker
import psycopg2
conn = psycopg2.connect(host='...', database='...', user='...', password='...')
checker = SuppressionRuleChecker(conn)
checker.force_reload()
print(f"Loaded {len(checker._rules_cache)} rules")
```

### Problem: Statistics not updating

**Solution:** Check database connection is alive

```bash
# Look for database errors in logs
grep -i "database\|postgres" /var/log/resolvix.log
```

---

## 📚 Additional Resources

- **Full Documentation:** [SUPPRESSION_RULES.md](SUPPRESSION_RULES.md)
- **Test Suite:** `python3 test_suppression.py`
- **Commands Reference:** [suppression_commands.sh](suppression_commands.sh)
- **Main README:** [README.md](README.md)

---

## ✅ Success Checklist

- [ ] psycopg2-binary installed
- [ ] Database table created
- [ ] Test rule created
- [ ] Daemon started with DB credentials
- [ ] Logs show "SuppressionChecker: Enabled"
- [ ] Status endpoint shows suppression stats
- [ ] Test error suppressed correctly
- [ ] Database match_count incremented
- [ ] Systemd service updated (if applicable)

---

**🎉 You're ready to use suppression rules!**

For help: Check logs at `/var/log/resolvix.log` or run `python3 test_suppression.py`
