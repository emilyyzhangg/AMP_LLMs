"""
Authentication middleware for webapp.
"""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging

from .config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(
    scheme_name="API Key Authentication",
    description="Provide your API key in the Authorization header"
)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """
    Verify API key from Authorization header.
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        API key if valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    api_key = credentials.credentials
    
    if api_key not in settings.api_keys:
        logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Valid API key used: {api_key[:10]}...")
    return api_key


async def optional_verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(
        HTTPBearer(auto_error=False)
    )
) -> Optional[str]:
    """
    Optional API key verification (for public endpoints with optional auth).
    
    Returns:
        API key if provided and valid, None otherwise
    """
    if credentials is None:
        return None
    
    try:
        return await verify_api_key(credentials)
    except HTTPException:
        return None