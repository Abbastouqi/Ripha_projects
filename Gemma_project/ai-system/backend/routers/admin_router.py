from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.auth.dependencies import require_admin
from backend.database.db import (
    get_all_users, update_user_role, toggle_user_active,
    delete_user_by_id, get_user_by_id, get_system_stats,
    get_all_appointments, get_all_doctors, get_sessions,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class RoleUpdate(BaseModel):
    role: str


@router.get("/stats")
def stats(admin: dict = Depends(require_admin)):
    try:
        return get_system_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users")
def list_users(admin: dict = Depends(require_admin)):
    try:
        return [dict(u) for u in get_all_users()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}/role")
def set_role(user_id: int, body: RoleUpdate, admin: dict = Depends(require_admin)):
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
    try:
        update_user_role(user_id, body.role)
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}/toggle")
def toggle_active(user_id: int, admin: dict = Depends(require_admin)):
    try:
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        new_state = not user.get("is_active", True)
        toggle_user_active(user_id, new_state)
        return {"status": "ok", "is_active": new_state}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        delete_user_by_id(user_id)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/appointments")
def list_appointments(admin: dict = Depends(require_admin)):
    try:
        return [dict(a) for a in get_all_appointments()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/doctors")
def list_doctors(admin: dict = Depends(require_admin)):
    try:
        return [dict(d) for d in get_all_doctors()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
def list_sessions(admin: dict = Depends(require_admin)):
    try:
        return [dict(s) for s in get_sessions()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
