
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.orm import Session

from nexus_app.config import settings
from nexus_app.database import get_db
from nexus_app.models.user import User, APIKey
from nexus_app.schemas.auth import TokenData

security_bearer = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with a unique random salt."""
    salt = os.urandom(16).hex()
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        bytes.fromhex(salt),
        iterations
    ).hex()
    return f"pbkdf2:sha256:{iterations}${salt}${derived}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored PBKDF2 hash."""
    try:
        if not hashed_password.startswith("pbkdf2:sha256:"):
            return False
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        meta, salt, expected_hash = parts
        iterations = int(meta.split(":")[2])
        derived = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            bytes.fromhex(salt),
            iterations
        ).hex()
        return hmac.compare_digest(derived, expected_hash)
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encodes a JWT access token with expiration time."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[TokenData]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        if user_id is None:
            return None
        return TokenData(user_id=user_id, email=email)
    except (jwt.PyJWTError, Exception):
        return None

def hash_api_key(api_key: str) -> str:
    """Hashes an API key using SHA-256 for secure lookup."""
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

def generate_api_key() -> tuple[str, str, str]:
    """
    Generates a new secure API key with prefix.
    Returns (raw_key, prefix, hashed_key)
    """
    token = secrets.token_urlsafe(32)
    raw_key = f"nxs_{token}"
    prefix = raw_key[:8]
    hashed_key = hash_api_key(raw_key)
    return raw_key, prefix, hashed_key

def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    api_key_val: Optional[str] = Security(api_key_header),
    db: Session = Depends(get_db)
) -> User:
    """
    Resolves the current authenticated user via either:
    1. Authorization: Bearer <JWT>
    2. X-API-Key: <nxs_...>
    """
    # 1. Check Bearer token
    if auth and auth.credentials:
        token_data = decode_access_token(auth.credentials)
        if token_data and token_data.user_id:
            user = db.query(User).filter(User.id == token_data.user_id, User.is_active == True).first()
            if user:
                return user

    # 2. Check API Key
    if api_key_val:
        key_hash = hash_api_key(api_key_val)
        api_key_record = db.query(APIKey).filter(
            APIKey.key_hash == key_hash,
            APIKey.is_revoked == False
        ).first()
        if api_key_record:
            if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key has expired")
            api_key_record.last_used_at = datetime.utcnow()
            db.commit()
            user = db.query(User).filter(User.id == api_key_record.user_id, User.is_active == True).first()
            if user:
                return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials were not provided or are invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )
