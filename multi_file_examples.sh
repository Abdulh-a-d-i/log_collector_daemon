#!/bin/bash
# Multi-File Log Monitoring - Usage Examples
# Option B Implementation

echo "=========================================="
echo "Multi-File Log Monitoring - Examples"
echo "=========================================="

# Example 1: Basic - Monitor 2 files
echo -e "\n1. Basic: Monitor System and Apache logs"
echo "-------------------------------------------"
cat << 'EOF'
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --api-url http://13.235.113.192:3000/api/ticket \
  --control-port 8754
EOF

# Example 2: Multiple web server logs
echo -e "\n2. Web Servers: Apache + Nginx"
echo "-------------------------------------------"
cat << 'EOF'
python3 log_collector_daemon.py \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/nginx/error.log \
  --api-url http://13.235.113.192:3000/api/ticket
EOF

# Example 3: Full stack monitoring
echo -e "\n3. Full Stack: System + Web + Database"
echo "-------------------------------------------"
cat << 'EOF'
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/nginx/error.log \
  --log-file /var/log/mysql/error.log \
  --api-url http://13.235.113.192:3000/api/ticket
EOF

# Example 4: With suppression rules
echo -e "\n4. With Suppression Rules"
echo "-------------------------------------------"
cat << 'EOF'
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/nginx/error.log \
  --api-url http://13.235.113.192:3000/api/ticket \
  --db-host 140.238.255.110 \
  --db-name resolvix_db \
  --db-user resolvix_user \
  --db-password resolvix4321 \
  --db-port 5432
EOF

# Example 5: With telemetry
echo -e "\n5. With Telemetry Backend"
echo "-------------------------------------------"
cat << 'EOF'
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --api-url http://13.235.113.192:3000/api/ticket \
  --telemetry-backend-url http://13.235.113.192:3000 \
  --telemetry-jwt-token "your-jwt-token-here" \
  --telemetry-interval 5
EOF

# Example 6: Custom ports
echo -e "\n6. Custom Ports Configuration"
echo "-------------------------------------------"
cat << 'EOF'
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --api-url http://13.235.113.192:3000/api/ticket \
  --control-port 8754 \
  --ws-port 8755 \
  --telemetry-ws-port 8756
EOF

# Example 7: Systemd service
echo -e "\n7. Systemd Service File"
echo "-------------------------------------------"
cat << 'EOF'
[Unit]
Description=Resolvix Log Collector Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/resolvix
ExecStart=/opt/resolvix/venv/bin/python3 /opt/resolvix/log_collector_daemon.py \
  --log-file "/var/log/syslog" \
  --log-file "/var/log/apache2/error.log" \
  --log-file "/var/log/nginx/error.log" \
  --api-url "http://13.235.113.192:3000/api/ticket" \
  --db-host "140.238.255.110" \
  --db-name "resolvix_db" \
  --db-user "resolvix_user" \
  --db-password "resolvix4321"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Example 8: Check status
echo -e "\n8. Check Daemon Status"
echo "-------------------------------------------"
cat << 'EOF'
# Get full status
curl http://localhost:8754/api/status | jq

# Get only monitored files
curl http://localhost:8754/api/status | jq .monitored_files

# Check if daemon is running
curl -s http://localhost:8754/api/status | jq -r '.monitored_files.count'
EOF

# Example 9: Testing setup
echo -e "\n9. Quick Test Setup"
echo "-------------------------------------------"
cat << 'EOF'
# Create test log files
touch /tmp/test1.log /tmp/test2.log /tmp/test3.log

# Start daemon
python3 log_collector_daemon.py \
  --log-file /tmp/test1.log \
  --log-file /tmp/test2.log \
  --log-file /tmp/test3.log \
  --api-url http://localhost:3000/api/ticket &

# Generate test errors
echo "ERROR: Test error in file 1" >> /tmp/test1.log
echo "CRITICAL: Test critical in file 2" >> /tmp/test2.log
echo "FAILURE: Test failure in file 3" >> /tmp/test3.log

# Watch daemon logs
tail -f /var/log/resolvix.log | grep "Issue detected"

# Cleanup
pkill -f log_collector_daemon.py
rm /tmp/test*.log
EOF

# Example 10: Production deployment
echo -e "\n10. Production Deployment"
echo "-------------------------------------------"
cat << 'EOF'
# 1. Stop existing daemon
sudo systemctl stop resolvix-daemon

# 2. Update service file with multiple log files
sudo nano /etc/systemd/system/resolvix-daemon.service

# 3. Reload systemd
sudo systemctl daemon-reload

# 4. Start daemon
sudo systemctl start resolvix-daemon

# 5. Verify status
sudo systemctl status resolvix-daemon
curl http://localhost:8754/api/status | jq .monitored_files

# 6. Check logs
sudo tail -f /var/log/resolvix.log
EOF

echo -e "\n=========================================="
echo "For more information:"
echo "  - Full Guide: MULTI_FILE_MONITORING_GUIDE.md"
echo "  - Implementation: OPTION_B_IMPLEMENTATION.md"
echo "=========================================="
