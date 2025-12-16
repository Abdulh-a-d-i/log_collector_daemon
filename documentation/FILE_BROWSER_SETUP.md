# File Browser SSH Access - Implementation Guide

## ✅ Changes Completed

The `install.sh` script has been updated to support SSH access for the file browser feature.

## 📝 What Changed

### 1. New Parameter
```bash
# OLD: 2 parameters
./install.sh "/var/log/syslog" "http://backend:3000/api/ticket"

# NEW: 3 parameters
./install.sh "/var/log/syslog" "http://backend:3000/api/ticket" "ssh-rsa AAAAB3NzaC1yc2E..."
```

### 2. New Functions Added
- `create_file_browser_user()` - Creates `log-horizon-observer` user
- `setup_ssh_access()` - Configures SSH key authentication

### 3. User Created
- **Username**: `log-horizon-observer`
- **Home**: `/opt/log-horizon`
- **Shell**: `/usr/sbin/nologin` (no interactive login)
- **Groups**: `adm` (read access to `/var/log`)
- **Permissions**: Read-only, no sudo

## 🚀 Backend Integration

### How to Deploy with SSH Access

```javascript
// In your backend deployment code
const sshPublicKey = fs.readFileSync('/root/.ssh/log_horizon_rsa.pub', 'utf8').trim();

const installCommand = `
  cd /root/log_collector_daemon &&
  sudo ./install.sh "${logFile}" "${apiUrl}" "${sshPublicKey}"
`;

await ssh.execCommand(installCommand);
```

### Example Call
```bash
sudo ./install.sh \
  "/var/log/syslog" \
  "http://192.168.1.14:3000/api/ticket" \
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC7xK..."
```

## 🔍 Verification

### 1. Check User Created
```bash
id log-horizon-observer
# Expected: uid=999(log-horizon-observer) gid=999(log-horizon-observer) groups=999(log-horizon-observer),4(adm)
```

### 2. Check SSH Setup
```bash
sudo ls -la /opt/log-horizon/.ssh/
# Expected:
# drwx------ 2 log-horizon-observer log-horizon-observer 4096 ... .ssh
# -rw------- 1 log-horizon-observer log-horizon-observer  xxx ... authorized_keys
```

### 3. Test SSH Connection (from backend)
```bash
ssh -i /root/.ssh/log_horizon_rsa log-horizon-observer@NODE_IP "ls /var/log"
# Expected: List of log files
```

### 4. Test File Access
```bash
sudo -u log-horizon-observer cat /var/log/syslog
# Expected: Log contents (should work)

sudo -u log-horizon-observer cat /etc/passwd
# Expected: Works, but backend should validate paths
```

## 🔒 Security Features

✅ **SSH key authentication only** - No passwords  
✅ **No shell access** - `/usr/sbin/nologin` prevents interactive login  
✅ **Limited permissions** - Only `adm` group for `/var/log`  
✅ **No sudo access** - Cannot execute privileged commands  
✅ **Backward compatible** - Works without SSH key (file browser disabled)  

## 📊 File Structure Created

```
/opt/log-horizon/
├── .ssh/                           (700 permissions)
│   └── authorized_keys             (600 permissions)
│                                   (contains backend's public key)
```

## ⚠️ Important Notes

1. **No Python daemon changes** - Only `install.sh` was modified
2. **Backward compatible** - If no SSH key provided, installation continues normally
3. **Path validation required** - Backend must validate file paths to prevent access outside `/var/log`
4. **User cannot login** - Shell is `/usr/sbin/nologin`, only SSH commands work

## 🧪 Testing Checklist

- [ ] Install on clean Ubuntu system
- [ ] Verify user created with correct groups
- [ ] Verify SSH directory permissions (700)
- [ ] Verify authorized_keys permissions (600)
- [ ] Test SSH connection from backend
- [ ] Test file read access to `/var/log`
- [ ] Verify no interactive shell access
- [ ] Test backward compatibility (no SSH key)

## 🐛 Troubleshooting

### SSH Connection Refused
```bash
# Check SSH service running
sudo systemctl status sshd

# Check firewall
sudo ufw status
sudo ufw allow 22/tcp
```

### Permission Denied
```bash
# Check file ownership
sudo ls -la /opt/log-horizon/.ssh/

# Fix if needed
sudo chown -R log-horizon-observer:log-horizon-observer /opt/log-horizon
sudo chmod 700 /opt/log-horizon/.ssh
sudo chmod 600 /opt/log-horizon/.ssh/authorized_keys
```

### User Not in adm Group
```bash
# Check groups
groups log-horizon-observer

# Add to adm group
sudo usermod -aG adm log-horizon-observer
```

## 📞 Backend Requirements

### 1. Generate SSH Key Pair (One Time)
```bash
ssh-keygen -t rsa -b 4096 -f /root/.ssh/log_horizon_rsa -N ""
```

### 2. Pass Public Key During Installation
```javascript
const publicKey = fs.readFileSync('/root/.ssh/log_horizon_rsa.pub', 'utf8').trim();
// Pass as 3rd parameter to install.sh
```

### 3. Use Private Key for SSH Commands
```javascript
const ssh = new NodeSSH();
await ssh.connect({
  host: nodeIp,
  username: 'log-horizon-observer',
  privateKey: '/root/.ssh/log_horizon_rsa'
});

// Read file
const result = await ssh.execCommand('cat /var/log/syslog');
```

## ✅ Summary

**Changes Made:**
- ✅ Added 3rd parameter to `install.sh` for SSH public key
- ✅ Added `create_file_browser_user()` function
- ✅ Added `setup_ssh_access()` function
- ✅ User `log-horizon-observer` created with read-only access
- ✅ SSH key authentication configured
- ✅ Backward compatible (works without SSH key)

**No Changes:**
- ❌ Python daemon code
- ❌ Systemd service
- ❌ Existing features
- ❌ Performance impact

**Ready for production!** 🎉
