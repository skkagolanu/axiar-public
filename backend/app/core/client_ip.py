from ipaddress import ip_address

from fastapi import Request

from app.core.config import settings


def get_client_ip(request: Request) -> str:
    """Return a validated client IP, trusting only the configured proxy header."""
    header_name = settings.RATE_LIMIT_TRUSTED_PROXY_HEADER.strip()
    if header_name:
        forwarded_ip = request.headers.get(header_name, "").strip()
        try:
            return str(ip_address(forwarded_ip))
        except ValueError:
            pass

    return request.client.host if request.client else "unknown"
