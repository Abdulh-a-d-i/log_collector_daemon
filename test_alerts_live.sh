#!/bin/bash
# test_alerts_live.sh
# Test alert system with actual backend configuration from daemon

set -e

echo "========================================"
echo "Smart Alert System - Live Test"
echo "========================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get daemon configuration
echo -e "${BLUE}[1/6]${NC} Checking daemon configuration..."

SERVICE_FILE="/etc/systemd/system/resolvix.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}✗ Error: Daemon service file not found${NC}"
    echo "Run install.sh first or check if daemon is installed"
    exit 1
fi

# Extract API URL from service file
API_URL=$(grep -oP 'api-url\s+"\K[^"]+' "$SERVICE_FILE" || echo "")
if [ -z "$API_URL" ]; then
    API_URL=$(grep -oP -- '--api-url\s+\K\S+' "$SERVICE_FILE" || echo "")
fi

if [ -z "$API_URL" ]; then
    echo -e "${RED}✗ Error: Could not find API URL in service file${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Backend URL: $API_URL${NC}"

# Get node information
NODE_IP=$(hostname -I | awk '{print $1}')
NODE_HOSTNAME=$(hostname)

echo -e "${GREEN}✓ Node IP: $NODE_IP${NC}"
echo -e "${GREEN}✓ Hostname: $NODE_HOSTNAME${NC}"
echo ""

# Check if venv exists
echo -e "${BLUE}[2/6]${NC} Checking Python environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo -e "${RED}✗ Error: Virtual environment not found${NC}"
    echo "Run install.sh first"
    exit 1
fi

source venv/bin/activate

# Check if alert modules exist
if [ ! -f "alert_manager.py" ] || [ ! -f "alert_config.py" ]; then
    echo -e "${RED}✗ Error: Alert modules not found${NC}"
    echo "Upload alert_manager.py and alert_config.py"
    exit 1
fi

echo -e "${GREEN}✓ Alert modules found${NC}"
echo ""

# Test backend connectivity
echo -e "${BLUE}[3/6]${NC} Testing backend connectivity..."

BACKEND_BASE=$(echo "$API_URL" | sed 's|/api/.*||')
ALERT_ENDPOINT="${BACKEND_BASE}/api/alerts/create"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$ALERT_ENDPOINT" \
    -H "Content-Type: application/json" \
    -d '{"title":"test"}' \
    --connect-timeout 5 || echo "000")

if [ "$HTTP_CODE" = "000" ]; then
    echo -e "${RED}✗ Error: Cannot connect to backend${NC}"
    echo "Backend URL: $ALERT_ENDPOINT"
    echo "Check if backend is running and reachable"
    exit 1
elif [ "$HTTP_CODE" = "404" ]; then
    echo -e "${YELLOW}⚠ Warning: Endpoint /api/alerts/create not found (HTTP 404)${NC}"
    echo "Backend is reachable but alert endpoint may not be implemented"
    echo "Continuing anyway..."
elif [ "$HTTP_CODE" = "500" ]; then
    echo -e "${YELLOW}⚠ Warning: Backend error (HTTP 500)${NC}"
    echo "Backend is reachable but returned server error"
    echo "Continuing anyway..."
else
    echo -e "${GREEN}✓ Backend is reachable (HTTP $HTTP_CODE)${NC}"
fi

echo ""

# Check if daemon has alert manager enabled
echo -e "${BLUE}[4/6]${NC} Checking daemon alert status..."

if grep -q "AlertManager.*enabled" /var/log/resolvix.log 2>/dev/null; then
    echo -e "${GREEN}✓ Alert manager is enabled in daemon${NC}"
elif grep -q "AlertManager.*Disabled" /var/log/resolvix.log 2>/dev/null; then
    echo -e "${YELLOW}⚠ Warning: Alert manager is disabled in daemon${NC}"
    echo "Restart daemon after uploading alert files"
else
    echo -e "${YELLOW}⚠ Warning: Cannot determine alert manager status${NC}"
    echo "Check daemon logs: tail /var/log/resolvix.log"
fi

echo ""

# Show test menu
echo -e "${BLUE}[5/6]${NC} Select test to run:"
echo ""
echo "1. Disk Alert (immediate - recommended for testing)"
echo "2. CPU Alert (requires 5 minutes of sustained high CPU)"
echo "3. Memory Alert (requires 5 minutes of sustained high memory)"
echo "4. Process Count Alert (requires 5 minutes above threshold)"
echo "5. Custom test (interactive)"
echo "0. Exit"
echo ""
read -p "Select test (0-5): " TEST_CHOICE

case $TEST_CHOICE in
    0)
        echo "Exiting..."
        exit 0
        ;;
    1)
        echo ""
        echo -e "${BLUE}[6/6]${NC} Running Disk Alert Test..."
        echo "Simulating disk usage at 92% (critical threshold is 90%)"
        echo ""
        
        python3 << EOF
from alert_manager import AlertManager

alert_mgr = AlertManager(
    backend_url="$API_URL",
    hostname="$NODE_HOSTNAME",
    ip_address="$NODE_IP"
)

print("Sending disk alert...")
alert_mgr.check_disk_alert(92.5)
print("Done!")
EOF
        ;;
    2)
        echo ""
        echo -e "${BLUE}[6/6]${NC} Running CPU Alert Test..."
        echo "Simulating CPU at 95% for 6 minutes (alert after 5 min)"
        echo "Press Ctrl+C to stop"
        echo ""
        
        python3 << EOF
import time
from alert_manager import AlertManager

alert_mgr = AlertManager(
    backend_url="$API_URL",
    hostname="$NODE_HOSTNAME",
    ip_address="$NODE_IP"
)

print("Simulating high CPU...")
for i in range(360):
    alert_mgr.check_cpu_alert(95.5)
    elapsed = i + 1
    mins = elapsed // 60
    secs = elapsed % 60
    print(f"Elapsed: {mins}m {secs}s - CPU at 95.5%   ", end='\r')
    time.sleep(1)
    
    if elapsed == 300:
        print("\n✓ Alert should have been sent!")

print("\nTest completed!")
EOF
        ;;
    3)
        echo ""
        echo -e "${BLUE}[6/6]${NC} Running Memory Alert Test..."
        echo "Simulating memory at 96% for 6 minutes (alert after 5 min)"
        echo "Press Ctrl+C to stop"
        echo ""
        
        python3 << EOF
import time
from alert_manager import AlertManager

alert_mgr = AlertManager(
    backend_url="$API_URL",
    hostname="$NODE_HOSTNAME",
    ip_address="$NODE_IP"
)

print("Simulating high memory...")
for i in range(360):
    alert_mgr.check_memory_alert(96.2)
    elapsed = i + 1
    mins = elapsed // 60
    secs = elapsed % 60
    print(f"Elapsed: {mins}m {secs}s - Memory at 96.2%   ", end='\r')
    time.sleep(1)
    
    if elapsed == 300:
        print("\n✓ Alert should have been sent!")

print("\nTest completed!")
EOF
        ;;
    4)
        echo ""
        echo -e "${BLUE}[6/6]${NC} Running Process Count Alert Test..."
        echo "Simulating 550 processes for 6 minutes (alert after 5 min)"
        echo "Press Ctrl+C to stop"
        echo ""
        
        python3 << EOF
import time
from alert_manager import AlertManager

alert_mgr = AlertManager(
    backend_url="$API_URL",
    hostname="$NODE_HOSTNAME",
    ip_address="$NODE_IP"
)

print("Simulating high process count...")
for i in range(360):
    alert_mgr.check_process_count(550)
    elapsed = i + 1
    mins = elapsed // 60
    secs = elapsed % 60
    print(f"Elapsed: {mins}m {secs}s - Processes: 550   ", end='\r')
    time.sleep(1)
    
    if elapsed == 300:
        print("\n✓ Alert should have been sent!")

print("\nTest completed!")
EOF
        ;;
    5)
        echo ""
        echo -e "${BLUE}[6/6]${NC} Custom Interactive Test"
        echo ""
        read -p "Enter alert type (cpu_critical/memory_critical/disk_critical): " ALERT_TYPE
        read -p "Enter metric value (e.g., 95.5): " METRIC_VALUE
        read -p "Enter duration in seconds (0 for immediate): " DURATION
        
        python3 << EOF
import time
from alert_manager import AlertManager

alert_mgr = AlertManager(
    backend_url="$API_URL",
    hostname="$NODE_HOSTNAME",
    ip_address="$NODE_IP"
)

alert_type = "$ALERT_TYPE"
metric_value = float("$METRIC_VALUE")
duration = int("$DURATION")

if "cpu" in alert_type:
    check_func = alert_mgr.check_cpu_alert
elif "memory" in alert_type:
    check_func = alert_mgr.check_memory_alert
elif "disk" in alert_type:
    check_func = alert_mgr.check_disk_alert
else:
    print("Unknown alert type")
    exit(1)

if duration == 0:
    print(f"Sending {alert_type} alert immediately...")
    check_func(metric_value)
else:
    print(f"Simulating {alert_type} for {duration} seconds...")
    for i in range(duration + 60):
        check_func(metric_value)
        print(f"Elapsed: {i+1}s", end='\r')
        time.sleep(1)

print("\nDone!")
EOF
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo "Verification Steps:"
echo "========================================"
echo ""
echo "1. Check daemon logs:"
echo -e "   ${YELLOW}tail -f /var/log/resolvix.log | grep ALERT${NC}"
echo ""
echo "2. Check backend for new ticket/alert at:"
echo -e "   ${YELLOW}$ALERT_ENDPOINT${NC}"
echo ""
echo "3. Look for these messages in logs:"
echo -e "   ${GREEN}[ALERT] ✓ Ticket created for ...${NC}"
echo -e "   ${RED}[ALERT] ✗ Failed to create ticket ...${NC}"
echo ""
echo "4. Check daemon alert status:"
echo -e "   ${YELLOW}grep AlertManager /var/log/resolvix.log | tail -5${NC}"
echo ""

exit 0
