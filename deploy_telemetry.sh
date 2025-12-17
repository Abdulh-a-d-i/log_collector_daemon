#!/bin/bash
# deploy_telemetry.sh
# Deploy telemetry updates to server

set -e

echo "========================================"
echo "TELEMETRY DEPLOYMENT SCRIPT"
echo "========================================"

# Configuration - UPDATE THESE
NODE_IP="your-node-ip-here"
BACKEND_URL="http://localhost:3000"
JWT_TOKEN="your-jwt-token-here"

# Files to deploy
FILES=(
    "telemetry_queue.py"
    "telemetry_poster.py"
    "log_collector_daemon.py"
    "telemetry_ws.py"
)

echo ""
echo "Configuration:"
echo "  Node: $NODE_IP"
echo "  Backend: $BACKEND_URL"
echo "  JWT Token: ${JWT_TOKEN:0:20}..."
echo ""

read -p "Deploy to $NODE_IP? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 1
fi

echo ""
echo "Step 1: Copying files..."
for file in "${FILES[@]}"; do
    echo "  Copying $file..."
    scp "$file" "bitnami@$NODE_IP:/home/bitnami/log-horizon-daemon/"
done
echo "✅ Files copied"

echo ""
echo "Step 2: Creating queue directory..."
ssh "bitnami@$NODE_IP" "sudo mkdir -p /var/lib/resolvix && sudo chown bitnami:bitnami /var/lib/resolvix"
echo "✅ Queue directory created"

echo ""
echo "Step 3: Updating systemd service..."
ssh "bitnami@$NODE_IP" << 'EOF'
# Update service file to include telemetry parameters
sudo sed -i '/^ExecStart/s/$/ --telemetry-backend-url http:\/\/localhost:3000 --telemetry-jwt-token YOUR_TOKEN_HERE/' /etc/systemd/system/resolvix-daemon.service
sudo systemctl daemon-reload
EOF
echo "✅ Service updated"

echo ""
echo "⚠️  IMPORTANT: You need to manually edit the service file to add your JWT token:"
echo "   sudo nano /etc/systemd/system/resolvix-daemon.service"
echo "   Add these flags to ExecStart:"
echo "     --telemetry-backend-url $BACKEND_URL"
echo "     --telemetry-jwt-token $JWT_TOKEN"
echo ""

read -p "Have you updated the service file? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please update the service file before restarting"
    exit 1
fi

echo ""
echo "Step 4: Restarting daemon..."
ssh "bitnami@$NODE_IP" "sudo systemctl restart resolvix-daemon"
sleep 3
echo "✅ Daemon restarted"

echo ""
echo "Step 5: Checking status..."
ssh "bitnami@$NODE_IP" "sudo systemctl status resolvix-daemon --no-pager"

echo ""
echo "Step 6: Checking logs for telemetry initialization..."
ssh "bitnami@$NODE_IP" "sudo journalctl -u resolvix-daemon --since '30 seconds ago' | grep -i telemetry"

echo ""
echo "========================================"
echo "DEPLOYMENT COMPLETE"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Monitor logs: sudo journalctl -u resolvix-daemon -f"
echo "2. Check queue: python3 -c 'from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_stats())'"
echo "3. Verify backend receiving data"
echo ""
