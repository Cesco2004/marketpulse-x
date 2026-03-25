"""System health monitoring for Oracle Cloud Free Tier.

Reports disk, memory, and database size without external dependencies.
Uses only Python stdlib + /proc/meminfo on Linux (falls back gracefully on macOS).
"""

import os
import shutil

import config


def get_system_health():
    """Return system health metrics.

    Returns dict with disk, memory (if available), and DB size.
    """
    result = {}

    # Disk usage
    try:
        disk = shutil.disk_usage("/")
        result["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        result["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
        result["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
        result["disk_pct"] = round(disk.used / disk.total * 100, 1) if disk.total else 0
    except Exception:
        result["disk_total_gb"] = 0
        result["disk_used_gb"] = 0
        result["disk_free_gb"] = 0
        result["disk_pct"] = 0

    # Memory (Linux: /proc/meminfo, macOS: fallback)
    result.update(_get_memory())

    # Database size
    try:
        db_path = config.DB_PATH
        if os.path.exists(db_path):
            result["db_size_mb"] = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        else:
            result["db_size_mb"] = 0
    except Exception:
        result["db_size_mb"] = 0

    # Overall status
    result["status"] = _compute_status(result)

    return result


def _get_memory():
    """Try to read memory info from /proc/meminfo (Linux), fallback on macOS."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        info = {}
        for line in lines:
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]  # value in kB
                info[key] = int(val)

        total_mb = info.get("MemTotal", 0) / 1024
        available_mb = info.get("MemAvailable", 0) / 1024
        used_mb = total_mb - available_mb

        return {
            "mem_total_mb": round(total_mb),
            "mem_used_mb": round(used_mb),
            "mem_free_mb": round(available_mb),
            "mem_pct": round(used_mb / total_mb * 100, 1) if total_mb else 0,
        }
    except FileNotFoundError:
        # macOS or other non-Linux
        try:
            import subprocess
            # sysctl on macOS
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            total_mb = int(out) / (1024 * 1024)
            return {
                "mem_total_mb": round(total_mb),
                "mem_used_mb": 0,
                "mem_free_mb": 0,
                "mem_pct": 0,
            }
        except Exception:
            return {
                "mem_total_mb": 0,
                "mem_used_mb": 0,
                "mem_free_mb": 0,
                "mem_pct": 0,
            }
    except Exception:
        return {
            "mem_total_mb": 0,
            "mem_used_mb": 0,
            "mem_free_mb": 0,
            "mem_pct": 0,
        }


def _compute_status(health):
    """Determine overall health status."""
    if health["disk_pct"] >= 95:
        return "critical"
    if health["disk_pct"] >= 80 or health.get("mem_pct", 0) >= 90:
        return "warning"
    return "ok"
