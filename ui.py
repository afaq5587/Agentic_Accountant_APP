"""FastAPI UI for SHAHENSHA GROUP' ACCOUNTANT."""

from __future__ import annotations

from typing import Any, Dict, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, validator

from agent import GeminiAgent
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

    @validator("amount")
    def _validate_amount(cls, value: float) -> float:
        if value < 250:
            raise ValueError("Minimum payment is 250")
        return value

    @validator("password", pre=True, always=True)
    def _trim_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class DeleteMemberRequest(AdminCredentials):
    member_id: str = Field(..., min_length=1)


class MarkPaymentRequest(AdminCredentials):
    member_id: str = Field(..., min_length=1)
    payment_status: Literal["Paid", "Unpaid"]
    amount: float | None = Field(default=None, gt=0)

    @validator("amount")
    def _validate_optional_amount(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 250:
            raise ValueError("Minimum payment is 250")
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


def create_app(agent_bundle: Dict[str, Any]) -> FastAPI:
    agent: GeminiAgent = agent_bundle["agent"]
    db: MemberDatabase = agent_bundle["db"]
    tracer: ToolTracer = agent_bundle["tracer"]

    app = FastAPI(title="SHAHENSHA GROUP' ACCOUNTANT", version="1.0.0")

    def get_agent() -> GeminiAgent:
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
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if not authenticated:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:  # noqa: ARG001
        return HTMLResponse(_render_dashboard())

    @app.post("/api/chat")
    async def chat(
        payload: ChatRequest,
        agent_service: GeminiAgent = Depends(get_agent),
    ) -> JSONResponse:
        try:
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
        _require_admin(db_service, payload.admin_id, payload.admin_password)

        return JSONResponse({"status": "success", "authenticated": True, "message": "Admin authenticated successfully."})

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
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {"status": "success", "member": member, "message": "Member created successfully."}
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
    async def memory(agent_service: GeminiAgent = Depends(get_agent)) -> JSONResponse:
        return JSONResponse({"memory": agent_service.memory.serialize()})

    return app


def _render_dashboard() -> str:
    """Return a Tailwind-based responsive dashboard page."""

    logo = "&#x1F451;&#x20B9;"

    return f"""<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>SHAHENSHA GROUP' ACCOUNTANT</title>
    <script src=\"https://cdn.tailwindcss.com\"></script>
    <style>
      :root {{
        color-scheme: dark;
      }}
      body {{ background: #050b1f; color: #f5f8ff; font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; }}
      .glass {{ background: rgba(15, 22, 55, 0.78); backdrop-filter: blur(16px); border: 1px solid rgba(116, 134, 196, 0.35); }}
      .gold {{ color: #f6c65d; }}
      .gold-bg {{ background: linear-gradient(135deg, #f7d479, #c6872f); }}
      .button-primary {{ background: linear-gradient(135deg, #3558ff, #2a9dff); transition: transform 150ms ease, box-shadow 150ms ease; }}
      .button-primary:hover {{ transform: translateY(-2px); box-shadow: 0 12px 24px rgba(33, 111, 255, 0.35); }}
      .button-outline {{ border: 1px solid rgba(246, 198, 93, 0.6); color: #f6c65d; }}
      .sidebar {{ background: radial-gradient(circle at top, rgba(12, 22, 58, 0.95), rgba(4, 8, 21, 0.95)); border-right: 1px solid rgba(37, 55, 120, 0.5); }}
      .card {{ transition: transform 150ms ease, box-shadow 150ms ease; }}
      .card:hover {{ transform: translateY(-4px); box-shadow: 0 18px 40px rgba(5, 10, 30, 0.55); }}
      .status-paid {{ color: #4ade80; }}
      .status-unpaid {{ color: #f87171; }}
      .badge {{ background: rgba(246, 198, 93, 0.08); border: 1px solid rgba(246, 198, 93, 0.3); }}
      .hidden {{ display: none !important; }}
    </style>
  </head>
  <body class=\"min-h-screen flex flex-col\">
    <div id=\"login-screen\" class=\"fixed inset-0 flex items-center justify-center bg-black/75 z-40\">
      <div class=\"glass rounded-3xl p-10 w-full max-w-2xl shadow-2xl\">
        <div class=\"flex items-center gap-4 mb-6\">
          <div class=\"text-5xl gold\">{logo}</div>
          <div>
            <h1 class=\"text-3xl font-semibold gold\">SHAHENSHA GROUP' ACCOUNTANT</h1>
            <p class=\"text-blue-200 text-sm mt-1\">Select your access to continue</p>
          </div>
        </div>
        <div class=\"grid grid-cols-1 md:grid-cols-2 gap-6\">
          <button id=\"login-user\" class=\"glass rounded-2xl p-6 text-left hover:border-blue-400 transition border border-transparent\">
            <h2 class=\"text-xl font-semibold text-blue-100\">User Access</h2>
            <p class=\"text-sm text-blue-300 mt-2\">View payment summaries and member status with read-only access.</p>
            <div class=\"mt-6\">
              <span class=\"badge px-4 py-1 rounded-full text-xs uppercase tracking-wide\">No password required</span>
            </div>
          </button>
          <div class=\"glass rounded-2xl p-6 border border-transparent hover:border-blue-400 transition\">
            <h2 class=\"text-xl font-semibold text-blue-100\">Admin Login</h2>
            <p class=\"text-sm text-blue-300 mt-2\">Manage members, update payments, and track finances securely.</p>
            <form id=\"admin-login-form\" class=\"mt-5 space-y-4\">
              <div>
                <label class=\"block text-sm text-blue-200 mb-1\">Admin ID</label>
                <input id=\"admin-login-id\" type=\"text\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" placeholder=\"admin\" required />
              </div>
              <div>
                <label class=\"block text-sm text-blue-200 mb-1\">Password</label>
                <input id=\"admin-login-password\" type=\"password\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" placeholder=\"********\" required />
              </div>
              <button class=\"button-primary w-full rounded-xl py-3 font-semibold text-white\" type=\"submit\">Unlock Admin Dashboard</button>
            </form>
          </div>
        </div>
        <p class=\"text-xs text-center text-blue-300 mt-6\">Hint: default admin password is <span class=\"gold\">admin@250</span></p>
      </div>
    </div>

    <div class=\"flex-1 flex min-h-screen\">
      <aside class=\"sidebar w-64 hidden lg:flex flex-col p-6 space-y-2\" id=\"sidebar\">
        <div class=\"flex items-center gap-3 mb-6\">
          <div class=\"text-4xl gold\">{logo}</div>
          <div>
            <p class=\"text-xs text-blue-300 uppercase tracking-widest\">Welcome</p>
            <h2 class=\"text-lg font-semibold gold\">SHAHENSHA GROUP</h2>
          </div>
        </div>
        <nav class=\"flex-1 space-y-1 text-sm\">
          <button class=\"nav-item w-full text-left px-4 py-3 rounded-xl hover:bg-white/5 transition flex items-center justify-between\" data-section=\"dashboard\">
            <span>Dashboard</span>
            <span class=\"text-xs text-blue-400\">Summary</span>
          </button>
          <button class=\"nav-item w-full text-left px-4 py-3 rounded-xl hover:bg-white/5 transition flex items-center justify-between\" data-section=\"members\">
            <span>Members</span>
            <span class=\"text-xs text-blue-400\">Directory</span>
          </button>
          <button class=\"nav-item w-full text-left px-4 py-3 rounded-xl hover:bg-white/5 transition flex items-center justify-between\" data-section=\"payments\">
            <span>Payments</span>
            <span class=\"text-xs text-blue-400\">Status</span>
          </button>
          <button class=\"nav-item w-full text-left px-4 py-3 rounded-xl hover:bg-white/5 transition flex items-center justify-between\" data-section=\"settings\">
            <span>Settings</span>
            <span class=\"text-xs text-blue-400\">Access</span>
          </button>
        </nav>
        <button id=\"logout\" class=\"button-outline rounded-xl py-3 text-sm font-semibold hover:bg-white/5 transition\">Sign Out</button>
      </aside>

      <div class=\"flex-1 flex flex-col\">
        <header class=\"glass px-6 md:px-10 py-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4\">
          <div>
            <h1 class=\"text-3xl font-semibold gold\">SHAHENSHA GROUP' ACCOUNTANT</h1>
            <p class=\"text-sm text-blue-200\">Real-time insights powered by Gemini intelligence</p>
          </div>
          <div class=\"flex items-center gap-3\">
            <div class=\"badge px-4 py-2 rounded-full text-xs uppercase tracking-widest\" id=\"role-badge\">Guest</div>
            <div class=\"text-xs text-blue-300\">
              <p>Live status updates</p>
              <p>Minimum payment: ₹250</p>
            </div>
          </div>
        </header>

        <main class=\"flex-1 overflow-y-auto p-6 md:p-10 space-y-8\">
          <section id=\"alerts\" class=\"space-y-3\"></section>

          <section id=\"dashboard-section\" class=\"space-y-6\">
            <div class=\"grid grid-cols-1 md:grid-cols-3 gap-6\">
              <div class=\"glass card rounded-3xl p-6\">
                <p class=\"text-sm text-blue-200\">Total Members</p>
                <h2 class=\"text-3xl font-semibold mt-3\" id=\"metric-members\">0</h2>
              </div>
              <div class=\"glass card rounded-3xl p-6\">
                <p class=\"text-sm text-blue-200\">Paid Members</p>
                <h2 class=\"text-3xl font-semibold mt-3 status-paid\" id=\"metric-paid\">0</h2>
              </div>
              <div class=\"glass card rounded-3xl p-6\">
                <p class=\"text-sm text-blue-200\">Pending Payments</p>
                <h2 class=\"text-3xl font-semibold mt-3 status-unpaid\" id=\"metric-unpaid\">0</h2>
              </div>
            </div>

            <div class=\"glass rounded-3xl p-6 space-y-4\">
              <div class=\"flex flex-col md:flex-row md:items-center md:justify-between gap-4\">
                <h2 class=\"text-xl font-semibold gold\">Member Ledger</h2>
                <div class=\"flex flex-wrap gap-2\">
                  <button class=\"button-outline rounded-xl px-4 py-2 text-xs uppercase tracking-wide\" data-filter=\"all\">All</button>
                  <button class=\"button-outline rounded-xl px-4 py-2 text-xs uppercase tracking-wide\" data-filter=\"Paid\">Paid</button>
                  <button class=\"button-outline rounded-xl px-4 py-2 text-xs uppercase tracking-wide\" data-filter=\"Unpaid\">Unpaid</button>
                </div>
                <button id=\"open-add-member\" class=\"button-primary rounded-xl px-4 py-2 text-sm font-semibold hidden\">Add Member</button>
              </div>
              <div id=\"members-grid\" class=\"grid gap-4 sm:grid-cols-2 xl:grid-cols-3\"></div>
            </div>
          </section>

          <section id=\"members-section\" class=\"space-y-4 hidden\">
            <div class=\"glass rounded-3xl p-6\">
              <h2 class=\"text-2xl font-semibold gold mb-4\">Full Member Directory</h2>
              <div id=\"members-table\" class=\"overflow-x-auto\"></div>
            </div>
          </section>

          <section id=\"payments-section\" class=\"space-y-4 hidden\">
            <div class=\"glass rounded-3xl p-6\">
              <h2 class=\"text-2xl font-semibold gold mb-4\">Payment Insights</h2>
              <div id=\"payment-summary\" class=\"text-sm text-blue-200\"></div>
            </div>
          </section>

          <section id=\"settings-section\" class=\"space-y-4 hidden\">
            <div class=\"glass rounded-3xl p-6\">
              <h2 class=\"text-2xl font-semibold gold mb-4\">Admin Settings</h2>
              <form id=\"password-change-form\" class=\"space-y-4 hidden\">
                <div class=\"grid grid-cols-1 md:grid-cols-3 gap-4\">
                  <div>
                    <label class=\"block text-sm text-blue-200 mb-1\">Admin ID</label>
                    <input id=\"settings-admin-id\" type=\"text\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" required />
                  </div>
                  <div>
                    <label class=\"block text-sm text-blue-200 mb-1\">New Password</label>
                    <input id=\"settings-new-password\" type=\"password\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" required />
                  </div>
                  <div class=\"flex items-end\">
                    <button class=\"button-primary rounded-xl px-4 py-3 font-semibold text-white w-full\" type=\"submit\">Change Password</button>
                  </div>
                </div>
              </form>
              <p id=\"settings-locked\" class=\"text-blue-300 text-sm\">Login as admin to access settings.</p>
            </div>
          </section>
        </main>

        <footer class=\"px-6 md:px-10 py-6 text-xs text-blue-300 border-t border-white/5\">
          © 2025 SHAHENSHA GROUP
        </footer>
      </div>
    </div>

    <div id=\"add-member-modal\" class=\"fixed inset-0 bg-black/70 hidden items-center justify-center z-30\">
      <div class=\"glass rounded-3xl p-8 w-full max-w-xl space-y-4\">
        <div class=\"flex items-center justify-between\">
          <h3 class=\"text-2xl font-semibold gold\">Add Member</h3>
          <button id=\"close-add-member\" class=\"text-blue-200 text-sm uppercase tracking-wide\">Close</button>
        </div>
        <form id=\"add-member-form\" class=\"space-y-4\">
          <div class=\"grid grid-cols-1 md:grid-cols-2 gap-4\">
            <div>
              <label class=\"block text-sm text-blue-200 mb-1\">Member ID</label>
              <input id=\"add-member-id\" type=\"text\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" required />
            </div>
            <div>
              <label class=\"block text-sm text-blue-200 mb-1\">Name</label>
              <input id=\"add-member-name\" type=\"text\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" required />
            </div>
          </div>
          <div class=\"grid grid-cols-1 md:grid-cols-2 gap-4\">
            <div>
              <label class=\"block text-sm text-blue-200 mb-1\">Amount (₹)</label>
              <input id=\"add-member-amount\" type=\"number\" min=\"250\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" required />
            </div>
            <div>
              <label class=\"block text-sm text-blue-200 mb-1\">Role</label>
              <select id=\"add-member-role\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\">
                <option value=\"User\">User</option>
                <option value=\"Admin\">Admin</option>
              </select>
            </div>
          </div>
          <div id=\"add-member-password\" class=\"hidden\">
            <label class=\"block text-sm text-blue-200 mb-1\">Admin Password</label>
            <input id=\"add-member-admin-password\" type=\"password\" class=\"w-full glass rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-white\" placeholder=\"Required for admin role\" />
          </div>
          <button class=\"button-primary rounded-xl px-4 py-3 font-semibold text-white w-full\" type=\"submit\">Create Member</button>
        </form>
      </div>
    </div>

    <script>
      const state = {{
        role: null,
        adminId: null,
        adminPassword: null,
        members: [],
        filter: 'all'
      }};

      const loginScreen = document.getElementById('login-screen');
      const loginUserBtn = document.getElementById('login-user');
      const adminLoginForm = document.getElementById('admin-login-form');
      const logoutBtn = document.getElementById('logout');
      const roleBadge = document.getElementById('role-badge');
      const alerts = document.getElementById('alerts');
      const membersGrid = document.getElementById('members-grid');
      const membersTable = document.getElementById('members-table');
      const paymentSummary = document.getElementById('payment-summary');
      const addMemberModal = document.getElementById('add-member-modal');
      const openAddMemberBtn = document.getElementById('open-add-member');
      const closeAddMemberBtn = document.getElementById('close-add-member');
      const addMemberForm = document.getElementById('add-member-form');
      const addMemberRole = document.getElementById('add-member-role');
      const addMemberPasswordWrapper = document.getElementById('add-member-password');
      const settingsLocked = document.getElementById('settings-locked');
      const passwordChangeForm = document.getElementById('password-change-form');

      const metricMembers = document.getElementById('metric-members');
      const metricPaid = document.getElementById('metric-paid');
      const metricUnpaid = document.getElementById('metric-unpaid');

      document.querySelectorAll('.nav-item').forEach((button) => {{
        button.addEventListener('click', () => {{
          const section = button.getAttribute('data-section');
          document.querySelectorAll('main section[id$="-section"]').forEach((sec) => {{
            sec.classList.add('hidden');
          }});
          document.getElementById(`${{section}}-section`).classList.remove('hidden');
        }});
      }});

      function showAlert(type, message) {{
        const alert = document.createElement('div');
        const palette = {{
          success: 'border-green-400/70 bg-green-500/10 text-green-200',
          error: 'border-rose-400/70 bg-rose-500/10 text-rose-200',
          info: 'border-blue-400/70 bg-blue-500/10 text-blue-200'
        }};
        alert.className = `glass border rounded-2xl px-5 py-4 text-sm transition ${{palette[type] || palette.info}}`;
        alert.innerHTML = `<div class="flex justify-between items-start"><span>${{message}}</span><button class="text-xs uppercase tracking-wide">Dismiss</button></div>`;
        alert.querySelector('button').addEventListener('click', () => alert.remove());
        alerts.prepend(alert);
        setTimeout(() => alert.remove(), 6000);
      }}

      async function callAgent(message, options = {{}}) {{
        const payload = {{
          message,
          role: options.role || state.role || 'User',
          admin_id: options.adminId || state.adminId,
          admin_password: options.adminPassword || state.adminPassword
        }};

        const res = await fetch('/api/chat', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});

        if (!res.ok) {{
          const detail = await res.json().catch(() => ({{ detail: 'Unknown error' }}));
          throw new Error(detail.detail || 'Agent request failed');
        }}

        return res.json();
      }}

      async function refreshMembers() {{
        const res = await fetch('/api/members');
        const data = await res.json();
        state.members = data.members || [];
        renderMembers();
        renderMetrics();
        renderDirectoryTable();
        renderPaymentSummary();
      }}

      function renderMembers() {{
        const filtered = state.members.filter((member) => {{
          if (state.filter === 'all') return true;
          return member.payment_status === state.filter;
        }});

        if (filtered.length === 0) {{
          membersGrid.innerHTML = '<div class="text-sm text-blue-300">No members match the current filters.</div>';
          return;
        }}

        membersGrid.innerHTML = filtered.map((member) => {{
          const statusClass = member.payment_status === 'Paid' ? 'status-paid' : 'status-unpaid';
          const adminActions = state.role === 'Admin' ? `
            <div class="flex gap-2 pt-4">
              <button class="button-outline rounded-xl px-3 py-2 text-xs" data-action="delete" data-member="${{member.member_id}}">Delete</button>
              <button class="button-primary rounded-xl px-3 py-2 text-xs" data-action="mark" data-status="Paid" data-member="${{member.member_id}}">Mark Paid</button>
              <button class="button-primary rounded-xl px-3 py-2 text-xs" data-action="mark" data-status="Unpaid" data-member="${{member.member_id}}">Mark Unpaid</button>
            </div>
          ` : '';
          return `
            <article class="glass card rounded-3xl p-5" data-member-card="${{member.member_id}}">
              <div class="flex items-center justify-between">
                <h3 class="text-lg font-semibold">${{member.name}}</h3>
                <span class="badge px-3 py-1 rounded-full text-xs">${{member.role}}</span>
              </div>
              <p class="mt-2 text-sm text-blue-200">ID: ${{member.member_id}}</p>
              <p class="mt-3 text-2xl font-semibold">₹${{member.amount}}</p>
              <p class="${{statusClass}} text-sm mt-1">${{member.payment_status}}</p>
              ${{adminActions}}
            </article>
          `;
        }}).join('');

        if (state.role === 'Admin') {{
          membersGrid.querySelectorAll('button[data-action]').forEach((button) => {{
            button.addEventListener('click', handleMemberCardAction);
          }});
        }}
      }}

      function renderMetrics() {{
        const total = state.members.length;
        const paid = state.members.filter((m) => m.payment_status === 'Paid').length;
        const unpaid = total - paid;
        metricMembers.textContent = total;
        metricPaid.textContent = paid;
        metricUnpaid.textContent = unpaid;
      }}

      function renderDirectoryTable() {{
        if (state.members.length === 0) {{
          membersTable.innerHTML = '<p class="text-sm text-blue-300">No members yet.</p>';
          return;
        }}
        membersTable.innerHTML = `
          <table class="w-full text-left text-sm">
            <thead class="text-blue-200 uppercase tracking-wide text-xs">
              <tr>
                <th class="py-3">Member</th>
                <th class="py-3">Role</th>
                <th class="py-3">Amount</th>
                <th class="py-3">Payment Status</th>
              </tr>
            </thead>
            <tbody class="text-blue-100 divide-y divide-white/5">
              ${{state.members.map((member) => `
                <tr>
                  <td class="py-3">
                    <div class="font-semibold">${{member.name}}</div>
                    <div class="text-xs text-blue-300">${{member.member_id}}</div>
                  </td>
                  <td class="py-3">${{member.role}}</td>
                  <td class="py-3">₹${{member.amount}}</td>
                  <td class="py-3">${{member.payment_status}}</td>
                </tr>
              `).join('')}}
            </tbody>
          </table>
        `;
      }}

      function renderPaymentSummary() {{
        if (state.members.length === 0) {{
          paymentSummary.innerHTML = '<p>No payment data yet.</p>';
          return;
        }}
        const paidMembers = state.members.filter((m) => m.payment_status === 'Paid');
        const unpaidMembers = state.members.filter((m) => m.payment_status === 'Unpaid');
        const totalCollected = paidMembers.reduce((acc, m) => acc + Number(m.amount || 0), 0);
        paymentSummary.innerHTML = `
          <div class="space-y-2">
            <p>Total collected: <span class="status-paid font-semibold">₹${{totalCollected}}</span></p>
            <p>Paid members: ${{paidMembers.length}}</p>
            <p>Pending payments: ${{unpaidMembers.length}}</p>
          </div>
        `;
      }}

      async function adminPost(path, payload = {{}}) {{
        if (state.role !== 'Admin' || !state.adminId || !state.adminPassword) {{
          throw new Error('Admin privileges required');
        }}
        const response = await fetch(path, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            admin_id: state.adminId,
            admin_password: state.adminPassword,
            ...payload,
          }}),
        }});
        const data = await response.json().catch(() => ({{}}));
        if (!response.ok || data.status === 'error') {{
          const detail = data.detail || data.message || 'Action failed';
          throw new Error(detail);
        }}
        return data;
      }}

      async function handleMemberCardAction(event) {{
        const button = event.currentTarget;
        const action = button.getAttribute('data-action');
        const memberId = button.getAttribute('data-member');

        if (!memberId) return;

        try {{
          if (action === 'delete') {{
            const result = await adminPost('/api/admin/members/delete', {{ member_id: memberId }});
            showAlert('success', result.message || `Member ${{memberId}} deleted.`);
          }} else if (action === 'mark') {{
            const status = button.getAttribute('data-status');
            const result = await adminPost('/api/admin/members/mark', {{
              member_id: memberId,
              payment_status: status,
            }});
            showAlert('success', result.message || `Member ${{memberId}} marked as ${{status}}.`);
          }}
          await refreshMembers();
        }} catch (error) {{
          showAlert('error', error.message);
        }}
      }}

      loginUserBtn.addEventListener('click', async () => {{
        state.role = 'User';
        loginScreen.classList.add('hidden');
        roleBadge.textContent = 'User';
        document.getElementById('sidebar').classList.remove('hidden');
        settingsLocked.classList.remove('hidden');
        passwordChangeForm.classList.add('hidden');
        openAddMemberBtn.classList.add('hidden');
        try {{
          await callAgent('Provide a status summary for members.');
        }} catch (err) {{
          console.warn('Agent summary for user view failed', err);
        }}
        refreshMembers();
      }});

      adminLoginForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        const adminId = document.getElementById('admin-login-id').value.trim();
        const adminPassword = document.getElementById('admin-login-password').value.trim();

        if (!adminId || !adminPassword) {{
          showAlert('error', 'Admin ID and password required');
          return;
        }}

        try {{
          const response = await fetch('/api/admin/login', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ admin_id: adminId, admin_password: adminPassword }}),
          }});
          const data = await response.json().catch(() => ({{}}));
          if (!response.ok || !data.authenticated) {{
            const detail = data.detail || data.message || 'Invalid admin credentials';
            throw new Error(detail);
          }}
          state.role = 'Admin';
          state.adminId = adminId;
          state.adminPassword = adminPassword;
          loginScreen.classList.add('hidden');
          roleBadge.textContent = `Admin: ${{adminId}}`;
          document.getElementById('sidebar').classList.remove('hidden');
          settingsLocked.classList.add('hidden');
          passwordChangeForm.classList.remove('hidden');
          openAddMemberBtn.classList.remove('hidden');
          showAlert('success', data.message || 'Admin authenticated successfully.');
          refreshMembers();
        }} catch (error) {{
          showAlert('error', error.message || 'Authentication failed');
        }}
      }});

      logoutBtn.addEventListener('click', () => {{
        state.role = null;
        state.adminId = null;
        state.adminPassword = null;
        roleBadge.textContent = 'Guest';
        document.getElementById('sidebar').classList.add('hidden');
        openAddMemberBtn.classList.add('hidden');
        passwordChangeForm.classList.add('hidden');
        settingsLocked.classList.remove('hidden');
        loginScreen.classList.remove('hidden');
      }});

      document.querySelectorAll('[data-filter]').forEach((button) => {{
        button.addEventListener('click', () => {{
          state.filter = button.getAttribute('data-filter');
          renderMembers();
        }});
      }});

      openAddMemberBtn.addEventListener('click', () => addMemberModal.classList.remove('hidden'));
      closeAddMemberBtn.addEventListener('click', () => addMemberModal.classList.add('hidden'));

      addMemberRole.addEventListener('change', (event) => {{
        if (event.target.value === 'Admin') {{
          addMemberPasswordWrapper.classList.remove('hidden');
        }} else {{
          addMemberPasswordWrapper.classList.add('hidden');
        }}
      }});

      addMemberForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        const memberId = document.getElementById('add-member-id').value.trim();
        const name = document.getElementById('add-member-name').value.trim();
        const amount = Number(document.getElementById('add-member-amount').value.trim());
        const role = addMemberRole.value;
        const adminPasswordForNewAdmin = document.getElementById('add-member-admin-password').value.trim();

        if (!memberId || !name || Number.isNaN(amount)) {{
          showAlert('error', 'All fields are required');
          return;
        }}
        if (amount < 250) {{
          showAlert('error', 'Minimum payment is ₹250');
          return;
        }}
        if (role === 'Admin' && !adminPasswordForNewAdmin) {{
          showAlert('error', 'Admin role requires a password');
          return;
        }}

        try {{
          const payload = {{
            member_id: memberId,
            name,
            amount,
            role,
          }};
          if (role === 'Admin') {{
            payload.password = adminPasswordForNewAdmin;
          }}
          const result = await adminPost('/api/admin/members', payload);
          showAlert('success', result.message || `Member ${{name}} added.`);
          addMemberModal.classList.add('hidden');
          addMemberForm.reset();
          addMemberPasswordWrapper.classList.add('hidden');
          await refreshMembers();
        }} catch (error) {{
          showAlert('error', error.message);
        }}
      }});

      passwordChangeForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        const adminId = document.getElementById('settings-admin-id').value.trim();
        const newPassword = document.getElementById('settings-new-password').value.trim();

        if (!adminId || !newPassword) {{
          showAlert('error', 'Admin ID and new password required');
          return;
        }}

        try {{
          const result = await adminPost('/api/admin/password', {{
            target_admin_id: adminId,
            new_password: newPassword,
          }});
          showAlert('success', result.message || 'Password updated successfully.');
          passwordChangeForm.reset();
        }} catch (error) {{
          showAlert('error', error.message);
        }}
      }});

      // Mobile sidebar toggle (optional future enhancement)
      refreshMembers();
    </script>
  </body>
</html>
"""
