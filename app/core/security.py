from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Query, WebSocketException
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
import redis
import logging

logger = logging.getLogger(__name__)

# Flask Rate Limit Setup
try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception as e:
    logger.error(f"Failed to initialize Redis for rate_limit: {e}")
    redis_client = None


def rate_limit(limit: int, per: int = 60):
    from functools import wraps
    from flask import request, abort

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not redis_client:
                return f(*args, **kwargs)
            ip = request.remote_addr or "unknown_ip"
            endpoint = request.endpoint or "unknown_endpoint"
            key = f"rate_limit:{ip}:{endpoint}"
            try:
                current = redis_client.get(key)
                if current and int(current) >= limit:
                    abort(429, "Too Many Requests")
                pipe = redis_client.pipeline()
                pipe.incr(key)
                if not current:
                    pipe.expire(key, per)
                pipe.execute()
            except redis.ConnectionError:
                pass
            return f(*args, **kwargs)
        return wrapper
    return decorator


# FastAPI OAuth2 & Security Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token", auto_error=False
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


# Dependency for standard requests
async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    query_token: Optional[str] = Query(None, alias="token")
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Prefer header, fallback to query param (for EventSource/WebSockets)
    jwt_token = token or query_token
    if not jwt_token:
        raise credentials_exception

    try:
        payload = jwt.decode(
            jwt_token, settings.APP_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None or username != settings.ADMIN_USERNAME:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception


# Dependency for WebSockets
async def get_current_user_ws(token: Optional[str] = Query(None)):
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        payload = jwt.decode(
            token, settings.APP_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None or username != settings.ADMIN_USERNAME:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        return username
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
