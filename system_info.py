#!/usr/bin/env python3
import platform
import psutil
import socket
import uuid
import json
from datetime import datetime

def get_system_info():
    uname = platform.uname()
    disk = psutil.disk_usage('/')
    svmem = psutil.virtual_memory()
    ip = None
    for iface, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                ip = a.address
                break
        if ip:
            break
    return {
        "collected_at": datetime.utcnow().isoformat() + "Z",
        "hostname": socket.gethostname(),
        "ip": ip or "NotFound",
        "os": uname.system,
        "os_version": uname.version,
        "arch": uname.machine,
        "mac": ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0,8*6,8)][::-1]),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "ram_gb": round(svmem.total / (1024**3), 2),
        "cpu_physical": psutil.cpu_count(logical=False),
        "cpu_logical": psutil.cpu_count(logical=True)
    }

if __name__ == "__main__":
    info = get_system_info()
    with open("system_info.json", "w") as f:
        json.dump(info, f, indent=2)
    print("Saved system_info.json")
