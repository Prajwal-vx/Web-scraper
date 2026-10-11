import ipaddress
import socket
from urllib.parse import urlparse, urljoin
from typing import Tuple, List

class SSRFSecurityError(ValueError):
    """Raised when a URL violates SSRF security boundaries."""
    pass

# Blocked IP networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),         # Broadcast/Zero
    ipaddress.ip_network("10.0.0.0/8"),        # Private network
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / Cloud metadata (AWS, GCP, Azure)
    ipaddress.ip_network("172.16.0.0/12"),     # Private network
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),    # Private network
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved
    ipaddress.ip_network("255.255.255.255/32"),# Broadcast
    # IPv6 blocked
    ipaddress.ip_network("::1/128"),           # Loopback IPv6
    ipaddress.ip_network("fc00::/7"),          # Unique local address
    ipaddress.ip_network("fe80::/10"),         # Link-local IPv6
    ipaddress.ip_network("ff00::/8"),          # Multicast IPv6
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}

def is_ip_blocked(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Checks whether an IP address belongs to any blocked/private/link-local network."""
    if ip_addr.is_loopback or ip_addr.is_private or ip_addr.is_link_local or ip_addr.is_multicast or ip_addr.is_reserved:
        return True
    for network in BLOCKED_NETWORKS:
        if ip_addr in network:
            return True
    return False

def resolve_hostname(hostname: str) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolves hostname to IP addresses via DNS."""
    try:
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        resolved_ips = []
        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            resolved_ips.append(ipaddress.ip_address(ip_str))
        return resolved_ips
    except socket.gaierror as e:
        raise SSRFSecurityError(f"DNS resolution failed for host '{hostname}': {e}")

def validate_url(url_string: str) -> Tuple[bool, str]:
    """
    Validates a URL against SSRF vulnerabilities:
    - Must be http or https
    - No credentials (user:pass)
    - Valid host
    - Does not resolve to private, loopback, or cloud-metadata IPs.
    Returns (True, normalized_url) or raises SSRFSecurityError.
    """
    if not url_string or not isinstance(url_string, str):
        raise SSRFSecurityError("URL must be a non-empty string.")

    url_string = url_string.strip()
    parsed = urlparse(url_string)

    # 1. Scheme check
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityError(f"Unsupported scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed.")

    # 2. Host check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL is missing a valid hostname.")

    hostname = hostname.lower()

    # Blocked hostnames check
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise SSRFSecurityError(f"Hostname '{hostname}' is not permitted.")

    # 3. Userinfo check
    if parsed.username or parsed.password:
        raise SSRFSecurityError("Embedded credentials in URLs are rejected.")

    # 4. Check if direct IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if is_ip_blocked(ip):
            raise SSRFSecurityError(f"Target IP address '{ip}' is in a private, loopback, or reserved range.")
        return True, url_string
    except ValueError:
        pass  # Not an IP string, proceed to DNS resolution

    # 5. DNS Resolution check
    resolved_ips = resolve_hostname(hostname)
    if not resolved_ips:
        raise SSRFSecurityError(f"Could not resolve any IP addresses for host '{hostname}'.")

    for ip in resolved_ips:
        if is_ip_blocked(ip):
            raise SSRFSecurityError(
                f"Host '{hostname}' resolved to blocked/private address '{ip}'. Connection rejected to prevent SSRF."
            )

    return True, url_string

def validate_redirect(target_url: str, base_url: str) -> str:
    """Validates that a redirected URL is secure and does not bypass SSRF checks."""
    resolved_target = urljoin(base_url, target_url)
    validate_url(resolved_target)
    return resolved_target
