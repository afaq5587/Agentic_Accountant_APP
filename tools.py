"""Tooling and data layer for SHAHENSHA GROUP' ACCOUNTANT.

This module defines the database helpers, tool registry, and tool implementations
that will be consumed by the agent layer. The goal is to mirror the OpenAI
Agents SDK structure while remaining fully local and Gemini-powered.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


# ---------------------------------------------------------------------------
# Database Layer
# ---------------------------------------------------------------------------


class MemberDatabase:
    """SQLite-backed store for member and admin records."""

    def __init__(self, db_path: str | os.PathLike[str]):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS members (
                    member_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    payment_status TEXT CHECK(payment_status IN ('Paid', 'Unpaid')) NOT NULL DEFAULT 'Unpaid',
                    amount REAL NOT NULL,
                    role TEXT CHECK(role IN ('Admin', 'User')) NOT NULL DEFAULT 'User',
                    password_hash TEXT,
                    password_salt TEXT,
                    phone TEXT
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    image_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rules_and_regulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._connection.commit()
            self._ensure_member_columns()

    def _ensure_member_columns(self) -> None:
        """Ensure optional columns exist for older databases."""
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA table_info(members)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "phone" not in columns:
            cursor.execute("ALTER TABLE members ADD COLUMN phone TEXT")
        if "last_payment_date" not in columns:
            cursor.execute("ALTER TABLE members ADD COLUMN last_payment_date TIMESTAMP")
        self._connection.commit()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        salt = salt or os.urandom(16).hex()
        digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
        return digest, salt

    def _validate_amount(self, amount: float) -> None:
        if amount < 250:
            raise ValueError("Minimum payment amount is ₨250")

    @staticmethod
    def _sanitize_record(record: Optional[Dict[str, Any] | sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if record is None:
            return None
        if isinstance(record, sqlite3.Row):
            record = dict(record)
        sanitized = dict(record)
        sanitized.pop("password_hash", None)
        sanitized.pop("password_salt", None)
        return sanitized

    def _execute(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(query, tuple(params))
            self._connection.commit()
            return cursor

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def add_member(
        self,
        member_id: str,
        name: str,
        amount: float,
        role: str = "User",
        password: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_amount(amount)
        password_hash: Optional[str] = None
        password_salt: Optional[str] = None
        if role == "Admin":
            if not password:
                raise ValueError("Admin accounts require a password")
            password_hash, password_salt = self._hash_password(password)

        try:
            self._execute(
                """
                INSERT INTO members (member_id, name, payment_status, amount, role, password_hash, password_salt, phone)
                VALUES (?, ?, 'Unpaid', ?, ?, ?, ?, ?)
                """,
                (member_id, name, amount, role, password_hash, password_salt, phone),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Member with id '{member_id}' already exists") from exc

        return self.get_member(member_id)

        if payment_status:
            if payment_status not in {"Paid", "Unpaid"}:
                raise ValueError("payment_status must be 'Paid' or 'Unpaid'")
            fields["payment_status"] = payment_status
        if phone is not None:
            fields["phone"] = phone
        
        # Allow passing extra fields like last_payment_date via kwargs if needed, 
        # but for now we'll just handle it if passed in the fields dict by internal callers
        # (mark_payment calls update_member with **kwargs)
        # We need to update the signature or just handle **kwargs in update_member if we want to be clean,
        # but since mark_payment calls update_member, we need to make sure update_member accepts it.
        # Let's modify update_member signature to accept **kwargs for flexibility.
        pass # Placeholder to keep context, actual change below in separate edit if needed.
        # Actually, mark_payment calls update_member(..., **update_kwargs). 
        # update_member signature is fixed. We need to add **kwargs to update_member or add the param.
        
    def update_member(
        self,
        member_id: str,
        name: Optional[str] = None,
        amount: Optional[float] = None,
        payment_status: Optional[str] = None,
        phone: Optional[str] = None,
        last_payment_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        if name:
            fields["name"] = name
        if amount is not None:
            self._validate_amount(amount)
            fields["amount"] = amount
        if payment_status:
            if payment_status not in {"Paid", "Unpaid"}:
                raise ValueError("payment_status must be 'Paid' or 'Unpaid'")
            fields["payment_status"] = payment_status
        if phone is not None:
            fields["phone"] = phone
        if last_payment_date is not None:
            fields["last_payment_date"] = last_payment_date

        if not fields:
            raise ValueError("No updates provided")

        assignments = ", ".join(f"{column} = ?" for column in fields)
        params = list(fields.values()) + [member_id]
        cursor = self._execute(
            f"UPDATE members SET {assignments} WHERE member_id = ?", params
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Member '{member_id}' not found")
        return self.get_member(member_id)

    def delete_member(self, member_id: str) -> Dict[str, Any]:
        member = self.get_member(member_id)
        cursor = self._execute("DELETE FROM members WHERE member_id = ?", (member_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Member '{member_id}' not found")
        return member

    def list_members(self) -> List[Dict[str, Any]]:
        cursor = self._execute("SELECT * FROM members ORDER BY name ASC")
        return [self._sanitize_record(row) for row in cursor.fetchall()]

    def get_member(self, member_id: str) -> Dict[str, Any]:
        cursor = self._execute("SELECT * FROM members WHERE member_id = ?", (member_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Member '{member_id}' not found")
        return self._sanitize_record(row)

    def mark_payment(self, member_id: str, payment_status: str, amount: Optional[float] = None) -> Dict[str, Any]:
        if payment_status not in {"Paid", "Unpaid"}:
            raise ValueError("payment_status must be 'Paid' or 'Unpaid'")
        
        update_kwargs: Dict[str, Any] = {"payment_status": payment_status}
        if payment_status == "Paid":
            from datetime import datetime
            update_kwargs["last_payment_date"] = datetime.now().isoformat()
            
        if amount is not None:
            self._validate_amount(amount)
            update_kwargs["amount"] = amount
        return self.update_member(member_id, **update_kwargs)

    def change_admin_password(self, admin_id: str, new_password: str) -> Dict[str, Any]:
        row = self.get_member(admin_id)
        if row["role"] != "Admin":
            raise ValueError("Password changes are only supported for admins")
        password_hash, password_salt = self._hash_password(new_password)
        self._execute(
            "UPDATE members SET password_hash = ?, password_salt = ? WHERE member_id = ?",
            (password_hash, password_salt, admin_id),
        )
        return self.get_member(admin_id)

    def verify_admin(self, admin_id: str, password: str) -> bool:
        cursor = self._execute(
            "SELECT password_hash, password_salt FROM members WHERE member_id = ? AND role = 'Admin'",
            (admin_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Admin '{admin_id}' not found")
        password_hash = row["password_hash"]
        password_salt = row["password_salt"]
        if not password_hash or not password_salt:
            raise ValueError("Admin account has no password set")
        expected_hash, _ = self._hash_password(password, salt=password_salt)
        return expected_hash == password_hash

    def check_and_reset_monthly_payments(self) -> int:
        """
        Check if it's the 28th of the month (or later).
        If so, and we haven't reset payments for this month yet,
        reset all 'Paid' members to 'Unpaid'.
        """
        from datetime import datetime
        
        now = datetime.now()
        current_month_key = f"reset_{now.year}_{now.month}"
        
        # Only proceed if it's the 28th or later
        if now.day < 28:
            return 0
            
        with self._lock:
            # Check if already run for this month
            cursor = self._execute(
                "SELECT value FROM metadata WHERE key = ?", 
                (current_month_key,)
            )
            if cursor.fetchone():
                return 0
            
            # Reset all Paid members to Unpaid
            # We don't need to check last_payment_date anymore, just reset everyone
            cursor = self._execute(
                "UPDATE members SET payment_status = 'Unpaid' WHERE payment_status = 'Paid'"
            )
            count = cursor.rowcount
            
            # Mark as done for this month
            self._execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (current_month_key, now.isoformat())
            )
            
            return count

    def ensure_default_admin(self) -> None:
        """Ensure default admin exists with known password. Reset password if admin exists."""
        default_password = "admin@250"
        default_admin_id = "admin"
        
        # Check if default admin exists
        try:
            existing_admin = self.get_member(default_admin_id)
            # Admin exists, check if it's an Admin role and reset password
            cursor = self._execute(
                "SELECT role FROM members WHERE member_id = ?",
                (default_admin_id,)
            )
            row = cursor.fetchone()
            if row and row[0] == "Admin":
                # Reset password for existing admin
                password_hash, password_salt = self._hash_password(default_password)
                self._execute(
                    """
                    UPDATE members 
                    SET password_hash = ?, password_salt = ?, role = 'Admin'
                    WHERE member_id = ?
                    """,
                    (password_hash, password_salt, default_admin_id),
                )
                return
        except ValueError:
            # Admin doesn't exist, create it
            pass
        
        # Check if any admin exists
        cursor = self._execute("SELECT COUNT(*) as count FROM members WHERE role = 'Admin'")
        row = cursor.fetchone()
        if row["count"] == 0:
            # Provide a default admin for first-run experience
            password_hash, password_salt = self._hash_password(default_password)
            try:
                self._execute(
                    """
                    INSERT INTO members (member_id, name, payment_status, amount, role, password_hash, password_salt)
                    VALUES (?, 'Primary Admin', 'Paid', 250, 'Admin', ?, ?)
                    """,
                    (default_admin_id, password_hash, password_salt),
                )
            except Exception:
                # Admin might have been created by another process, try to update password
                password_hash, password_salt = self._hash_password(default_password)
                self._execute(
                    """
                    UPDATE members 
                    SET password_hash = ?, password_salt = ?, role = 'Admin', name = 'Primary Admin'
                    WHERE member_id = ?
                    """,
                    (password_hash, password_salt, default_admin_id),
                )

    # ------------------------------------------------------------------
    # Announcements CRUD operations
    # ------------------------------------------------------------------

    def add_announcement(self, title: str, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Add a new announcement."""
        cursor = self._execute(
            """
            INSERT INTO announcements (title, text, image_path)
            VALUES (?, ?, ?)
            """,
            (title, text, image_path),
        )
        announcement_id = cursor.lastrowid
        return self.get_announcement(announcement_id)

    def get_announcement(self, announcement_id: int) -> Dict[str, Any]:
        """Get a single announcement by ID."""
        cursor = self._execute("SELECT * FROM announcements WHERE id = ?", (announcement_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Announcement with id '{announcement_id}' not found")
        return dict(row)

    def list_announcements(self) -> List[Dict[str, Any]]:
        """List all announcements, most recent first."""
        cursor = self._execute("SELECT * FROM announcements ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def update_announcement(
        self, announcement_id: int, title: Optional[str] = None, 
        text: Optional[str] = None, image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an announcement."""
        fields: Dict[str, Any] = {}
        if title:
            fields["title"] = title
        if text is not None:
            fields["text"] = text
        if image_path is not None:
            fields["image_path"] = image_path

        if not fields:
            raise ValueError("No updates provided")

        assignments = ", ".join(f"{column} = ?" for column in fields)
        params = list(fields.values()) + [announcement_id]
        cursor = self._execute(
            f"UPDATE announcements SET {assignments} WHERE id = ?", params
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Announcement '{announcement_id}' not found")
        return self.get_announcement(announcement_id)

    def delete_announcement(self, announcement_id: int) -> Dict[str, Any]:
        """Delete an announcement."""
        announcement = self.get_announcement(announcement_id)
        cursor = self._execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Announcement '{announcement_id}' not found")
        return announcement

    # ------------------------------------------------------------------
    # Rules and Regulations CRUD operations
    # ------------------------------------------------------------------

    def add_rule(self, title: str, text: str) -> Dict[str, Any]:
        """Add a new rule or regulation."""
        cursor = self._execute(
            """
            INSERT INTO rules_and_regulations (title, text)
            VALUES (?, ?)
            """,
            (title, text),
        )
        rule_id = cursor.lastrowid
        return self.get_rule(rule_id)

    def get_rule(self, rule_id: int) -> Dict[str, Any]:
        """Get a single rule by ID."""
        cursor = self._execute("SELECT * FROM rules_and_regulations WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Rule with id '{rule_id}' not found")
        return dict(row)

    def list_rules(self) -> List[Dict[str, Any]]:
        """List all rules and regulations, most recent first."""
        cursor = self._execute("SELECT * FROM rules_and_regulations ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def update_rule(
        self, rule_id: int, title: Optional[str] = None, text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update a rule or regulation."""
        fields: Dict[str, Any] = {}
        if title:
            fields["title"] = title
        if text is not None:
            fields["text"] = text

        if not fields:
            raise ValueError("No updates provided")

        assignments = ", ".join(f"{column} = ?" for column in fields)
        params = list(fields.values()) + [rule_id]
        cursor = self._execute(
            f"UPDATE rules_and_regulations SET {assignments} WHERE id = ?", params
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Rule '{rule_id}' not found")
        return self.get_rule(rule_id)

    def delete_rule(self, rule_id: int) -> Dict[str, Any]:
        """Delete a rule or regulation."""
        rule = self.get_rule(rule_id)
        cursor = self._execute("DELETE FROM rules_and_regulations WHERE id = ?", (rule_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Rule '{rule_id}' not found")
        return rule


# ---------------------------------------------------------------------------
# Tool Registry & Resource Registry
# ---------------------------------------------------------------------------


class ToolExecutionError(Exception):
    """Custom error surfaced to the agent when tool execution fails."""


@dataclass
class ToolContext:
    requester_role: str
    admin_id: Optional[str] = None
    admin_password: Optional[str] = None


@dataclass
class ToolResult:
    name: str
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class AgentTool:
    name: str
    description: str
    schema: Dict[str, Any]
    handler: Callable[..., ToolResult]


class ToolTracer:
    """Simple in-memory tracer for debugging tool usage."""

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, tool_name: str, payload: Dict[str, Any], response: ToolResult) -> None:
        with self._lock:
            self._entries.append(
                {
                    "timestamp": time.time(),
                    "tool": tool_name,
                    "request": payload,
                    "response": {
                        "status": response.status,
                        "message": response.message,
                        "data": response.data,
                    },
                }
            )

    @property
    def entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._entries)


class ToolRegistry:
    def __init__(self, tracer: ToolTracer, db: MemberDatabase):
        self._tools: Dict[str, AgentTool] = {}
        self._tracer = tracer
        self._db = db

    def register(
        self, name: str, description: str, schema: Dict[str, Any]
    ) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
        def decorator(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
            self._tools[name] = AgentTool(
                name=name, description=description, schema=schema, handler=func
            )
            return func

        return decorator

    def get(self, name: str) -> AgentTool:
        return self._tools[name]

    @property
    def tools(self) -> Dict[str, AgentTool]:
        return dict(self._tools)

    # ------------------------------------------------------------------
    # Tool Implementations
    # ------------------------------------------------------------------

    def require_admin(self, context: ToolContext) -> None:
        if context.requester_role != "Admin":
            raise ToolExecutionError("Admin credentials required for this action")
        if not context.admin_id or not context.admin_password:
            raise ToolExecutionError("Admin ID and password must be supplied")
        try:
            authenticated = self._db.verify_admin(
                context.admin_id, context.admin_password
            )
        except ValueError as exc:
            raise ToolExecutionError(str(exc)) from exc
        if not authenticated:
            raise ToolExecutionError("Admin authentication failed")

    def add_builtin_tools(self) -> None:
        @self.register(
            name="add_member",
            description="Create a new member or admin with minimum payment amount validation.",
            schema={
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "name": {"type": "string"},
                    "amount": {"type": "number"},
                    "role": {"type": "string", "enum": ["Admin", "User"], "default": "User"},
                    "password": {"type": "string"},
                    "phone": {
                        "type": "string",
                        "description": "Pakistani mobile number formatted as +923XXXXXXXXX or 03XXXXXXXXX",
                    },
                },
                "required": ["member_id", "name", "amount"],
            },
        )
        def add_member(context: ToolContext, **payload: Any) -> ToolResult:
            self.require_admin(context)
            member = self._db.add_member(
                member_id=payload["member_id"],
                name=payload["name"],
                amount=float(payload["amount"]),
                role=payload.get("role", "User"),
                password=payload.get("password"),
                phone=payload.get("phone"),
            )
            result = ToolResult(
                name="add_member",
                status="success",
                message=f"Member {member['name']} created successfully.",
                data=member,
            )
            self._tracer.record("add_member", payload, result)
            return result

        @self.register(
            name="update_member",
            description="Update member details such as name, amount or payment status.",
            schema={
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "name": {"type": "string"},
                    "amount": {"type": "number"},
                    "payment_status": {"type": "string", "enum": ["Paid", "Unpaid"]},
                    "phone": {
                        "type": "string",
                        "description": "Pakistani mobile number formatted as +923XXXXXXXXX or 03XXXXXXXXX",
                    },
                },
                "required": ["member_id"],
            },
        )
        def update_member(context: ToolContext, **payload: Any) -> ToolResult:
            self.require_admin(context)
            member = self._db.update_member(
                member_id=payload["member_id"],
                name=payload.get("name"),
                amount=float(payload["amount"]) if payload.get("amount") is not None else None,
                payment_status=payload.get("payment_status"),
                phone=payload.get("phone"),
            )
            result = ToolResult(
                name="update_member",
                status="success",
                message=f"Member {member['name']} updated successfully.",
                data=member,
            )
            self._tracer.record("update_member", payload, result)
            return result

        @self.register(
            name="delete_member",
            description="Remove a member from the registry.",
            schema={
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                },
                "required": ["member_id"],
            },
        )
        def delete_member(context: ToolContext, **payload: Any) -> ToolResult:
            self.require_admin(context)
            member = self._db.delete_member(payload["member_id"])
            result = ToolResult(
                name="delete_member",
                status="success",
                message=f"Member {member['name']} deleted successfully.",
                data=member,
            )
            self._tracer.record("delete_member", payload, result)
            return result

        @self.register(
            name="mark_payment",
            description="Mark a member as Paid or Unpaid and optionally update the amount.",
            schema={
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "payment_status": {"type": "string", "enum": ["Paid", "Unpaid"]},
                    "amount": {"type": "number"},
                },
                "required": ["member_id", "payment_status"],
            },
        )
        def mark_payment(context: ToolContext, **payload: Any) -> ToolResult:
            self.require_admin(context)
            member = self._db.mark_payment(
                member_id=payload["member_id"],
                payment_status=payload["payment_status"],
                amount=float(payload["amount"]) if payload.get("amount") is not None else None,
            )
            result = ToolResult(
                name="mark_payment",
                status="success",
                message=f"Payment status for {member['name']} updated to {member['payment_status']}.",
                data=member,
            )
            self._tracer.record("mark_payment", payload, result)
            return result

        @self.register(
            name="list_members",
            description="List all members with their payment status and roles.",
            schema={"type": "object", "properties": {}},
        )
        def list_members(context: ToolContext, **payload: Any) -> ToolResult:
            members = self._db.list_members()
            result = ToolResult(
                name="list_members",
                status="success",
                message="Member registry fetched successfully.",
                data={"members": members},
            )
            self._tracer.record("list_members", payload, result)
            return result

        @self.register(
            name="change_admin_password",
            description="Update the password for a specific admin.",
            schema={
                "type": "object",
                "properties": {
                    "admin_id": {"type": "string"},
                    "new_password": {"type": "string"},
                },
                "required": ["admin_id", "new_password"],
            },
        )
        def change_admin_password(context: ToolContext, **payload: Any) -> ToolResult:
            self.require_admin(context)
            updated = self._db.change_admin_password(
                admin_id=payload["admin_id"],
                new_password=payload["new_password"],
            )
            result = ToolResult(
                name="change_admin_password",
                status="success",
                message=f"Password updated for admin {updated['member_id']}.",
                data={"admin": updated},
            )
            self._tracer.record("change_admin_password", payload, result)
            return result

        @self.register(
            name="authenticate_admin",
            description="Validate admin credentials before performing sensitive actions.",
            schema={
                "type": "object",
                "properties": {
                    "admin_id": {"type": "string"},
                    "password": {"type": "string"},
                },
                "required": ["admin_id", "password"],
            },
        )
        def authenticate_admin(context: ToolContext, **payload: Any) -> ToolResult:
            # This tool can be invoked by admins themselves to confirm authentication.
            is_valid = self._db.verify_admin(
                admin_id=payload["admin_id"], password=payload["password"]
            )
            result = ToolResult(
                name="authenticate_admin",
                status="success" if is_valid else "error",
                message="Admin authenticated successfully." if is_valid else "Invalid admin credentials.",
                data={"authenticated": is_valid},
            )
            self._tracer.record("authenticate_admin", payload, result)
            return result

        @self.register(
            name="search_web",
            description="Search the web for information using Tavily API. Useful for finding current information, facts, or answers to questions.",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query to look up"},
                    "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 5},
                },
                "required": ["query"],
            },
        )
        def search_web(context: ToolContext, **payload: Any) -> ToolResult:
            try:
                from tavily import TavilyClient
                
                api_key = os.getenv("TAVILY_API_KEY")
                if not api_key:
                    raise ToolExecutionError("TAVILY_API_KEY environment variable is not set. Please set it in your .env file.")
                
                client = TavilyClient(api_key=api_key)
                query = payload["query"]
                max_results = payload.get("max_results", 5)
                
                # Perform the search with basic answer included
                response = client.search(query=query, max_results=max_results, include_answer="basic")
                
                # Convert response to dict - Tavily returns a dict-like object
                # Use json.loads(json.dumps()) to ensure proper serialization
                if isinstance(response, dict):
                    response_data = response
                else:
                    # If it's an object, convert to dict via JSON serialization
                    response_str = json.dumps(response, default=str)
                    response_data = json.loads(response_str)
                
                num_results = len(response_data.get("results", []))
                answer = response_data.get("answer", "")
                
                message = f"Found {num_results} results for query: {query}"
                if answer:
                    message += f". Summary: {answer[:200]}..."
                
                result = ToolResult(
                    name="search_web",
                    status="success",
                    message=message,
                    data=response_data,
                )
                self._tracer.record("search_web", payload, result)
                return result
            except ImportError:
                raise ToolExecutionError("tavily-python package is not installed. Please install it with: pip install tavily-python")
            except Exception as exc:
                raise ToolExecutionError(f"Search failed: {str(exc)}")


@dataclass
class Resource:
    name: str
    description: str
    fetcher: Callable[[], Dict[str, Any]]


class ResourceRegistry:
    def __init__(self):
        self._resources: Dict[str, Resource] = {}

    def register(
        self, name: str, description: str
    ) -> Callable[[Callable[[], Dict[str, Any]]], Callable[[], Dict[str, Any]]]:
        def decorator(func: Callable[[], Dict[str, Any]]) -> Callable[[], Dict[str, Any]]:
            self._resources[name] = Resource(name=name, description=description, fetcher=func)
            return func

        return decorator

    def snapshot(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for name, resource in self._resources.items():
            try:
                payload[name] = resource.fetcher()
            except Exception as exc:  # pragma: no cover - defensive
                payload[name] = {"error": str(exc)}
        return payload

    @property
    def resources(self) -> Dict[str, Resource]:
        return dict(self._resources)


def build_tooling(db_path: str | os.PathLike[str]) -> Dict[str, Any]:
    """Factory to assemble database, tools, resources, and tracer."""

    db = MemberDatabase(db_path)
    db.ensure_default_admin()
    tracer = ToolTracer()
    tool_registry = ToolRegistry(tracer=tracer, db=db)
    tool_registry.add_builtin_tools()

    resources = ResourceRegistry()

    @resources.register(
        name="member_overview",
        description="Current snapshot of members including counts of paid/unpaid.",
    )
    def member_overview() -> Dict[str, Any]:
        members = db.list_members()
        paid = [m for m in members if m["payment_status"] == "Paid"]
        unpaid = [m for m in members if m["payment_status"] == "Unpaid"]
        return {
            "totals": {
                "members": len(members),
                "paid": len(paid),
                "unpaid": len(unpaid),
                "total_collected": sum(m["amount"] for m in paid),
            },
            "recent_members": members[-5:],
        }

    @resources.register(
        name="policy_reference",
        description="Operational guidelines for admin and user capabilities.",
    )
    def policy_reference() -> Dict[str, Any]:
        return {
            "admin_actions": [
                "Add, update, or delete members",
                "Mark payments and change payment amounts",
                "Change admin passwords",
                "Authenticate administrators",
            ],
            "user_actions": [
                "View all members",
                "Filter paid vs unpaid members",
            ],
            "constraints": [
                "Minimum payment is 250",
                "Password required for every admin operation",
                "Members default to 'Unpaid' when created",
            ],
        }

    return {
        "db": db,
        "tools": tool_registry,
        "resources": resources,
        "tracer": tracer,
    }
