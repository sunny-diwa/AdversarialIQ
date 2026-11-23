"""
AdversarialIQ User Authentication & Role-Based Access Control (RBAC) Service
Provides SQLite-backed user storage, bcrypt hashing, JWT issuance & verification,
and automatic admin provisioning based on .env configuration.
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
from pydantic import BaseModel, Field

from src.core.config import DATA_DIR

logger = logging.getLogger("AuthService")

USER_DB_FILE = DATA_DIR / "users.db"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "adversarialiq-jwt-secret-key-38bdf8")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days session validity


class UserRecord(BaseModel):
    id: int
    username: str
    role: str  # "admin", "trader", "analyst"
    created_at: str
    last_login: Optional[str] = None


class AuthService:
    """Manages user persistence, bcrypt hashing, and JWT token issuance."""

    @classmethod
    def init_db(cls):
        """Initializes SQLite user table and provisions initial Admin user."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'trader',
                    created_at TEXT NOT NULL,
                    last_login TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
            conn.commit()

        # Provision initial Admin from .env if table is empty
        cls._seed_admin_if_needed()

    @classmethod
    def _seed_admin_if_needed(cls):
        """Seeds default admin credentials from environment if no admin exists."""
        admin_user = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123").strip()

        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username FROM users WHERE username = ?", (admin_user,))
            existing = cursor.fetchone()

            if not existing:
                hashed = cls.hash_password(admin_pass)
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role, created_at)
                    VALUES (?, ?, 'admin', ?)
                """, (admin_user, hashed, now))
                conn.commit()
                logger.info(f"Initialized root admin user '{admin_user}' from .env")
            else:
                # Optionally sync password if explicitly set in environment
                env_pass = os.getenv("ADMIN_PASSWORD")
                if env_pass:
                    hashed = cls.hash_password(env_pass)
                    cursor.execute("""
                        UPDATE users SET password_hash = ? WHERE username = ?
                    """, (hashed, admin_user))
                    conn.commit()

    @staticmethod
    def hash_password(password: str) -> str:
        """Hashes password using bcrypt with cryptographic salt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifies plain password against stored bcrypt hash."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    @classmethod
    def create_token(cls, username: str, role: str) -> str:
        """Generates a signed JWT access token."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": username,
            "role": role,
            "iat": now,
            "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iss": "adversarialiq-auth"
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    @classmethod
    def verify_token(cls, token: str) -> Optional[Dict[str, Any]]:
        """Decodes and validates a JWT access token."""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None

    @classmethod
    def authenticate(cls, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verifies credentials, updates last_login timestamp, and issues JWT."""
        user = username.strip().lower()
        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, password_hash, role, created_at, last_login FROM users WHERE username = ?",
                (user,)
            )
            row = cursor.fetchone()

        if not row:
            return None

        uid, uname, phash, role, cat, llog = row
        if not cls.verify_password(password, phash):
            return None

        # Update last login
        now_str = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_str, uid))
            conn.commit()

        token = cls.create_token(username=uname, role=role)
        return {
            "token": token,
            "user": {
                "id": uid,
                "username": uname,
                "role": role,
                "created_at": cat,
                "last_login": now_str
            }
        }

    @classmethod
    def get_user_by_username(cls, username: str) -> Optional[UserRecord]:
        """Fetches user record by username."""
        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, role, created_at, last_login FROM users WHERE username = ?",
                (username.strip().lower(),)
            )
            row = cursor.fetchone()

        if not row:
            return None

        return UserRecord(
            id=row[0],
            username=row[1],
            role=row[2],
            created_at=row[3],
            last_login=row[4]
        )

    @classmethod
    def list_users(cls) -> List[Dict[str, Any]]:
        """Returns all registered users (excluding password hashes)."""
        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role, created_at, last_login FROM users ORDER BY id ASC")
            rows = cursor.fetchall()

        return [
            {
                "id": r[0],
                "username": r[1],
                "role": r[2],
                "created_at": r[3],
                "last_login": r[4]
            }
            for r in rows
        ]

    @classmethod
    def create_user(cls, username: str, password: str, role: str = "trader") -> Dict[str, Any]:
        """Creates a new user record. Enforces unique username."""
        uname = username.strip().lower()
        if not uname or len(uname) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not password or len(password) < 4:
            raise ValueError("Password must be at least 4 characters")

        valid_roles = ["admin", "trader", "analyst"]
        clean_role = role.strip().lower()
        if clean_role not in valid_roles:
            clean_role = "trader"

        hashed = cls.hash_password(password)
        now_str = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?)
                """, (uname, hashed, clean_role, now_str))
                uid = cursor.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"User '{uname}' already exists")

        return {
            "id": uid,
            "username": uname,
            "role": clean_role,
            "created_at": now_str
        }

    @classmethod
    def delete_user(cls, username: str, requesting_admin: str) -> bool:
        """Deletes user by username. Prevents deleting oneself."""
        target = username.strip().lower()
        requester = requesting_admin.strip().lower()

        if target == requester:
            raise ValueError("Admins cannot delete their own active account")

        with sqlite3.connect(str(USER_DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE username = ?", (target,))
            deleted = cursor.rowcount > 0
            conn.commit()

        return deleted


# Initialize database upon import
AuthService.init_db()
