# Quick Test Guide - Add Monitored Files Endpoint

## Endpoint
```
POST http://{daemon_ip}:8754/api/config/monitored_files/add
```

---

## Basic Test (Copy & Paste Ready)

### Linux/Mac:
```bash
# Test 1: Add a single file (update path to valid file on your system)
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/syslog",
        "label": "system_log",
        "priority": "high",
        "enabled": true
      }
    ]
  }'

# Test 2: Add multiple files
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/auth.log",
        "label": "auth",
        "priority": "critical"
      },
      {
        "path": "/var/log/kern.log",
        "label": "kernel",
        "priority": "high"
      }
    ]
  }'

# Test 3: Verify files were added
curl http://172.31.7.124:8754/api/monitored-files

# Test 4: Test with non-existent file (should fail)
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/fake.log",
        "label": "fake"
      }
    ]
  }'
```

### Windows PowerShell:
```powershell
# Test 1: Add a single file
Invoke-RestMethod -Uri "http://172.31.7.124:8754/api/config/monitored_files/add" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "files": [
      {
        "path": "/var/log/syslog",
        "label": "system_log",
        "priority": "high",
        "enabled": true
      }
    ]
  }'

# Test 2: Verify files
Invoke-RestMethod -Uri "http://172.31.7.124:8754/api/monitored-files" -Method GET
```

---

## Quick Validation Checklist

Before testing, ensure:
- ✅ Daemon is running on port 8754
- ✅ Test file paths exist and are readable
- ✅ Daemon has permissions to read the files
- ✅ No duplicate labels in request

---

## Expected Responses

### ✅ Success (200 OK)
```json
{
  "status": "success",
  "message": "Added 1 log file",
  "added_files": ["/var/log/syslog"],
  "monitoring": true
}
```

### ⚠️ Partial Success (207 Multi-Status)
```json
{
  "status": "partial",
  "message": "Added 1 of 2 files",
  "added_files": ["/var/log/syslog"],
  "failed_files": [
    {
      "path": "/var/log/fake.log",
      "error": "File not found"
    }
  ]
}
```

### ❌ Error (400 Bad Request)
```json
{
  "status": "error",
  "message": "Failed to add any files",
  "failed_files": [
    {
      "path": "/var/log/fake.log",
      "error": "File not found"
    }
  ]
}
```

---

## Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `Path must be absolute` | Relative path used | Use `/var/log/app.log` not `var/log/app.log` |
| `File not found` | File doesn't exist | Verify path with `ls -la /path/to/file` |
| `Permission denied` | No read access | Run `sudo chmod 644 /path/to/file` |
| `Label already exists` | Duplicate label | Use different label or omit to auto-generate |
| `File already being monitored` | Path already monitored | Remove file first or use different path |

---

## Quick Debug

```bash
# Check daemon status
curl http://172.31.7.124:8754/health

# Check daemon logs
sudo tail -f /var/log/resolvix.log | grep AddMonitoredFiles

# Check if file is readable
sudo -u resolvix cat /var/log/app.log

# List all monitored files
curl http://172.31.7.124:8754/api/monitored-files | jq
```

---

## Integration Test Flow

1. **Start Daemon**
   ```bash
   sudo systemctl start resolvix-daemon
   ```

2. **Add Test File**
   ```bash
   curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
     -H "Content-Type: application/json" \
     -d '{"files":[{"path":"/var/log/test.log","label":"test"}]}'
   ```

3. **Verify Added**
   ```bash
   curl http://172.31.7.124:8754/api/monitored-files | jq '.files[] | select(.label=="test")'
   ```

4. **Generate Test Error**
   ```bash
   echo "ERROR: Test error message" | sudo tee -a /var/log/test.log
   ```

5. **Check Log Was Detected**
   ```bash
   sudo tail -f /var/log/resolvix.log | grep "Issue detected"
   ```

6. **Cleanup**
   ```bash
   # Get file ID
   FILE_ID=$(curl -s http://172.31.7.124:8754/api/monitored-files | jq -r '.files[] | select(.label=="test") | .id')
   
   # Delete file
   curl -X DELETE "http://172.31.7.124:8754/api/monitored-files/$FILE_ID"
   ```

---

## Python Test Script

```python
import requests
import json

DAEMON_URL = "http://172.31.7.124:8754"

def test_add_files():
    """Test adding files"""
    payload = {
        "files": [
            {
                "path": "/var/log/syslog",
                "label": "test_syslog",
                "priority": "high",
                "enabled": True
            }
        ]
    }
    
    response = requests.post(
        f"{DAEMON_URL}/api/config/monitored_files/add",
        json=payload,
        timeout=10
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    assert response.status_code in [200, 207, 400]
    assert "status" in response.json()

def test_get_files():
    """Verify files were added"""
    response = requests.get(f"{DAEMON_URL}/api/monitored-files")
    data = response.json()
    
    print(f"Monitored files: {data['count']}")
    for file in data['files']:
        print(f"  - {file['label']}: {file['path']}")

if __name__ == "__main__":
    print("Test 1: Add files")
    test_add_files()
    
    print("\nTest 2: List files")
    test_get_files()
```

---

## Performance Test

Test adding 10 files at once:

```bash
cat > test_multiple.json << 'EOF'
{
  "files": [
    {"path": "/var/log/syslog", "label": "syslog", "priority": "high"},
    {"path": "/var/log/auth.log", "label": "auth", "priority": "critical"},
    {"path": "/var/log/kern.log", "label": "kernel", "priority": "high"},
    {"path": "/var/log/dmesg", "label": "dmesg", "priority": "medium"},
    {"path": "/var/log/boot.log", "label": "boot", "priority": "low"}
  ]
}
EOF

time curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d @test_multiple.json
```

Expected: < 2 seconds for 5 files

---

## Validation Test Matrix

| Test Case | Path | Label | Expected Result |
|-----------|------|-------|----------------|
| Valid file | `/var/log/syslog` | `test1` | ✅ Success |
| No label | `/var/log/syslog` | - | ✅ Success (auto-generated) |
| Duplicate label | `/var/log/kern.log` | `test1` | ❌ Label exists |
| Non-existent | `/fake/log.log` | `fake` | ❌ File not found |
| Relative path | `var/log/syslog` | `rel` | ❌ Path not absolute |
| Directory | `/var/log/` | `dir` | ❌ Not a file |
| No permission | `/root/.ssh/id_rsa` | `key` | ❌ Permission denied |
| Already monitored | `/var/log/syslog` | `test2` | ❌ Already monitored |

---

## Ready-to-Use Test Files

Create test log files:

```bash
# Create test directory
sudo mkdir -p /var/log/test

# Create test files
for i in {1..5}; do
  sudo touch "/var/log/test/app$i.log"
  sudo chmod 644 "/var/log/test/app$i.log"
done

# Test adding them
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {"path": "/var/log/test/app1.log", "label": "app1"},
      {"path": "/var/log/test/app2.log", "label": "app2"},
      {"path": "/var/log/test/app3.log", "label": "app3"}
    ]
  }'

# Generate test errors
for i in {1..3}; do
  echo "ERROR: Test error from app$i" | sudo tee -a "/var/log/test/app$i.log"
done

# Cleanup
curl -s http://172.31.7.124:8754/api/monitored-files | \
  jq -r '.files[] | select(.label | startswith("app")) | .id' | \
  xargs -I {} curl -X DELETE "http://172.31.7.124:8754/api/monitored-files/{}"
```

---

For complete documentation, see [ADD_MONITORED_FILES_ENDPOINT.md](./ADD_MONITORED_FILES_ENDPOINT.md)
