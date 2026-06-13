"""TCP-based internet connectivity probe.

Probes all configured hosts concurrently; returns True if ANY is reachable.
Used by run_watchdog before each evaluate() call.
"""

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed


def probe_host(host: str, port: int = 53, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _parse(hosts_str: str) -> list[tuple[str, int]]:
    entries = []
    for part in hosts_str.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            host, port_s = part.rsplit(":", 1)
            entries.append((host.strip(), int(port_s)))
        else:
            entries.append((part, 53))
    return entries


def check_connectivity(hosts_str: str, timeout: float = 2.0) -> bool:
    """Return True if ANY host in hosts_str is reachable. Empty string → True."""
    entries = _parse(hosts_str)
    if not entries:
        return True
    with ThreadPoolExecutor(max_workers=len(entries)) as pool:
        futures = [pool.submit(probe_host, h, p, timeout) for h, p in entries]
        for f in as_completed(futures):
            if f.result():
                return True
    return False
