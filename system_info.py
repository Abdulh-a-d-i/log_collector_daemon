#!/usr/bin/env python3
# system_info.py
import platform
import psutil
import socket
import uuid
import json
import os

def get_system_info():
    uname = platform.uname()
    svmem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    ip = None
    for iface, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                ip = a.address
                break
        if ip:
            break

    return {
        "os": uname.system,
        "os_version": uname.version,
        "os_release": uname.release,
        "hostname": socket.gethostname(),
        "architecture": uname.machine,
        "mac": ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8 * 6, 8)][::-1]),
        "ip": ip or "NotFound",
        "disk_gb": {
            "total": round(disk.total / (1024**3), 2),
            "used": round(disk.used / (1024**3), 2),
            "free": round(disk.free / (1024**3), 2),
            "percent": disk.percent
        },
        "ram_gb": round(svmem.total / (1024**3), 2),
        "cpu": {
            "physical": psutil.cpu_count(logical=False),
            "logical": psutil.cpu_count(logical=True)
        }
    }

if __name__ == "__main__":
    info = get_system_info()
    with open("system_info.json", "w") as f:
        json.dump(info, f, indent=2)
    print("Saved system_info.json")
