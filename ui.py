"""FastAPI UI for SHAHENSHA GROUP' ACCOUNTANT."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
import re
from typing import Any, Dict, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, validator

from agent import GeminiAgentWrapper
from tools import MemberDatabase, ToolTracer


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    role: str = Field(..., pattern=r"^(Admin|User)$")
    admin_id: str | None = None
    admin_password: str | None = None

    @validator("admin_id", "admin_password", pre=True, always=True)
    def trim_strings(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class AdminLoginRequest(BaseModel):
    admin_id: str = Field(..., min_length=1)
    admin_password: str = Field(..., min_length=1)

    @validator("admin_id", "admin_password", pre=True, always=True)
    def _trim_and_validate(cls, value: str | None) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be empty")
        return stripped


class AdminCredentials(BaseModel):
    admin_id: str = Field(..., min_length=1)
    admin_password: str = Field(..., min_length=1)

    @validator("admin_id", "admin_password", pre=True, always=True)
    def _trim(cls, value: str | None) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be empty")
        return stripped


class AddMemberRequest(AdminCredentials):
    member_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    role: Literal["Admin", "User"] = "User"
    password: str | None = None
    phone: str | None = None

    @validator("amount")
    def _validate_amount(cls, value: float) -> float:
        if value < 250:
            raise ValueError("Minimum payment is ₨250")
        return value

    @validator("password", pre=True, always=True)
    def _trim_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @validator("phone", pre=True, always=True)
    def _validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        pattern = r"^(\+92|0)3\d{9}$"
        if not re.match(pattern, stripped):
            raise ValueError("Phone must be a valid Pakistani mobile number")
        return stripped


class DeleteMemberRequest(AdminCredentials):
    member_id: str = Field(..., min_length=1)


class UpdateMemberRequest(AdminCredentials):
    member_id: str = Field(..., min_length=1)
    name: str | None = None
    amount: float | None = Field(default=None, gt=0)
    phone: str | None = None

    @validator("phone", pre=True, always=True)
    def _validate_update_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        pattern = r"^(\+92|0)3\d{9}$"
        if not re.match(pattern, stripped):
            raise ValueError("Phone must be a valid Pakistani mobile number")
        return stripped


class MarkPaymentRequest(AdminCredentials):
    member_id: str = Field(..., min_length=1)
    payment_status: Literal["Paid", "Unpaid"]
    amount: float | None = Field(default=None, gt=0)

    @validator("amount")
    def _validate_optional_amount(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 250:
            raise ValueError("Minimum payment is ₨250")
        return value


class ChangeAdminPasswordRequest(AdminCredentials):
    target_admin_id: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=1)

    @validator("target_admin_id", "new_password", pre=True, always=True)
    def _trim_values(cls, value: str | None) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be empty")
        return stripped


class AddAnnouncementRequest(AdminCredentials):
    title: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    image_path: str | None = None


class UpdateAnnouncementRequest(AdminCredentials):
    announcement_id: int
    title: str | None = None
    text: str | None = None
    image_path: str | None = None


class DeleteAnnouncementRequest(AdminCredentials):
    announcement_id: int


class AddRuleRequest(AdminCredentials):
    title: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class UpdateRuleRequest(AdminCredentials):
    rule_id: int
    title: str | None = None
    text: str | None = None


class DeleteRuleRequest(AdminCredentials):
    rule_id: int


def create_app(agent_bundle: Dict[str, Any]) -> FastAPI:
    agent: GeminiAgentWrapper = agent_bundle["agent"]
    db: MemberDatabase = agent_bundle["db"]
    tracer: ToolTracer = agent_bundle["tracer"]

    app = FastAPI(title="SHAHENSHA GROUP' ACCOUNTANT", version="1.0.0")
    
    # Setup uploads directory for announcement images
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
    
    # Setup static files
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Setup templates
    templates = Jinja2Templates(directory="templates")

    def get_agent() -> GeminiAgentWrapper:
        return agent

    def get_db() -> MemberDatabase:
        return db

    def get_tracer() -> ToolTracer:
        return tracer

    def _require_admin(
        db_service: MemberDatabase, admin_id: str, admin_password: str
    ) -> None:
        try:
            authenticated = db_service.verify_admin(admin_id, admin_password)
            if not authenticated:
                raise HTTPException(status_code=401, detail="Invalid admin credentials")
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except ValueError as exc:
            # ValueError from verify_admin means admin not found or no password set
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:
            # Catch any other unexpected errors (database errors, etc.)
            raise HTTPException(status_code=500, detail=f"Authentication error: {str(exc)}") from exc

    @app.on_event("startup")
    async def startup_event():
        async def run_payment_reset_loop():
            while True:
                try:
                    # Run the synchronous db operation in a thread pool
                    count = await asyncio.to_thread(db.check_and_reset_monthly_payments)
                    if count > 0:
                        print(f"INFO: Monthly payment reset executed. Reset {count} members.")
                except Exception as e:
                    print(f"ERROR: Failed to run monthly payment reset: {e}")
                
                # Check every hour (3600 seconds) to ensure we catch the 28th promptly
                await asyncio.sleep(3600)

        # Start the background task
        asyncio.create_task(run_payment_reset_loop())

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("index.html", {"request": request})

    @app.post("/api/chat")
    async def chat(
        payload: ChatRequest,
        agent_service: GeminiAgentWrapper = Depends(get_agent),
    ) -> JSONResponse:
        try:
            # Handle both async and sync handle_request methods
            if asyncio.iscoroutinefunction(agent_service.handle_request):
                result = await agent_service.handle_request(
                    message=payload.message,
                    requester_role=payload.role,
                    admin_id=payload.admin_id,
                    admin_password=payload.admin_password,
                )
            else:
                result = agent_service.handle_request(
                    message=payload.message,
                    requester_role=payload.role,
                    admin_id=payload.admin_id,
                    admin_password=payload.admin_password,
                )
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return JSONResponse(result)

    @app.post("/api/admin/login")
    async def admin_login(
        payload: AdminLoginRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        try:
            _require_admin(db_service, payload.admin_id, payload.admin_password)
            return JSONResponse({"status": "success", "authenticated": True, "message": "Admin authenticated successfully."})
        except HTTPException:
            # Re-raise HTTP exceptions (like 401) as-is
            raise
        except Exception as exc:
            # Catch any other exceptions and return a proper error response
            raise HTTPException(status_code=401, detail=f"Authentication failed: {str(exc)}") from exc

    @app.post("/api/admin/members")
    async def admin_add_member(
        payload: AddMemberRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            member = db_service.add_member(
                member_id=payload.member_id,
                name=payload.name,
                amount=payload.amount,
                role=payload.role,
                password=payload.password,
                phone=payload.phone,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "member": member, "message": "Member created successfully."}
        )

    @app.post("/api/admin/members/update")
    async def admin_update_member(
        payload: UpdateMemberRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            member = db_service.update_member(
                member_id=payload.member_id,
                name=payload.name,
                amount=payload.amount,
                phone=payload.phone,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "member": member, "message": "Member updated successfully."}
        )

    @app.post("/api/admin/members/delete")
    async def admin_delete_member(
        payload: DeleteMemberRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            member = db_service.delete_member(payload.member_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "member": member, "message": "Member deleted successfully."}
        )

    @app.post("/api/admin/members/mark")
    async def admin_mark_payment(
        payload: MarkPaymentRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            member = db_service.mark_payment(
                member_id=payload.member_id,
                payment_status=payload.payment_status,
                amount=payload.amount,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {
                "status": "success",
                "member": member,
                "message": f"Payment status updated to {payload.payment_status}.",
            }
        )

    @app.post("/api/admin/password")
    async def admin_change_password(
        payload: ChangeAdminPasswordRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            updated = db_service.change_admin_password(
                admin_id=payload.target_admin_id,
                new_password=payload.new_password,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {
                "status": "success",
                "admin": updated,
                "message": "Password updated successfully.",
            }
        )

    @app.get("/api/members")
    async def members(db_service: MemberDatabase = Depends(get_db)) -> JSONResponse:
        members = db_service.list_members()
        return JSONResponse({"members": members})

    @app.get("/api/traces")
    async def traces(tracer_service: ToolTracer = Depends(get_tracer)) -> JSONResponse:
        return JSONResponse({"traces": tracer_service.entries})

    @app.get("/api/memory")
    async def memory(agent_service: GeminiAgentWrapper = Depends(get_agent)) -> JSONResponse:
        return JSONResponse({"memory": agent_service.memory.serialize()})

    @app.get("/api/announcements")
    async def get_announcements(db_service: MemberDatabase = Depends(get_db)) -> JSONResponse:
        announcements = db_service.list_announcements()
        return JSONResponse({"announcements": announcements})

    @app.post("/api/admin/announcements/upload")
    async def upload_announcement_image(
        file: UploadFile = File(...),
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Generate unique filename
        file_extension = Path(file.filename).suffix if file.filename else ".jpg"
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = uploads_dir / unique_filename
        
        # Save file
        try:
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(exc)}") from exc
        
        return JSONResponse({
            "status": "success",
            "image_path": f"/uploads/{unique_filename}",
            "message": "Image uploaded successfully."
        })

    @app.post("/api/admin/announcements")
    async def admin_add_announcement(
        payload: AddAnnouncementRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            announcement = db_service.add_announcement(
                title=payload.title,
                text=payload.text,
                image_path=payload.image_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "announcement": announcement, "message": "Announcement created successfully."}
        )

    @app.post("/api/admin/announcements/update")
    async def admin_update_announcement(
        payload: UpdateAnnouncementRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            announcement = db_service.update_announcement(
                announcement_id=payload.announcement_id,
                title=payload.title,
                text=payload.text,
                image_path=payload.image_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "announcement": announcement, "message": "Announcement updated successfully."}
        )

    @app.post("/api/admin/announcements/delete")
    async def admin_delete_announcement(
        payload: DeleteAnnouncementRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            announcement = db_service.delete_announcement(payload.announcement_id)
            # Delete associated image file if exists
            if announcement.get("image_path"):
                # Extract filename from path like "/uploads/filename.jpg"
                image_path_str = announcement["image_path"]
                if image_path_str.startswith("/uploads/"):
                    filename = image_path_str.replace("/uploads/", "")
                    image_path = uploads_dir / filename
                    if image_path.exists():
                        try:
                            image_path.unlink()
                        except Exception:
                            pass  # Ignore file deletion errors
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "announcement": announcement, "message": "Announcement deleted successfully."}
        )

    @app.get("/api/rules")
    async def get_rules(db_service: MemberDatabase = Depends(get_db)) -> JSONResponse:
        rules = db_service.list_rules()
        return JSONResponse({"rules": rules})

    @app.post("/api/admin/rules")
    async def admin_add_rule(
        payload: AddRuleRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            rule = db_service.add_rule(
                title=payload.title,
                text=payload.text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "rule": rule, "message": "Rule created successfully."}
        )

    @app.post("/api/admin/rules/update")
    async def admin_update_rule(
        payload: UpdateRuleRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            rule = db_service.update_rule(
                rule_id=payload.rule_id,
                title=payload.title,
                text=payload.text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "rule": rule, "message": "Rule updated successfully."}
        )

    @app.post("/api/admin/rules/delete")
    async def admin_delete_rule(
        payload: DeleteRuleRequest,
        db_service: MemberDatabase = Depends(get_db),
    ) -> JSONResponse:
        _require_admin(db_service, payload.admin_id, payload.admin_password)
        try:
            rule = db_service.delete_rule(payload.rule_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "rule": rule, "message": "Rule deleted successfully."}
        )

    return app
