#!/usr/bin/env python3
import platform
import psutil
import socket
import uuid
import json
from datetime import datetime

def get_ip_address():
    """
    Get the actual network IP address.
    Never returns 127.0.0.1 or localhost IPs.
    """
    # Method 1: Connect to external address to determine routing IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))  # Connect to Google DNS (doesn't send data)
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != "127.0.0.1" and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    
    # Method 2: Try hostname resolution
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and ip != "127.0.0.1" and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    
    # Method 3: Try all network interfaces
    try:
        import netifaces
        for interface in netifaces.interfaces():
            if interface.startswith('lo'):  # Skip loopback
                continue
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get('addr')
                    if ip and ip != "127.0.0.1" and not ip.startswith("127."):
                        return ip
    except ImportError:
        pass
    except Exception:
        pass
    
    return "IP_Not_Found"

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