from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from nexus_app.database import get_db
from nexus_app.models.user import User, APIKey
from nexus_app.schemas.auth import UserCreate, UserLogin, UserOut, Token, APIKeyCreate, APIKeyOut, APIKeyCreatedOut
from nexus_app.security.auth import hash_password, verify_password, create_access_token, get_current_user, generate_api_key

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    hashed_pw = hash_password(user_in.password)
    user = User(
        email=user_in.email,
        hashed_password=hashed_pw,
        full_name=user_in.full_name,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=Token)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_in.email).first()
    if not user or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User account is inactive")

    token = create_access_token({"sub": user.id, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.get("/me", response_model=UserOut)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/api-keys", response_model=APIKeyCreatedOut)
def create_new_api_key(
    key_in: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    raw_key, prefix, hashed_key = generate_api_key()
    api_key_record = APIKey(
        user_id=current_user.id,
        name=key_in.name,
        key_prefix=prefix,
        key_hash=hashed_key
    )
    db.add(api_key_record)
    db.commit()
    db.refresh(api_key_record)

    return APIKeyCreatedOut(
        id=api_key_record.id,
        name=api_key_record.name,
        key_prefix=api_key_record.key_prefix,
        created_at=api_key_record.created_at,
        last_used_at=api_key_record.last_used_at,
        is_revoked=api_key_record.is_revoked,
        api_key=raw_key
    )

@router.get("/api-keys", response_model=List[APIKeyOut])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(APIKey).filter(APIKey.user_id == current_user.id, APIKey.is_revoked == False).all()

@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API Key not found")
    key.is_revoked = True
    db.commit()
    return None
