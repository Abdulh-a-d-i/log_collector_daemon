#!/bin/bash

# Resolvix Daemon Diagnostics Script
# This script checks if the daemon is properly installed and running

echo "======================================"
echo "   Resolvix Daemon Diagnostics"
echo "======================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check results counter
PASSED=0
FAILED=0

# Function to print result
check_result() {
    if [ $1 -eq 0 ]; then
        echo -e "   ${GREEN}✅ PASS${NC}: $2"
        ((PASSED++))
    else
        echo -e "   ${RED}❌ FAIL${NC}: $2"
        ((FAILED++))
    fi
}

# 1. Check if daemon service exists
echo "1. Checking if daemon service exists..."
if systemctl list-unit-files | grep -q "resolvix.service"; then
    check_result 0 "Service file exists at /etc/systemd/system/resolvix.service"
else
    check_result 1 "Service file NOT found - daemon may not be installed"
fi
echo ""

# 2. Check daemon service status
echo "2. Checking daemon service status..."
if systemctl is-active --quiet resolvix; then
    check_result 0 "Daemon service is running"
    UPTIME=$(systemctl show resolvix --property=ActiveEnterTimestamp | cut -d= -f2)
    echo "   → Started: $UPTIME"
else
    check_result 1 "Daemon service is NOT running"
    echo "   → Run: sudo systemctl start resolvix"
fi
echo ""

# 3. Check if port 8754 is listening
echo "3. Checking if port 8754 is listening..."
if sudo ss -tulpn | grep -q ":8754 "; then
    check_result 0 "Port 8754 is listening"
    PORT_INFO=$(sudo ss -tulpn | grep ":8754 ")
    echo "   → $PORT_INFO"
else
    check_result 1 "Port 8754 is NOT listening"
    echo "   → Daemon may not be running or binding to wrong port"
fi
echo ""

# 4. Check if daemon process is running
echo "4. Checking if daemon process is running..."
if pgrep -f "log_collector_daemon.py" > /dev/null; then
    check_result 0 "Daemon process found"
    PID=$(pgrep -f "log_collector_daemon.py")
    echo "   → PID: $PID"
    echo "   → Command: $(ps -p $PID -o cmd --no-headers)"
else
    check_result 1 "Daemon process NOT found"
fi
echo ""

# 5. Test local HTTP connection
echo "5. Testing local HTTP connection to daemon..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8754/api/health 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    check_result 0 "Daemon responds to HTTP requests (HTTP 200)"
    RESPONSE=$(curl -s http://localhost:8754/api/health)
    echo "   → Response: $RESPONSE"
elif [ "$HTTP_CODE" = "000" ]; then
    check_result 1 "Cannot connect to daemon (connection refused)"
else
    check_result 1 "Daemon returned HTTP $HTTP_CODE (expected 200)"
fi
echo ""

# 6. Check daemon log file
echo "6. Checking daemon log file..."
if [ -f "/var/log/resolvix.log" ]; then
    check_result 0 "Log file exists at /var/log/resolvix.log"
    LOG_SIZE=$(du -h /var/log/resolvix.log | cut -f1)
    echo "   → Size: $LOG_SIZE"
    echo "   → Last 5 lines:"
    sudo tail -n 5 /var/log/resolvix.log | sed 's/^/      /'
else
    check_result 1 "Log file NOT found at /var/log/resolvix.log"
fi
echo ""

# 7. Check for errors in recent logs
echo "7. Checking for errors in recent logs..."
if [ -f "/var/log/resolvix.log" ]; then
    ERROR_COUNT=$(sudo grep -i "error\|exception\|failed" /var/log/resolvix.log | tail -n 20 | wc -l)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo -e "   ${YELLOW}⚠️  WARNING${NC}: Found $ERROR_COUNT error-related messages in recent logs"
        echo "   → Recent errors:"
        sudo grep -i "error\|exception\|failed" /var/log/resolvix.log | tail -n 5 | sed 's/^/      /'
    else
        check_result 0 "No recent errors found in logs"
    fi
else
    echo "   → Skipped (log file not found)"
fi
echo ""

# 8. Check firewall rules
echo "8. Checking firewall rules for port 8754..."
if command -v ufw &> /dev/null; then
    if sudo ufw status | grep -q "8754"; then
        check_result 0 "UFW rule exists for port 8754"
        sudo ufw status | grep 8754 | sed 's/^/   → /'
    else
        echo -e "   ${YELLOW}⚠️  WARNING${NC}: No UFW rule for port 8754 (may still work if default allows)"
    fi
elif command -v iptables &> /dev/null; then
    if sudo iptables -L INPUT -n | grep -q "8754"; then
        check_result 0 "iptables rule exists for port 8754"
        sudo iptables -L INPUT -n | grep 8754 | sed 's/^/   → /'
    else
        echo -e "   ${YELLOW}⚠️  WARNING${NC}: No iptables rule for port 8754 (may still work if default allows)"
    fi
else
    echo "   → No firewall detected (ufw/iptables)"
fi
echo ""

# 9. Check Python dependencies
echo "9. Checking Python dependencies..."
# Detect daemon directory from running process
DAEMON_DIR=$(ps aux | grep -oP 'python3?\s+\K[^\s]+(?=/log_collector_daemon\.py)' | head -1 | xargs dirname 2>/dev/null)
if [ -z "$DAEMON_DIR" ]; then
    # Fallback to common locations
    for DIR in /opt/resolvix-daemon /root/log_collector_daemon; do
        if [ -d "$DIR" ]; then
            DAEMON_DIR="$DIR"
            break
        fi
    done
fi

if [ -n "$DAEMON_DIR" ] && [ -f "$DAEMON_DIR/venv/bin/python" ]; then
    check_result 0 "Virtual environment exists at $DAEMON_DIR/venv"
    PYTHON_VERSION=$($DAEMON_DIR/venv/bin/python --version 2>&1)
    echo "   → $PYTHON_VERSION"
    
    # Check key modules
    for MODULE in flask psutil requests pika; do
        if $DAEMON_DIR/venv/bin/python -c "import $MODULE" 2>/dev/null; then
            echo "   → Module $MODULE: ✅ installed"
        else
            echo -e "   → Module $MODULE: ${RED}❌ missing${NC}"
        fi
    done
elif [ -n "$DAEMON_DIR" ]; then
    check_result 1 "Daemon directory found at $DAEMON_DIR but venv missing"
else
    check_result 1 "Cannot determine daemon directory"
fi
echo ""

# 10. Test network connectivity (external)
echo "10. Testing network connectivity to backend..."
# Extract backend URL from running daemon process
BACKEND_URL=$(ps aux | grep log_collector_daemon | grep -oP -- '--api-url\s+\K[^\s]+' | head -1)
if [ -z "$BACKEND_URL" ]; then
    BACKEND_URL="http://13.235.113.192:3000"
fi
BACKEND_HOST=$(echo $BACKEND_URL | sed -E 's|https?://([^:/]+).*|\1|')
if ping -c 1 -W 2 $BACKEND_HOST &> /dev/null; then
    check_result 0 "Backend host $BACKEND_HOST is reachable"
else
    echo -e "   ${YELLOW}⚠️  WARNING${NC}: Cannot ping backend host $BACKEND_HOST (extracted: $BACKEND_URL)"
fi
echo ""

# Summary
echo "======================================"
echo "           SUMMARY"
echo "======================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed! Daemon is healthy.${NC}"
    echo ""
    echo "You can now test from your backend server:"
    echo "  curl http://$(hostname -I | awk '{print $1}'):8754/api/health"
    exit 0
elif [ $FAILED -le 2 ]; then
    echo -e "${YELLOW}⚠️  Some checks failed, but daemon may still work.${NC}"
    echo "Review the failed checks above."
    exit 1
else
    echo -e "${RED}❌ Multiple checks failed. Daemon is likely not working.${NC}"
    echo ""
    echo "Recommended actions:"
    echo "1. Check if daemon is installed: ls -la $DAEMON_DIR"
    echo "2. Check service status: sudo systemctl status resolvix"
    echo "3. Check logs: sudo tail -n 100 /var/log/resolvix.log"
    echo "4. Restart daemon: sudo systemctl restart resolvix"
    exit 2
fi
