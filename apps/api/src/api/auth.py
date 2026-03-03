# apps/api/src/api/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_query_scheme = APIKeyQuery(name="key", auto_error=False)


def get_api_key(
    header_key: str = Security(_header_scheme),
    query_key: str = Security(_query_scheme),
) -> str:
    from core.config import get_settings
    expected = get_settings().dashboard_api_key
    if not expected:
        return ""  # Auth disabled when key not configured
    provided = header_key or query_key
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return provided
