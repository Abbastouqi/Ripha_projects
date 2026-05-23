from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.auth.auth import hash_password, verify_password, create_access_token
from backend.auth.dependencies import get_current_user
from backend.database.db import create_user, get_user_by_email, get_user_by_id

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def _safe_user(user: dict) -> dict:
    return {
        "id":       user["id"],
        "username": user["username"],
        "email":    user["email"],
        "role":     user["role"],
    }


@router.post("/register")
def register(req: RegisterRequest):
    if len(req.username.strip()) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    try:
        existing = get_user_by_email(req.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = create_user(req.username.strip(), req.email.lower().strip(), hash_password(req.password))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {e}")

    token = create_access_token(user["id"], user["email"], user["role"], user["username"])
    return {"token": token, "user": _safe_user(user)}


@router.post("/login")
def login(req: LoginRequest):
    try:
        user = get_user_by_email(req.email.lower().strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled. Contact admin.")

    token = create_access_token(user["id"], user["email"], user["role"], user["username"])
    return {"token": token, "user": _safe_user(user)}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    try:
        user = get_user_by_id(current_user["id"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _safe_user(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
