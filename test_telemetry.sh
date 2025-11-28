#!/bin/bash
# Test script to run telemetry WebSocket manually with full debug output

echo "=========================================="
echo "Testing Telemetry WebSocket Server"
echo "=========================================="

cd "$(dirname "$0")"

# Check if telemetry_ws.py exists
if [ ! -f "telemetry_ws.py" ]; then
    echo "❌ ERROR: telemetry_ws.py not found!"
    exit 1
fi

echo "✅ Found telemetry_ws.py"

# Activate venv
if [ -d "venv" ]; then
    echo "✅ Activating virtual environment..."
    source venv/bin/activate
else
    echo "❌ ERROR: venv directory not found!"
    exit 1
fi

# Check Python version
echo "Python version: $(python3 --version)"

# Check if psutil is installed
echo "Checking dependencies..."
python3 -c "import psutil; import websockets; print('✅ Dependencies OK')" || {
    echo "❌ Missing dependencies!"
    exit 1
}

# Get node ID (IP address)
NODE_ID=$(hostname -I | awk '{print $1}')
echo "Node ID: $NODE_ID"

# Run telemetry WebSocket server
echo ""
echo "=========================================="
echo "Starting Telemetry WebSocket Server"
echo "Port: 8756"
echo "Interval: 60 seconds"
echo "=========================================="
echo ""

python3 telemetry_ws.py "$NODE_ID" 8756 --interval 60
