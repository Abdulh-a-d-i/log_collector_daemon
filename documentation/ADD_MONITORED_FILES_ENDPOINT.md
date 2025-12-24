# Add & Remove Monitored Files Endpoints - Implementation Documentation

## Overview

This document describes the endpoints for adding and removing log files to/from the daemon's monitoring system dynamically, without requiring a daemon restart.

---

## 1. ADD Monitored Files

### Endpoint Details

**URL:** `POST http://{daemon_ip}:8754/api/config/monitored_files/add`

**Port:** 8754 (daemon's existing control API port)

**Method:** POST

**Content-Type:** application/json

---

## Request Format

```json
{
  "files": [
    {
      "path": "/var/log/apache2/error.log",
      "label": "apache_errors",
      "priority": "high",
      "enabled": true
    },
    {
      "path": "/var/log/nginx/access.log",
      "label": "nginx_access",
      "priority": "medium",
      "enabled": true
    }
  ]
}
```

### Request Parameters

| Field              | Type    | Required | Description                                                               |
| ------------------ | ------- | -------- | ------------------------------------------------------------------------- |
| `files`            | Array   | Yes      | Array of file objects to add                                              |
| `files[].path`     | String  | Yes      | Absolute path to the log file                                             |
| `files[].label`    | String  | No       | Unique identifier for this log source. Auto-generated if not provided     |
| `files[].priority` | String  | No       | Severity level: `critical`, `high`, `medium`, or `low`. Default: `medium` |
| `files[].enabled`  | Boolean | No       | Whether to monitor this file. Default: `true`                             |

---

## Response Formats

### Success Response (All files added)

**HTTP Status:** 200 OK

```json
{
  "status": "success",
  "message": "Added 2 log files",
  "added_files": ["/var/log/apache2/error.log", "/var/log/nginx/access.log"],
  "monitoring": true
}
```

### Partial Success Response (Some files failed)

**HTTP Status:** 207 Multi-Status

```json
{
  "status": "partial",
  "message": "Added 1 of 2 files",
  "added_files": ["/var/log/nginx/access.log"],
  "failed_files": [
    {
      "path": "/var/log/apache2/error.log",
      "error": "Permission denied"
    }
  ]
}
```

### Error Response (All files failed)

**HTTP Status:** 400 Bad Request

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

## Validation Rules

The endpoint performs comprehensive validation on each file:

### 1. Path is Required

- **Check:** Path field must be present and non-empty
- **Error:** `Path is required`

### 2. Path Must Be Absolute

- **Check:** Path must start with `/` (Unix) or drive letter (Windows)
- **Error:** `Path must be absolute`
- **Example:** ❌ `var/log/app.log` → ✅ `/var/log/app.log`

### 3. File Must Exist

- **Check:** File exists on filesystem
- **Error:** `File not found`

### 4. Must Be Regular File

- **Check:** Not a directory or special file
- **Error:** `Not a regular file`

### 5. File Must Be Readable

- **Check:** Daemon has read permissions
- **Error:** `Permission denied`

### 6. Label Must Be Unique

- **Check:** Label not already used by another monitored file
- **Error:** `Label already exists: {label}`

### 7. File Not Already Monitored

- **Check:** Path not already in monitoring list
- **Error:** `File already being monitored`

### 8. Priority Must Be Valid

- **Check:** Priority is one of: `critical`, `high`, `medium`, `low`
- **Behavior:** Defaults to `medium` if invalid

---

## Error Status Codes

| HTTP Status               | Scenario                                         |
| ------------------------- | ------------------------------------------------ |
| 200 OK                    | All files added successfully                     |
| 207 Multi-Status          | Some files added, some failed                    |
| 400 Bad Request           | No files provided or all files failed validation |
| 500 Internal Server Error | Unexpected server error                          |

---

## Implementation Features

### ✅ Automatic Label Generation

If no label is provided, the daemon generates one from the filename:

```
/var/log/apache2/error.log → "apache2_error"
/var/log/app.log → "app"
```

### ✅ Immediate Monitoring

Files are added to monitoring **without restarting the daemon**:

1. File metadata is added to daemon's internal list
2. New monitoring thread is spawned immediately
3. File is tailed from current position (only new lines monitored)

### ✅ Persistent Configuration

Changes are saved to disk (`/etc/resolvix/config.json`) so they survive daemon restarts.

### ✅ Thread-Safe

Multiple requests can be processed concurrently without conflicts.

### ✅ Logging

All configuration changes are logged with context:

```
[AddMonitoredFiles] Started monitoring: /var/log/app.log [app]
[AddMonitoredFiles] Configuration saved to disk
```

---

## Testing Examples

### Test 1: Add Single Valid File

```bash
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
```

**Expected Response:**

```json
{
  "status": "success",
  "message": "Added 1 log file",
  "added_files": ["/var/log/syslog"],
  "monitoring": true
}
```

---

### Test 2: Add Multiple Files

```bash
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
        "path": "/var/log/apache2/error.log",
        "label": "apache_errors",
        "priority": "high"
      }
    ]
  }'
```

**Expected Response:**

```json
{
  "status": "success",
  "message": "Added 2 log files",
  "added_files": ["/var/log/auth.log", "/var/log/apache2/error.log"],
  "monitoring": true
}
```

---

### Test 3: Add Non-Existent File (Should Fail)

```bash
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/fake.log",
        "label": "fake_log",
        "priority": "low"
      }
    ]
  }'
```

**Expected Response:**

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

### Test 4: Add File with Relative Path (Should Fail)

```bash
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "var/log/app.log",
        "label": "app"
      }
    ]
  }'
```

**Expected Response:**

```json
{
  "status": "error",
  "message": "Failed to add any files",
  "failed_files": [
    {
      "path": "var/log/app.log",
      "error": "Path must be absolute"
    }
  ]
}
```

---

### Test 5: Duplicate Label (Should Fail)

Assuming "system_log" already exists:

```bash
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/kern.log",
        "label": "system_log"
      }
    ]
  }'
```

**Expected Response:**

```json
{
  "status": "error",
  "message": "Failed to add any files",
  "failed_files": [
    {
      "path": "/var/log/kern.log",
      "error": "Label already exists: system_log"
    }
  ]
}
```

---

### Test 6: Mixed Success/Failure

```bash
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/syslog",
        "label": "syslog_main",
        "priority": "high"
      },
      {
        "path": "/var/log/nonexistent.log",
        "label": "fake"
      }
    ]
  }'
```

**Expected Response (207 Multi-Status):**

```json
{
  "status": "partial",
  "message": "Added 1 of 2 files",
  "added_files": ["/var/log/syslog"],
  "failed_files": [
    {
      "path": "/var/log/nonexistent.log",
      "error": "File not found"
    }
  ]
}
```

---

### Test 7: Verify File is Being Monitored

After adding a file, verify it appears in the status:

```bash
curl http://172.31.7.124:8754/api/monitored-files
```

**Expected Response:**

```json
{
  "success": true,
  "files": [
    {
      "id": "file_001",
      "path": "/var/log/syslog",
      "label": "system_log",
      "priority": "high",
      "enabled": true,
      "created_at": "2025-12-24T10:30:00.000Z",
      "last_modified": "2025-12-24T10:30:00.000Z",
      "auto_monitor": false
    }
  ],
  "count": 1
}
```

---

### Test 8: Add File Without Label (Auto-Generate)

```bash
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/var/log/apache2/access.log",
        "priority": "medium"
      }
    ]
  }'
```

**Expected Response:**

```json
{
  "status": "success",
  "message": "Added 1 log file",
  "added_files": ["/var/log/apache2/access.log"],
  "monitoring": true
}
```

The label will be auto-generated as `apache2_access`.

---

## 2. REMOVE Monitored Files

### Endpoint Details

**URL:** `DELETE http://{daemon_ip}:8754/api/config/monitored_files/remove`

**Port:** 8754 (daemon's existing control API port)

**Method:** DELETE

**Content-Type:** application/json

---

### Request Format

```json
{
  "labels": ["apache_errors", "nginx_access"]
}
```

#### Request Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `labels` | Array | Yes | Array of label strings to remove from monitoring |

---

### Response Formats

#### Success Response (All labels removed)

**HTTP Status:** 200 OK

```json
{
  "status": "success",
  "message": "Removed 2 log files",
  "removed_labels": ["apache_errors", "nginx_access"]
}
```

#### Partial Success Response (Some labels removed)

**HTTP Status:** 207 Multi-Status

```json
{
  "status": "partial",
  "message": "Removed 1 of 3 files",
  "removed_labels": ["apache_errors"],
  "not_found": ["nginx_access"],
  "cannot_remove": ["resolvix_daemon"]
}
```

#### Error Response (No labels removed)

**HTTP Status:** 400 Bad Request

```json
{
  "status": "error",
  "message": "Labels not found: apache_errors, nginx_access",
  "not_found": ["apache_errors", "nginx_access"]
}
```

---

### Error Scenarios

| Error Type | Response Field | Description |
|------------|---------------|-------------|
| Label not found | `not_found` | Label doesn't exist in monitored files |
| Cannot remove | `cannot_remove` | File is auto-monitored (e.g., daemon's own log) |
| No labels provided | - | Request body missing `labels` field or empty array |

---

### Implementation Details

#### What Happens When Removing Files?

1. **Validate Request** - Check `labels` array is provided and non-empty
2. **Find Files** - Locate files with matching labels in `daemon.log_files`
3. **Check Protection** - Skip auto-monitored files (e.g., `resolvix_daemon`)
4. **Remove from List** - Remove file configs from `daemon.log_files`
5. **Stop Monitoring** - Monitoring threads detect removal and exit naturally
6. **Save Config** - Update `/etc/resolvix/config.json` with new list
7. **Return Response** - Report success/partial/failure

#### Thread Cleanup

- Monitoring threads are daemon threads
- They periodically check if their file is still in `daemon.log_files`
- When removed, threads exit gracefully on next check
- No explicit thread termination needed

---

### Testing Examples

#### Test 1: Remove Single File

```bash
curl -X DELETE http://172.31.7.124:8754/api/config/monitored_files/remove \
  -H "Content-Type: application/json" \
  -d '{
    "labels": ["system_log"]
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Removed 1 log file",
  "removed_labels": ["system_log"]
}
```

---

#### Test 2: Remove Multiple Files

```bash
curl -X DELETE http://172.31.7.124:8754/api/config/monitored_files/remove \
  -H "Content-Type: application/json" \
  -d '{
    "labels": ["apache_errors", "nginx_access", "mysql_errors"]
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Removed 3 log files",
  "removed_labels": ["apache_errors", "nginx_access", "mysql_errors"]
}
```

---

#### Test 3: Remove Non-Existent Label

```bash
curl -X DELETE http://172.31.7.124:8754/api/config/monitored_files/remove \
  -H "Content-Type: application/json" \
  -d '{
    "labels": ["fake_log"]
  }'
```

**Expected Response (400 Bad Request):**
```json
{
  "status": "error",
  "message": "Labels not found: fake_log",
  "not_found": ["fake_log"],
  "cannot_remove": null
}
```

---

#### Test 4: Try to Remove Auto-Monitored File

```bash
curl -X DELETE http://172.31.7.124:8754/api/config/monitored_files/remove \
  -H "Content-Type: application/json" \
  -d '{
    "labels": ["resolvix_daemon"]
  }'
```

**Expected Response (400 Bad Request):**
```json
{
  "status": "error",
  "message": "Cannot remove auto-monitored files: resolvix_daemon",
  "not_found": null,
  "cannot_remove": ["resolvix_daemon"]
}
```

---

#### Test 5: Mixed Success/Failure

```bash
curl -X DELETE http://172.31.7.124:8754/api/config/monitored_files/remove \
  -H "Content-Type: application/json" \
  -d '{
    "labels": ["apache_errors", "fake_log", "resolvix_daemon"]
  }'
```

**Expected Response (207 Multi-Status):**
```json
{
  "status": "partial",
  "message": "Removed 1 of 3 files",
  "removed_labels": ["apache_errors"],
  "not_found": ["fake_log"],
  "cannot_remove": ["resolvix_daemon"]
}
```

---

#### Test 6: Verify Removal

After removing files, verify they're gone:

```bash
curl http://172.31.7.124:8754/api/monitored-files
```

**Expected:** Removed files should not appear in the list

---

### Complete Add/Remove Workflow

```bash
# 1. Add a test file
curl -X POST http://172.31.7.124:8754/api/config/monitored_files/add \
  -H "Content-Type: application/json" \
  -d '{
    "files": [{
      "path": "/var/log/test.log",
      "label": "test_log",
      "priority": "low"
    }]
  }'

# 2. Verify it was added
curl http://172.31.7.124:8754/api/monitored-files | jq '.files[] | select(.label=="test_log")'

# 3. Generate test error
echo "ERROR: Test message" | sudo tee -a /var/log/test.log

# 4. Check daemon detected it
sudo tail -f /var/log/resolvix.log | grep "Issue detected"

# 5. Remove the file
curl -X DELETE http://172.31.7.124:8754/api/config/monitored_files/remove \
  -H "Content-Type: application/json" \
  -d '{"labels": ["test_log"]}'

# 6. Verify removal
curl http://172.31.7.124:8754/api/monitored-files | jq '.files[] | select(.label=="test_log")'
# Should return nothing
```

---

## Integration with Backend

The backend at `api.resolvix.app` should handle both ADD and REMOVE operations:

### ADD Files Integration

1. **Authenticate User** - Verify JWT token
2. **Get Node IP** - Fetch node IP from database
3. **Forward Request** - POST to `http://{node_ip}:8754/api/config/monitored_files/add`
4. **Store in Database** - Save configuration after daemon confirms
5. **Return Response** - Forward daemon response to frontend

### REMOVE Files Integration

1. **Authenticate User** - Verify JWT token
2. **Get Node IP** - Fetch node IP from database
3. **Forward Request** - DELETE to `http://{node_ip}:8754/api/config/monitored_files/remove`
4. **Update Database** - Remove configurations from database
5. **Return Response** - Forward daemon response to frontend

### Backend Flow Diagrams

#### ADD Flow
```
Frontend
   ↓ (User adds files)
Backend API
   ↓ (GET node IP from DB)
Daemon API (172.31.7.124:8754)
   ↓ (Validate & add files)
   ↓ (Start monitoring threads)
   ↓ (Save config to disk)
Backend API
   ↓ (Store config in DB)
Frontend
   ↓ (Display success/error)
```

#### REMOVE Flow
```
Frontend
   ↓ (User removes files)
Backend API
   ↓ (GET node IP from DB)
Daemon API (172.31.7.124:8754)
   ↓ (Find & remove files)
   ↓ (Stop monitoring threads)
   ↓ (Save config to disk)
Backend API
   ↓ (Store config in DB)
Frontend
   ↓ (Display success/error)
```

---

## Monitoring Behavior

### What Happens After Adding Files?

1. **Immediate Effect:**

   - New monitoring thread starts immediately
   - File is opened and positioned at EOF (end of file)
   - Only **new** lines written after this point are monitored

2. **Log Detection:**

   - Lines are checked against error keyword patterns
   - Matches are sent to RabbitMQ queue
   - Suppression rules are applied (if configured)

3. **Persistence:**
   - Configuration is saved to `/etc/resolvix/config.json`
   - Survives daemon restarts
   - Can be edited manually if needed

---

## Error Handling Best Practices

### For Backend Developers:

1. **Always check `status` field** in response:

   - `success` = all files added
   - `partial` = some files added, some failed
   - `error` = all files failed

2. **Handle partial success gracefully:**

   - Show which files succeeded
   - Display specific error for each failed file
   - Allow user to retry failed files

3. **Validate before sending:**

   - Check if paths are absolute
   - Verify files exist (if backend has access)
   - Ensure labels are unique

4. **Timeout handling:**
   - Set reasonable timeout (10-30 seconds)
   - Daemon should respond quickly (<5 seconds)
   - If timeout, assume daemon is down

---

## Security Considerations

### ⚠️ Important Security Notes:

1. **Path Traversal:**

   - Endpoint accepts absolute paths only
   - No validation against path traversal attacks yet
   - Consider restricting to specific directories (e.g., `/var/log/*`)

2. **Permissions:**

   - Daemon runs as specific user (usually root)
   - Can read any file accessible to that user
   - Consider implementing file path whitelist

3. **Resource Limits:**

   - Each file spawns a new thread
   - Too many files can exhaust system resources
   - Consider limiting max monitored files (e.g., 50)

4. **Input Validation:**
   - Label field accepts any string
   - Could contain special characters or injection attempts
   - Consider sanitizing labels

### Recommended Improvements:

```python
# Add path whitelist validation
ALLOWED_LOG_DIRS = ['/var/log', '/opt/app/logs']

def is_path_allowed(path):
    return any(path.startswith(allowed) for allowed in ALLOWED_LOG_DIRS)

# Add file count limit
MAX_MONITORED_FILES = 50

if len(daemon.log_files) >= MAX_MONITORED_FILES:
    return error("Maximum monitored files limit reached")
```

---

## Troubleshooting

### Issue: "Permission denied" error

**Cause:** Daemon doesn't have read permissions on the file

**Solution:**

```bash
# Give daemon read access
sudo chmod 644 /var/log/app.log

# Or change ownership
sudo chown resolvix:resolvix /var/log/app.log
```

---

### Issue: File added but no logs appearing

**Possible Causes:**

1. File is not receiving new writes
2. Logs don't match error keywords
3. Suppression rule is blocking logs

**Debug Steps:**

```bash
# 1. Check if file is being written to
tail -f /var/log/app.log

# 2. Check daemon logs
tail -f /var/log/resolvix.log | grep AddMonitoredFiles

# 3. Test error keyword matching
echo "ERROR: Test error message" >> /var/log/app.log
```

---

### Issue: "File already being monitored"

**Cause:** File path already exists in monitored files list

**Solution:**

```bash
# Get list of monitored files
curl http://172.31.7.124:8754/api/monitored-files

# Remove the file first
curl -X DELETE http://172.31.7.124:8754/api/monitored-files/{file_id}

# Then add it again
```

---

### Issue: "Label already exists"

**Cause:** Another file is using the same label

**Solution:**

- Use a different label
- Or omit the label field to auto-generate

---

## Configuration File Structure

After adding files, the configuration is saved to `/etc/resolvix/config.json`:

```json
{
  "monitoring": {
    "log_files": [
      {
        "id": "file_001",
        "path": "/var/log/syslog",
        "label": "system",
        "priority": "high",
        "enabled": true,
        "created_at": "2025-12-24T10:00:00.000Z",
        "last_modified": "2025-12-24T10:00:00.000Z"
      },
      {
        "id": "file_002",
        "path": "/var/log/apache2/error.log",
        "label": "apache_errors",
        "priority": "high",
        "enabled": true,
        "created_at": "2025-12-24T10:30:00.000Z",
        "last_modified": "2025-12-24T10:30:00.000Z"
      }
    ]
  }
}
```

---

## Performance Considerations

### Resource Usage Per File:

- **1 thread** for monitoring
- **1 file handle** kept open
- **~1-2 MB RAM** per thread
- **Minimal CPU** when idle (waiting for writes)

### Recommendations:

- **Light usage:** 5-20 files - No concerns
- **Medium usage:** 20-50 files - Monitor thread count
- **Heavy usage:** 50+ files - Consider log aggregation

---

## Related Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config/monitored_files/add` | POST | Add new log files to monitoring |
| `/api/config/monitored_files/remove` | DELETE | Remove log files by label |
| `/api/monitored-files` | GET | List all monitored files |
| `/api/monitored-files` | POST | Legacy add files endpoint |
| `/api/monitored-files/{id}` | PUT | Update file configuration |
| `/api/monitored-files/{id}` | DELETE | Remove file by ID |
| `/api/monitored-files/reload` | POST | Reload monitoring config |

---

## Summary

### ADD Endpoint

✅ **Endpoint:** `POST /api/config/monitored_files/add`

✅ **Features:**
- Comprehensive validation (8 checks per file)
- Immediate monitoring without restart
- Persistent configuration
- Detailed error messages
- Partial success support

✅ **Status:** Fully implemented and ready for testing

✅ **Location:** [log_collector_daemon.py](../log_collector_daemon.py) (lines ~1443-1643)

### REMOVE Endpoint

✅ **Endpoint:** `DELETE /api/config/monitored_files/remove`

✅ **Features:**
- Remove multiple files by label
- Protection for auto-monitored files
- Graceful thread cleanup
- Persistent configuration updates
- Partial success support

✅ **Status:** Fully implemented and ready for testing

✅ **Location:** [log_collector_daemon.py](../log_collector_daemon.py) (lines ~1645-1777)

---

## Next Steps

1. **Backend Integration:**
   - Implement ADD and REMOVE endpoints in backend API
   - Add database storage for configurations
   - Create frontend UI for adding/removing files

2. **Testing:**
   - Run all test cases listed above
   - Test with various file types and paths
   - Verify monitoring starts and stops correctly
   - Test edge cases (auto-monitored files, duplicates, etc.)

3. **Documentation:**
   - Update API documentation
   - Add to Swagger/OpenAPI spec
   - Document for end users

4. **Enhancements:**
   - Add path whitelist validation
   - Implement max file limit
   - Add file size monitoring

---

**Implementation Date:** December 24, 2025

**Developer:** GitHub Copilot

**Status:** ✅ Complete and ready for deployment
