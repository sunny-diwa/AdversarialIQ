"""
FastAPI Authentication & User Management Endpoints
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.auth.service import AuthService, UserRecord

logger = logging.getLogger("AuthRoutes")

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(..., example="admin")
    password: str = Field(..., example="admin123")


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, example="trader_john")
    password: str = Field(..., min_length=4, max_length=100, example="securePass123")
    role: str = Field("trader", example="trader")  # admin, trader, analyst


def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Extracts and verifies JWT token from Authorization Bearer header, if present."""
    if not authorization:
        return None
    try:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            payload = AuthService.verify_token(token)
            return payload
    except Exception as e:
        logger.debug(f"Auth header decode error: {e}")
    return None


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Requires valid JWT token in Authorization Bearer header."""
    user = get_current_user_optional(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Ensures the authenticated user has the 'admin' role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to access this resource."
        )
    return current_user


@auth_router.post("/login")
def login(req: LoginRequest) -> Dict[str, Any]:
    """Authenticates username/password and returns a signed JWT access token."""
    result = AuthService.authenticate(req.username, req.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Verify username and password."
        )
    return {
        "status": "success",
        "access_token": result["token"],
        "token_type": "bearer",
        "user": result["user"]
    }


@auth_router.get("/me")
def get_current_user_info(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Returns profile and permission details for the currently signed-in user."""
    uname = user.get("sub", "")
    record = AuthService.get_user_by_username(uname)
    if not record:
        raise HTTPException(status_code=404, detail="User record not found")
    return {
        "status": "success",
        "user": record.model_dump()
    }


@auth_router.get("/users")
def list_users(admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """Returns list of all registered users (Admin only)."""
    users = AuthService.list_users()
    return {
        "status": "success",
        "total": len(users),
        "users": users
    }


@auth_router.post("/users")
def create_new_user(
    req: CreateUserRequest,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    """Creates a new user with designated role (Admin only)."""
    try:
        new_user = AuthService.create_user(
            username=req.username,
            password=req.password,
            role=req.role
        )
        return {
            "status": "success",
            "message": f"User '{new_user['username']}' registered successfully",
            "user": new_user
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@auth_router.delete("/users/{username}")
def delete_user(
    username: str,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    """Deletes user by username (Admin only). Cannot delete oneself."""
    requesting_admin = admin.get("sub", "")
    try:
        success = AuthService.delete_user(username=username, requesting_admin=requesting_admin)
        if not success:
            raise HTTPException(status_code=404, detail=f"User '{username}' does not exist")
        return {
            "status": "success",
            "message": f"User '{username}' was deleted successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
