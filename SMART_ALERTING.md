# Smart Alerting System - Complete Documentation

## Overview

The Resolvix daemon now includes **intelligent threshold-based alerting** that automatically monitors system metrics and creates tickets when resources exceed safe operational limits.

---

## 🎯 Features

### **Automated Monitoring**

- Continuous monitoring of CPU, memory, disk, network, and processes
- No manual intervention required once configured
- Runs seamlessly with existing telemetry collection

### **Smart Thresholds**

- **Duration-based alerts**: Prevents false positives from temporary spikes
- **Cooldown periods**: Prevents alert spam for persistent issues
- **Severity classification**: Critical, high, medium priority levels

### **Automatic Ticket Creation**

- Creates tickets in backend via API when thresholds breached
- Rich context: Includes metrics, timestamps, recommended actions
- Seamless integration with existing ticketing system

---

## 📊 Alert Types

### **1. CPU Alerts**

| Alert Level | Threshold | Duration   | Cooldown   | Priority |
| ----------- | --------- | ---------- | ---------- | -------- |
| Critical    | 90%       | 5 minutes  | 30 minutes | critical |
| High        | 75%       | 10 minutes | 1 hour     | high     |

**Triggers when**: CPU usage exceeds threshold continuously for specified duration

**Example**:

```
🔴 CRITICAL: CPU usage at 92.3% for 5.0 minutes on web-server-01
```

---

### **2. Memory Alerts**

| Alert Level | Threshold | Duration   | Cooldown   | Priority |
| ----------- | --------- | ---------- | ---------- | -------- |
| Critical    | 95%       | 5 minutes  | 30 minutes | critical |
| High        | 85%       | 10 minutes | 1 hour     | high     |

**Triggers when**: Memory usage exceeds threshold continuously for specified duration

**Example**:

```
🔴 CRITICAL: Memory usage at 96.2% for 5.0 minutes on db-server-02
```

---

### **3. Disk Alerts**

| Alert Level | Threshold | Duration  | Cooldown | Priority |
| ----------- | --------- | --------- | -------- | -------- |
| Critical    | 90%       | Immediate | 2 hours  | critical |
| High        | 80%       | Immediate | 4 hours  | high     |

**Triggers when**: Disk usage exceeds threshold (no duration requirement)

**Example**:

```
🔴 CRITICAL: Disk usage at 92% on app-server-03. Immediate action required!
```

---

### **4. Network Spike Alerts**

| Alert Type    | Threshold | Duration | Cooldown   | Priority |
| ------------- | --------- | -------- | ---------- | -------- |
| Network Spike | 5x normal | 1 minute | 30 minutes | medium   |

**Triggers when**: Network traffic exceeds 5x the baseline average

**Example**:

```
⚠️ Network traffic spike detected: 6.2x normal on api-server-04
```

---

### **5. Process Count Alerts**

| Alert Type         | Threshold     | Duration  | Cooldown | Priority |
| ------------------ | ------------- | --------- | -------- | -------- |
| High Process Count | 500 processes | 5 minutes | 1 hour   | medium   |

**Triggers when**: Too many processes running (potential fork bomb or leak)

**Example**:

```
⚠️ High process count: 550 processes running on worker-node-05
```

---

## 🛠️ Configuration

### **Default Thresholds** (`alert_config.py`)

```python
ALERT_THRESHOLDS = {
    'cpu_critical': {
        'threshold': 90,      # 90% CPU usage
        'duration': 300,      # Must last 5 minutes
        'priority': 'critical',
        'cooldown': 1800,     # 30 min before re-alerting
    },
    # ... more thresholds
}
```

### **Customization Guide**

#### **For Development/Staging Servers** (less strict):

```python
'cpu_critical': {
    'threshold': 95,      # Higher threshold
    'duration': 600,      # Longer duration (10 min)
    'cooldown': 300,      # Shorter cooldown (5 min)
}
```

#### **For Production Servers** (more strict):

```python
'cpu_critical': {
    'threshold': 80,      # Lower threshold
    'duration': 180,      # Shorter duration (3 min)
    'cooldown': 3600,     # Longer cooldown (1 hour)
}
```

#### **For High-Traffic Servers**:

```python
'network_spike': {
    'threshold_multiplier': 10,  # 10x instead of 5x
    'duration': 120,             # 2 minutes
}
```

---

## 🚀 Installation

### **Files Created**

1. **`alert_config.py`** - Threshold configuration
2. **`alert_manager.py`** - Alert logic and ticket creation
3. **`test_alerts.py`** - Testing suite

### **Integration Status**

✅ Automatically integrated into:

- `log_collector_daemon.py` - Main daemon
- `telemetry_ws.py` - Telemetry collector

✅ No manual integration required - works out of the box!

---

## 🧪 Testing

### **Run Test Suite**

```bash
cd /path/to/log_collector_daemon
source venv/bin/activate
python3 test_alerts.py
```

### **Test Menu**

```
1. CPU Alert (5 min duration)
2. Memory Alert (5 min duration)
3. Disk Alert (immediate)
4. Process Count Alert (5 min duration)
5. Cooldown Test
6. Run all tests
0. Exit
```

### **Manual Testing**

**Test CPU Alert:**

```python
from alert_manager import AlertManager

alert_mgr = AlertManager(
    backend_url="http://your-backend:3000",
    hostname="test-server",
    ip_address="192.168.1.100"
)

# Simulate high CPU for 6 minutes
for i in range(360):
    alert_mgr.check_cpu_alert(95.5)
    time.sleep(1)
```

**Expected Output:**

```
[ALERT] cpu_critical threshold breached: 95.5%
... (waits 5 minutes) ...
[ALERT] ✓ Ticket created for cpu_critical: 🔴 CRITICAL: CPU usage at 95.5% for 5.0 minutes on test-server
```

---

## 📡 Backend API Integration

### **Required Endpoint**

The daemon expects this endpoint on your backend:

**POST** `/api/alerts/create`

### **Request Payload**

```json
{
  "title": "🔴 CRITICAL: CPU usage at 92.3% for 5.0 minutes on web-server-01",
  "description": "**Alert Type:** Cpu Critical\n**Timestamp:** 2025-12-08 14:30:45\n...",
  "priority": "critical",
  "status": "open",
  "application": "System Monitor",
  "system_ip": "192.168.1.100",
  "alert_type": "cpu_critical",
  "metric_value": 92.3
}
```

### **Expected Response**

```json
{
  "success": true,
  "ticket_id": "TICKET-12345"
}
```

**Status Codes:**

- `200` or `201` - Success
- `4xx` or `5xx` - Error (logged but doesn't crash daemon)

---

## 🔧 How It Works

### **1. Continuous Monitoring**

```
Telemetry Collector (every 3-60 seconds)
    ↓
Collect CPU, Memory, Disk, Network, Process metrics
    ↓
Pass metrics to AlertManager
    ↓
Check against thresholds
```

### **2. Threshold Breach Detection**

```
Metric exceeds threshold?
    ↓ YES
Start timer (duration requirement)
    ↓
Still exceeding after duration?
    ↓ YES
Check cooldown period
    ↓ NOT in cooldown
Create ticket via API
    ↓
Set cooldown timer
```

### **3. Return to Normal**

```
Metric drops below threshold?
    ↓ YES
Reset alert timer
    ↓
Log: "Alert returned to normal"
```

---

## 📋 Alert Ticket Details

### **Ticket Content**

Each alert ticket includes:

1. **Title**: Emoji + severity + metric + hostname
2. **Description**:
   - Alert type and timestamp
   - Host information (hostname + IP)
   - Metric value and breach duration
   - Threshold configuration
   - Additional metrics context
   - Recommended remediation actions

### **Example Ticket**

```markdown
**Alert Type:** Cpu Critical
**Timestamp:** 2025-12-08 14:30:45
**Host:** web-server-01 (192.168.1.100)
**Metric Value:** 92.3%
**Duration:** 5.0 minutes

**Threshold Configuration:**

- Threshold: 90%
- Required Duration: 300s
- Priority: critical

**Additional Metrics:**

- cpu_percent: 92.3

**Recommended Actions:**

1. Check top processes: `top` or `htop`
2. Kill unnecessary processes
3. Consider scaling horizontally
```

---

## 🛡️ Alert Behavior

### **Duration Requirements Prevent False Positives**

❌ **Without duration**: Temporary spike → Immediate alert → Waste of time
✅ **With duration**: Sustained issue → Alert after 5 min → Actionable

### **Cooldown Prevents Alert Spam**

❌ **Without cooldown**: Issue persists → Alert every collection cycle → 20+ tickets
✅ **With cooldown**: Issue persists → One alert → Next alert after 30 min

### **Severity Classification**

- **Critical**: Immediate action required (>90% resource usage)
- **High**: Action needed soon (>75-85% resource usage)
- **Medium**: Monitor and plan (spikes, process count)

---

## 🔍 Monitoring & Logs

### **Daemon Logs**

```bash
tail -f /var/log/resolvix.log
```

**What to look for:**

```
[AlertManager] Smart alerting enabled
[ALERT] cpu_critical threshold breached: 92.3%
[ALERT] ✓ Ticket created for cpu_critical: 🔴 CRITICAL...
[ALERT] cpu_critical returned to normal
```

### **Error Messages**

```
[ALERT] ✗ Failed to create ticket: 500 - Internal Server Error
[ALERT] ✗ Timeout sending alert for cpu_critical
[ALERT] ✗ Connection error sending alert: Connection refused
```

---

## 🎯 Use Cases

### **1. Proactive Incident Prevention**

- Catch resource exhaustion before service crashes
- Alert before disk fills up completely
- Detect memory leaks early

### **2. Performance Monitoring**

- Track sustained high CPU usage
- Monitor memory pressure over time
- Identify capacity planning needs

### **3. Anomaly Detection**

- Network traffic spikes (DDoS, data exfiltration)
- Process count explosions (fork bombs, leaks)
- Unusual resource consumption patterns

### **4. Compliance & SLA**

- Automated alerting for resource thresholds
- Documented response times
- Audit trail of system issues

---

## 🚨 Troubleshooting

### **Alerts Not Triggering**

**Check:**

1. AlertManager initialized? Look for log: `[AlertManager] Smart alerting enabled`
2. Backend URL configured? Check daemon startup logs
3. Metrics being collected? Check telemetry is running
4. Thresholds too high? Review `alert_config.py`

**Debug:**

```bash
# Check if alert manager module is loaded
python3 -c "from alert_manager import AlertManager; print('OK')"

# Check current metrics
curl http://localhost:8754/status
```

### **Too Many Alerts (False Positives)**

**Solution**: Adjust thresholds in `alert_config.py`

```python
# Increase threshold
'cpu_critical': {'threshold': 95}  # was 90

# Increase duration
'cpu_critical': {'duration': 600}  # was 300 (now 10 min)

# Increase cooldown
'cpu_critical': {'cooldown': 3600}  # was 1800 (now 1 hour)
```

### **Backend Not Receiving Alerts**

**Check:**

1. Backend API endpoint exists: `/api/alerts/create`
2. Backend is reachable: `curl http://backend:3000/api/alerts/create`
3. Check daemon logs for HTTP errors
4. Verify backend URL in daemon startup

**Test manually:**

```bash
curl -X POST http://backend:3000/api/alerts/create \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","priority":"high","status":"open"}'
```

---

## 📊 Performance Impact

### **Resource Usage**

- **CPU**: Negligible (<0.1% additional)
- **Memory**: ~5-10 MB for alert tracking
- **Network**: Minimal (only when alerts triggered)

### **Optimization**

Alert checking is integrated into existing telemetry collection:

- No additional polling loops
- No separate threads
- Reuses collected metrics

---

## 🔄 Future Enhancements

### **Planned Features**

1. **Custom Alert Types**: Define app-specific thresholds
2. **Alert Aggregation**: Combine related alerts
3. **Machine Learning**: Adaptive baseline detection
4. **Notification Channels**: Email, Slack, PagerDuty integration
5. **Alert Acknowledgment**: Mark alerts as "investigating"
6. **Historical Analysis**: Trend-based alerting

### **Requested Features**

Submit feature requests to the development team!

---

## 📖 Quick Reference

### **Enable/Disable Alerts**

**Enabled by default** when:

- `alert_manager.py` and `alert_config.py` exist
- Backend URL is configured

**To disable**: Remove or rename `alert_manager.py`

### **Common Configurations**

**Production (Conservative)**:

```python
'cpu_critical': {'threshold': 85, 'duration': 300, 'cooldown': 3600}
```

**Development (Aggressive)**:

```python
'cpu_critical': {'threshold': 95, 'duration': 600, 'cooldown': 300}
```

**High-Traffic (Lenient)**:

```python
'cpu_critical': {'threshold': 90, 'duration': 900, 'cooldown': 1800}
```

---

## 📞 Support

**Issues?**

- Check logs: `/var/log/resolvix.log`
- Test alerts: `python3 test_alerts.py`
- Review configuration: `alert_config.py`

**Questions?**
Contact the daemon development team with:

- Log excerpts
- Configuration settings
- Expected vs actual behavior

---

**Version**: 1.0.0  
**Last Updated**: December 8, 2025  
**Author**: Resolvix Development Team
