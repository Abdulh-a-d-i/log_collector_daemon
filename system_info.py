#!/usr/bin/env python3
import platform
import psutil
import socket
import uuid
import json
from datetime import datetime

def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to a public IP (Google DNS)
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Not Found"

def get_system_info():
    uname = platform.uname()
    svmem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        "OS": uname.system,
        "OS_Version": uname.version,
        "OS_Release": uname.release,
        "Hostname": socket.gethostname(),
        "Machine_Architecture": uname.machine,
        "MAC_address": ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
                                 for ele in range(0, 8 * 6, 8)][::-1]),
        "IP_address": get_ip_address(),
        "Total_RAM_GB": round(svmem.total / (1024 ** 3), 2),
        "Total_Disk_GB": round(disk.total / (1024 ** 3), 2),
        "Disk_Used_GB": round(disk.used / (1024 ** 3), 2),
        "Disk_Free_GB": round(disk.free / (1024 ** 3), 2),
        "Disk_Usage_Percentage": disk.percent,
        "CPU_Physical_Core": psutil.cpu_count(logical=False),
        "CPU_logical_Core": psutil.cpu_count(logical=True),
    }


if __name__ == "__main__":
    info = get_system_info()
    with open("system_info.json", "w") as f:
        json.dump(info, f, indent=2)
    print("Saved system_info.json")