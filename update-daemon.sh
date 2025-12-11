#!/bin/bash

# Quick update script - Restarts daemon after code changes
# Run this after pulling latest code

set -e

echo "========================================="
echo "  Resolvix Daemon Update Script"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run as root (sudo ./update-daemon.sh)${NC}"
    exit 1
fi

# Find daemon directory
DAEMON_DIR=$(ps aux | grep -oP 'python3?\s+\K[^\s]+(?=/log_collector_daemon\.py)' | head -1 | xargs dirname 2>/dev/null)
if [ -z "$DAEMON_DIR" ]; then
    echo -e "${YELLOW}⚠️  Daemon not running, checking common locations...${NC}"
    for DIR in /opt/resolvix-daemon /root/log_collector_daemon; do
        if [ -d "$DIR" ]; then
            DAEMON_DIR="$DIR"
            break
        fi
    done
fi

if [ -z "$DAEMON_DIR" ]; then
    echo -e "${RED}❌ Cannot find daemon directory${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Found daemon at: $DAEMON_DIR${NC}"
echo ""

# Pull latest code
echo "1. Pulling latest code from Git..."
cd "$DAEMON_DIR"
if git pull origin main 2>/dev/null; then
    echo -e "${GREEN}✅ Code updated${NC}"
else
    echo -e "${YELLOW}⚠️  Not a git repo or no changes${NC}"
fi
echo ""

# Check Python dependencies
echo "2. Checking Python dependencies..."
if [ -f "$DAEMON_DIR/requirements.txt" ]; then
    source "$DAEMON_DIR/venv/bin/activate"
    pip install -q -r requirements.txt
    echo -e "${GREEN}✅ Dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  No requirements.txt found${NC}"
fi
echo ""

# Restart daemon
echo "3. Restarting daemon service..."
systemctl restart resolvix
sleep 2

if systemctl is-active --quiet resolvix; then
    echo -e "${GREEN}✅ Daemon restarted successfully${NC}"
else
    echo -e "${RED}❌ Daemon failed to start${NC}"
    echo "Checking logs:"
    journalctl -u resolvix -n 20 --no-pager
    exit 1
fi
echo ""

# Verify daemon is responding
echo "4. Testing daemon endpoints..."
sleep 1

# Test health endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8754/api/health)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ /api/health responding (HTTP 200)${NC}"
    RESPONSE=$(curl -s http://localhost:8754/api/health)
    echo "   → Response: $RESPONSE"
else
    echo -e "${RED}❌ /api/health returned HTTP $HTTP_CODE${NC}"
fi

# Test status endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8754/api/status)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ /api/status responding (HTTP 200)${NC}"
else
    echo -e "${YELLOW}⚠️  /api/status returned HTTP $HTTP_CODE${NC}"
fi

# Test processes endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8754/api/processes)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ /api/processes responding (HTTP 200)${NC}"
else
    echo -e "${YELLOW}⚠️  /api/processes returned HTTP $HTTP_CODE${NC}"
fi
echo ""

# Show recent logs
echo "5. Recent daemon logs:"
tail -n 10 /var/log/resolvix.log | sed 's/^/   /'
echo ""

echo "========================================="
echo -e "${GREEN}✅ Update complete!${NC}"
echo "========================================="
echo ""
echo "Next steps:"
echo "  • Test from backend: curl http://$(hostname -I | awk '{print $1}'):8754/api/health"
echo "  • Check process endpoint: curl http://$(hostname -I | awk '{print $1}'):8754/api/processes"
echo "  • Monitor logs: tail -f /var/log/resolvix.log"
