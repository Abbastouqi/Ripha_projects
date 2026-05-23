from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from backend.auth.auth import decode_token

security = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        return {
            "id":       int(payload["sub"]),
            "email":    payload["email"],
            "role":     payload["role"],
            "username": payload.get("username", ""),
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict | None:
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        return {
            "id":       int(payload["sub"]),
            "email":    payload["email"],
            "role":     payload["role"],
            "username": payload.get("username", ""),
        }
    except JWTError:
        return None


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
