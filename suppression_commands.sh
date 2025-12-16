#!/bin/bash
# Example commands for running daemon with suppression rules

# ================================================
# PRODUCTION DEPLOYMENT
# ================================================

# Run daemon with suppression rules enabled
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://13.235.113.192:3000/api/ticket \
  --db-host 140.238.255.110 \
  --db-name resolvix_db \
  --db-user resolvix_user \
  --db-password your_secure_password \
  --db-port 5432 \
  --control-port 8754 \
  --ws-port 8755 \
  --telemetry-ws-port 8756

# ================================================
# TESTING / DEVELOPMENT
# ================================================

# Run without suppression (no database)
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://localhost:3000/api/ticket

# Run with local database
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://localhost:3000/api/ticket \
  --db-host localhost \
  --db-name resolvix_dev \
  --db-user postgres \
  --db-password postgres

# ================================================
# SYSTEMD SERVICE UPDATE
# ================================================

# Edit service file to include database credentials
sudo nano /etc/systemd/system/resolvix.service

# Add to ExecStart line:
#   --db-host YOUR_DB_HOST \
#   --db-name YOUR_DB_NAME \
#   --db-user YOUR_DB_USER \
#   --db-password YOUR_DB_PASSWORD

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart resolvix
sudo systemctl status resolvix

# ================================================
# VERIFY SUPPRESSION IS WORKING
# ================================================

# Check daemon logs
tail -f /var/log/resolvix.log | grep -E "SuppressionChecker|SUPPRESSED"

# Check daemon status
curl http://localhost:8754/api/status | jq .suppression_rules

# Expected output:
# {
#   "enabled": true,
#   "statistics": {
#     "total_checks": 100,
#     "total_suppressed": 25,
#     "suppression_rate": 25.0,
#     "cached_rules": 3
#   }
# }

# ================================================
# DATABASE MANAGEMENT
# ================================================

# Create a test suppression rule
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d YOUR_DB_NAME << EOF
INSERT INTO suppression_rules (name, match_text, node_ip, duration_type, enabled)
VALUES ('Test Rule', 'test error', NULL, 'forever', true);
EOF

# View all active rules
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d YOUR_DB_NAME << EOF
SELECT id, name, match_text, node_ip, match_count, last_matched_at, enabled
FROM suppression_rules
WHERE enabled = true
ORDER BY match_count DESC;
EOF

# Check rule statistics
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d YOUR_DB_NAME << EOF
SELECT 
    name,
    match_count,
    last_matched_at,
    CASE WHEN last_matched_at IS NULL THEN 'Never' 
         ELSE (NOW() - last_matched_at)::TEXT 
    END as time_since_match
FROM suppression_rules
WHERE enabled = true
ORDER BY match_count DESC;
EOF

# Disable a rule (don't delete - keep history)
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d YOUR_DB_NAME << EOF
UPDATE suppression_rules SET enabled = false WHERE id = 1;
EOF

# ================================================
# TROUBLESHOOTING
# ================================================

# Test database connection
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d YOUR_DB_NAME -c "SELECT NOW()"

# Check if psycopg2 is installed
python3 -c "import psycopg2; print('✓ psycopg2 available')"

# Run test suite
python3 test_suppression.py

# Monitor suppression in real-time
watch -n 5 'curl -s http://localhost:8754/api/status | jq .suppression_rules'

# Check daemon process and arguments
ps aux | grep log_collector_daemon.py

# ================================================
# LOGS ANALYSIS
# ================================================

# Count suppressed errors
grep "SUPPRESSED" /var/log/resolvix.log | wc -l

# Show suppressed errors by rule
grep "SUPPRESSED" /var/log/resolvix.log | grep -oP "rule: \K[^(]+" | sort | uniq -c | sort -rn

# Recent suppressions
tail -100 /var/log/resolvix.log | grep "SUPPRESSED"

# ================================================
# PERFORMANCE MONITORING
# ================================================

# Check suppression check performance
grep "suppression" /var/log/resolvix.log | grep -i "slow\|timeout\|error"

# Monitor database queries
# (Enable PostgreSQL query logging)
# tail -f /var/log/postgresql/postgresql.log | grep suppression_rules
