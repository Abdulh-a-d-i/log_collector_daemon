# New Engineer Onboarding Guide - Resolvix Daemon

Welcome to the Resolvix team! This guide will help you get up to speed quickly.

---

## Day 1: Understanding the System

### What You'll Learn Today

- What Resolvix does and why it exists
- System architecture overview
- Development environment setup

### 1. Read the Executive Summary (30 minutes)

Start with [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md) to understand the business context and high-level architecture.

**Key Takeaways:**

- Resolvix monitors servers for errors and resource issues
- Smart alerting prevents alert fatigue
- Three main components: daemon, backend, and dashboards

### 2. Clone and Setup (30 minutes)

```bash
# Clone repository
git clone https://github.com/yourorg/resolvix-daemon.git
cd resolvix-daemon

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install pytest pytest-cov pylint black ipython
```

### 3. Run Your First Test Instance (45 minutes)

```bash
# Create a test log file
touch test.log

# Start the daemon
python3 log_collector_daemon.py \
    --log-file test.log \
    --api-url http://localhost:3000/api/ticket \
    --node-id test-dev-$(whoami)

# In another terminal, generate test logs
echo "$(date) ERROR: Test error message" >> test.log
echo "$(date) CRITICAL: Test critical message" >> test.log

# Check daemon is running
curl http://localhost:8754/api/health | jq

# View status
curl http://localhost:8754/api/status | jq
```

**Expected Output:**

```json
{
  "status": "healthy",
  "service": "resolvix",
  "version": "1.1.0",
  "components": {
    "log_collector": "running",
    "control_api": "running"
  }
}
```

### 4. Explore the Codebase (60 minutes)

**Start with these files in order:**

1. **log_collector_daemon.py** (main entry point)

   - Look for the `LogCollectorDaemon` class
   - Find the `_monitor_loop()` method - this is where log monitoring happens
   - Notice the `make_app()` function - this creates the Flask API

2. **alert_manager.py** (smart alerting logic)

   - Find `check_cpu_alert()` - see how thresholds work
   - Look at `_handle_threshold_alert()` - duration tracking
   - Check `alert_config.py` for threshold values

3. **telemetry_ws.py** (metrics collection)
   - Find `TelemetryCollector.collect_all_metrics()`
   - Notice how it uses `psutil` to get system metrics
   - See how it checks alert thresholds

**Exercise:**

```python
# Open Python REPL
ipython

# Try collecting system metrics
import psutil

# Get CPU usage
cpu = psutil.cpu_percent(interval=1)
print(f"CPU: {cpu}%")

# Get memory info
mem = psutil.virtual_memory()
print(f"Memory: {mem.percent}%")

# Get disk usage
disk = psutil.disk_usage('/')
print(f"Disk: {disk.percent}%")
```

---

## Day 2: Development Workflow

### What You'll Learn Today

- How to make code changes
- Testing strategies
- Debugging techniques

### 1. Make Your First Change (60 minutes)

**Task:** Add a new log level detection

```python
# Edit log_collector_daemon.py

# Find the detect_severity() function around line 180
def detect_severity(line: str) -> str:
    text = line.lower()
    if any(k in text for k in ["panic", "fatal", "critical", "crit"]):
        return "critical"
    if any(k in text for k in ["fail", "failed", "failure"]):
        return "failure"
    if any(k in text for k in ["err", "error"]):
        return "error"
    if any(k in text for k in ["warn", "warning"]):
        return "warn"
    # ADD THIS LINE:
    if any(k in text for k in ["debug"]):
        return "debug"
    return "info"
```

**Test your change:**

```bash
# Restart daemon
# (Ctrl+C to stop, then restart)

# Generate test log with DEBUG level
echo "$(date) DEBUG: This is a debug message" >> test.log

# Check daemon logs to see if it detected the debug level
tail -f /var/log/resolvix.log
```

### 2. Write a Unit Test (45 minutes)

```python
# Create tests/test_severity_detection.py

import pytest
from log_collector_daemon import detect_severity

def test_detect_critical_severity():
    line = "CRITICAL: System is down"
    assert detect_severity(line) == "critical"

def test_detect_error_severity():
    line = "ERROR: Connection failed"
    assert detect_severity(line) == "error"

def test_detect_debug_severity():
    line = "DEBUG: Variable value is 42"
    assert detect_severity(line) == "debug"

def test_detect_info_severity():
    line = "INFO: Application started"
    assert detect_severity(line) == "info"
```

**Run tests:**

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=. tests/

# Run specific test
pytest tests/test_severity_detection.py::test_detect_debug_severity -v
```

### 3. Debug Common Issues (45 minutes)

**Exercise 1: Fix a "port already in use" error**

```bash
# Problem: Daemon won't start because port 8754 is in use

# Find process using the port
lsof -ti:8754

# Kill it
kill $(lsof -ti:8754)

# Or use a different port
python3 log_collector_daemon.py \
    --log-file test.log \
    --api-url http://localhost:3000/api/ticket \
    --control-port 8755
```

**Exercise 2: Enable debug logging**

```bash
# Edit /etc/resolvix/config.json (or create local config)
{
    "logging": {
        "level": "DEBUG"
    }
}

# Restart daemon and watch detailed logs
tail -f /var/log/resolvix.log
```

**Exercise 3: Use Python debugger**

```python
# Add this to any function in log_collector_daemon.py
import pdb; pdb.set_trace()

# When daemon hits this line, you'll get an interactive prompt
# Commands:
#   n - next line
#   s - step into function
#   c - continue execution
#   p variable_name - print variable
#   l - show current code
#   q - quit
```

---

## Day 3: System Integration

### What You'll Learn Today

- How daemon integrates with backend
- WebSocket communication
- RabbitMQ message flow

### 1. Set Up Backend (60 minutes)

**Option A: Use provided Docker Compose**

```bash
# In backend repository
docker-compose up -d

# Services started:
# - Backend API (port 3000)
# - PostgreSQL (port 5432)
# - RabbitMQ (port 5672, management on 15672)
# - Frontend Dashboard (port 3001)

# Verify
curl http://localhost:3000/api/health
```

**Option B: Point to staging environment**

```bash
# Edit your daemon config
--api-url https://staging.resolvix.com/api/ticket
```

### 2. Test End-to-End Flow (45 minutes)

```bash
# Start daemon with backend connection
python3 log_collector_daemon.py \
    --log-file test.log \
    --api-url http://localhost:3000/api/ticket

# Generate an error
echo "$(date) ERROR: Database connection failed" >> test.log

# Check RabbitMQ management UI
# Open: http://localhost:15672 (guest/guest)
# Look for queue: error_logs_queue
# You should see 1 message

# Check backend API
curl http://localhost:3000/api/logs | jq

# You should see your error log entry
```

### 3. Test WebSocket Streaming (30 minutes)

**Install wscat (WebSocket client):**

```bash
npm install -g wscat
```

**Test Livelogs:**

```bash
# Start livelogs service
curl -X POST http://localhost:8754/api/control \
  -H "Content-Type: application/json" \
  -d '{"command": "start_livelogs"}'

# Connect with wscat
wscat -c ws://localhost:8755/livelogs

# In another terminal, generate logs
echo "$(date) INFO: WebSocket test" >> test.log

# You should see the log in wscat output
```

**Test Telemetry:**

```bash
# Start telemetry service
curl -X POST http://localhost:8754/api/control \
  -H "Content-Type: application/json" \
  -d '{"command": "start_telemetry"}'

# Connect with wscat
wscat -c ws://localhost:8756

# You'll receive system metrics every 3 seconds
```

### 4. Test Alert Flow (30 minutes)

```bash
# Create artificial high CPU usage
stress --cpu 8 --timeout 60s

# Watch daemon logs for alert
tail -f /var/log/resolvix.log | grep AlertManager

# After 5 minutes of 90%+ CPU, you should see:
# [AlertManager] ✓ Ticket created for cpu_critical: CPU usage at 92.5%
```

---

## Day 4: Advanced Features

### What You'll Learn Today

- Suppression rules system
- Process monitoring
- Configuration hot-reload

### 1. Create Suppression Rules (45 minutes)

**Connect to PostgreSQL:**

```bash
psql -h localhost -U resolvix_user -d resolvix
```

**Create a suppression rule:**

```sql
-- Suppress "connection timeout" errors from test server
INSERT INTO suppression_rules (
    name,
    match_text,
    node_ip,
    duration_type,
    enabled
) VALUES (
    'Ignore connection timeouts',
    'connection timeout',
    NULL,  -- applies to all servers
    'forever',
    true
);

-- View all rules
SELECT id, name, match_text, enabled, match_count
FROM suppression_rules;
```

**Test suppression:**

```bash
# Generate error that matches rule
echo "$(date) ERROR: connection timeout to database" >> test.log

# Check daemon logs - should see [SUPPRESSED]
tail -f /var/log/resolvix.log | grep SUPPRESSED
```

**View statistics:**

```bash
# After generating a few suppressed errors
curl http://localhost:8754/api/status | jq '.suppression_rules.statistics'
```

### 2. Use Process Monitoring API (45 minutes)

**Get top processes:**

```bash
# Top 10 by CPU
curl "http://localhost:8754/api/processes?limit=10&sortBy=cpu" | jq

# Top 10 by memory
curl "http://localhost:8754/api/processes?limit=10&sortBy=memory" | jq
```

**Get process details:**

```bash
# Find your Python process
ps aux | grep python3

# Get details (replace 12345 with actual PID)
curl http://localhost:8754/api/processes/12345 | jq
```

**Kill a process:**

```bash
# Start a sleep process
sleep 300 &
PID=$!

# Kill it via API
curl -X POST http://localhost:8754/api/processes/$PID/kill \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

**View process history:**

```bash
curl "http://localhost:8754/api/processes/$PID/history?hours=24" | jq
```

### 3. Test Configuration Hot-Reload (30 minutes)

**Change log level without restart:**

```bash
# Get current config
curl http://localhost:8754/config/get | jq

# Change log level to DEBUG
curl -X POST http://localhost:8754/config/update \
  -H "Content-Type: application/json" \
  -d '{"logging": {"level": "debug"}}'

# Verify change
tail -f /var/log/resolvix.log
# You should now see DEBUG level logs
```

**Change alert threshold:**

```bash
curl -X POST http://localhost:8754/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "alerts.thresholds.cpu_critical.threshold": 85
    }
  }'

# Verify
curl http://localhost:8754/api/config | jq '.config.alerts.thresholds.cpu_critical'
```

---

## Day 5: Production Scenarios

### What You'll Learn Today

- Deployment procedures
- Troubleshooting real issues
- Best practices

### 1. Deploy to Test Server (60 minutes)

**Using installation script:**

```bash
# SSH to test server
ssh test-server

# Download installer
curl -O https://github.com/yourorg/resolvix-daemon/install.sh

# Run installer
sudo bash install.sh \
  /var/log/syslog \
  https://staging.resolvix.com/api/ticket \
  https://staging.resolvix.com/api/system_info

# Verify service is running
sudo systemctl status resolvix

# Check logs
sudo journalctl -u resolvix -f
```

### 2. Troubleshoot Common Production Issues (60 minutes)

**Scenario 1: Daemon using too much CPU**

```bash
# Check current CPU usage
top -p $(pgrep -f log_collector_daemon)

# Check how many files being monitored
curl http://localhost:8754/api/status | jq '.monitored_files.count'

# Check log volume
sudo wc -l /var/log/syslog  # Lines in log file

# Solution: Reduce monitored files or increase interval
curl -X POST http://localhost:8754/api/config \
  -d '{"settings": {"monitoring.interval": 1}}'
```

**Scenario 2: Telemetry queue growing indefinitely**

```bash
# Check queue size
sqlite3 /var/lib/resolvix/telemetry_queue.db \
  "SELECT COUNT(*) FROM telemetry_queue;"

# Check for POST errors
sudo grep "TelemetryPoster" /var/log/resolvix.log

# Verify backend connectivity
curl https://backend.resolvix.com/api/health

# Solution: Fix backend URL or clear old queue
sudo systemctl stop resolvix
rm /var/lib/resolvix/telemetry_queue.db
sudo systemctl start resolvix
```

**Scenario 3: Suppression rules not working**

```bash
# Check suppression is enabled
curl http://localhost:8754/api/status | jq '.suppression_rules.enabled'

# If false, check database connection
sudo grep "SuppressionChecker" /var/log/resolvix.log

# Test database connectivity
psql -h db-host -U resolvix_user -d resolvix -c "SELECT 1;"

# Solution: Update database credentials
vim /etc/resolvix/secrets.json
sudo systemctl restart resolvix
```

### 3. Performance Tuning Exercise (45 minutes)

**Scenario:** 100 servers all sending telemetry simultaneously

**Problem:** Backend gets overwhelmed at :00 seconds of each minute

**Solution:** Stagger telemetry collection

```python
# Edit telemetry_ws.py - add random offset
import random

# In __init__():
self.interval = interval
self.offset = random.randint(0, 10)  # Random 0-10 second offset

# In broadcast_telemetry():
await asyncio.sleep(self.offset)  # Initial delay
while self.running:
    # ... collect metrics ...
    await asyncio.sleep(self.interval)
```

**Result:** Telemetry spread across 10-second window instead of all at once

---

## Week 2: Build a Feature

### Your First Feature Assignment

**Goal:** Add support for monitoring journald logs (in addition to file-based logs)

**Requirements:**

1. Add new parameter `--journald-unit systemd-unit-name`
2. Read logs from journalctl instead of file
3. Parse journald JSON format
4. Apply same error detection logic
5. Write tests

**Steps:**

1. **Research** (Day 6)

   - Read about journald and journalctl
   - Understand JSON format
   - Look at existing file monitoring code

2. **Design** (Day 7)

   - Create design document
   - Get feedback from senior engineer
   - Plan testing strategy

3. **Implementation** (Days 8-9)

   - Add journald monitoring class
   - Integrate with main daemon
   - Add configuration support
   - Write unit tests

4. **Testing** (Day 10)
   - Test on local machine
   - Deploy to test server
   - Performance testing
   - Fix bugs

**Deliverables:**

- Pull request with code
- Unit tests (>80% coverage)
- Documentation update
- Demo to team

---

## Resources

### Documentation

- **Full Technical Docs:** [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)
- **Executive Summary:** [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md)
- **API Reference:** PROJECT_DOCUMENTATION.md, section "API Reference"

### Tools You'll Use Daily

- **Python REPL:** Quick testing of functions
- **pytest:** Running unit tests
- **curl/httpie:** Testing API endpoints
- **wscat:** Testing WebSocket connections
- **psql:** Querying PostgreSQL
- **sqlite3:** Inspecting telemetry queue
- **journalctl:** Viewing daemon logs

### Useful Commands Reference

```bash
# Daemon management
sudo systemctl start resolvix
sudo systemctl stop resolvix
sudo systemctl restart resolvix
sudo systemctl status resolvix

# View logs
sudo journalctl -u resolvix -f              # Follow systemd logs
tail -f /var/log/resolvix.log               # Follow daemon logs

# Test API
curl http://localhost:8754/api/health | jq
curl http://localhost:8754/api/status | jq

# Database
psql -h localhost -U resolvix_user -d resolvix
sqlite3 /var/lib/resolvix/telemetry_queue.db

# Debugging
python3 -m pdb log_collector_daemon.py      # Run with debugger
pylint *.py                                  # Check code quality
black *.py                                   # Format code

# Testing
pytest tests/ -v                             # Run all tests
pytest tests/test_file.py::test_name -v     # Run specific test
pytest --cov=. tests/                        # With coverage
```

---

## Team Practices

### Code Review Process

1. Create feature branch from `main`
2. Make changes and commit frequently
3. Write/update tests
4. Run linter: `pylint *.py`
5. Format code: `black *.py`
6. Push and create pull request
7. Tag 2 reviewers
8. Address feedback
9. Merge when approved

### Daily Standup Questions

- What did you work on yesterday?
- What will you work on today?
- Any blockers?

### Weekly Demo

- Friday 2pm
- 15 minutes
- Show progress on your feature
- Get feedback

---

## Your Learning Checklist

### By End of Week 1

- [ ] Set up development environment
- [ ] Run daemon locally
- [ ] Understand main components (daemon, backend, WebSocket)
- [ ] Make a small code change
- [ ] Write a unit test
- [ ] Test integration with backend
- [ ] Create suppression rule
- [ ] Debug a common issue

### By End of Week 2

- [ ] Deploy to test server
- [ ] Troubleshoot production issue
- [ ] Complete first feature
- [ ] Write documentation
- [ ] Present to team

### By End of Month 1

- [ ] Own a component (e.g., process monitor)
- [ ] Participate in on-call rotation
- [ ] Mentor newer team member
- [ ] Contribute to architecture decisions

---

## Getting Help

### When You're Stuck (Use This Order)

1. **Check documentation** (this file + PROJECT_DOCUMENTATION.md)
2. **Search codebase** (`grep -r "function_name" *.py`)
3. **Read tests** (`tests/` directory)
4. **Ask in Slack** (#resolvix-dev channel)
5. **Schedule pairing session** with senior engineer

### Key People

- **Tech Lead:** [Name] - Architecture decisions, complex bugs
- **Backend Team:** [Names] - API integration questions
- **Operations Team:** [Names] - Production deployment, monitoring
- **DevOps:** [Name] - Infrastructure, CI/CD

---

## Next Steps

**Today:**

1. ✅ Complete Day 1 exercises
2. ✅ Join #resolvix-dev Slack channel
3. ✅ Schedule 1:1 with tech lead
4. ✅ Read full documentation (skim, don't memorize)

**This Week:**

1. Complete Days 2-5 exercises
2. Make your first code contribution
3. Attend team demo on Friday
4. Review open issues in GitHub

**This Month:**

1. Complete first feature
2. Shadow on-call engineer
3. Present in engineering all-hands
4. Propose improvement idea

---

**Welcome aboard! We're excited to have you on the team! 🚀**

---

**Document Version:** 1.0  
**Last Updated:** December 29, 2024  
**Maintained By:** Resolvix Engineering Team
