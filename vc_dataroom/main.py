"""
VC Data Room - Secure file sharing with authentication and audit logging
https://vc.amphoraxe.ca
"""

from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import hashlib
import secrets
import sqlite3
import jwt
import os

# Configuration
SECRET_KEY = os.environ.get("VC_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
DATA_DIR = Path(__file__).parent.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "dataroom.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    
    # Files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            mime_type TEXT,
            folder TEXT DEFAULT '/',
            uploaded_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
    """)
    
    # File access permissions (which users can see which files)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            can_download BOOLEAN DEFAULT 1,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            granted_by INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (granted_by) REFERENCES users(id),
            UNIQUE(file_id, user_id)
        )
    """)
    
    # Audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            user_email TEXT,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            resource_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Create default admin if not exists
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if not cursor.fetchone():
        admin_password = os.environ.get("VC_ADMIN_PASSWORD", "changeme123")
        password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)",
            ("admin@amphoraxe.ca", password_hash, "Admin", "admin")
        )
        print(f"Created default admin user: admin@amphoraxe.ca")
    
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup."""
    init_db()
    yield


app = FastAPI(
    title="VC Data Room",
    description="Secure file sharing for investors",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://vc.amphoraxe.ca"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


# =============================================================================
# Utility Functions
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def log_action(
    request: Request,
    action: str,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    resource_name: Optional[str] = None,
    details: Optional[str] = None
):
    """Log an action to the audit log."""
    conn = get_db()
    cursor = conn.cursor()
    
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    # Get forwarded IP if behind proxy
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    cursor.execute("""
        INSERT INTO audit_log 
        (user_id, user_email, action, resource_type, resource_id, resource_name, ip_address, user_agent, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, user_email, action, resource_type, resource_id, resource_name, ip_address, user_agent, details))
    
    conn.commit()
    conn.close()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[dict]:
    """Get current user from JWT token."""
    # Check Authorization header
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload:
            return payload
    
    # Check cookie
    token = request.cookies.get("access_token")
    if token:
        payload = decode_token(token)
        if payload:
            return payload
    
    return None


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Require authentication."""
    user = await get_current_user(request, credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """Require admin role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


# =============================================================================
# Auth Endpoints
# =============================================================================

@app.post("/api/auth/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    """Login and get access token."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,))
    user = cursor.fetchone()
    
    if not user or not verify_password(password, user["password_hash"]):
        log_action(request, "LOGIN_FAILED", user_email=email, details="Invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Update last login
    cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow(), user["id"]))
    conn.commit()
    conn.close()
    
    # Create token
    token = create_access_token({
        "sub": user["email"],
        "user_id": user["id"],
        "name": user["name"],
        "role": user["role"]
    })
    
    log_action(request, "LOGIN_SUCCESS", user_id=user["id"], user_email=user["email"])
    
    response = JSONResponse({"access_token": token, "token_type": "bearer", "name": user["name"]})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600
    )
    return response


@app.post("/api/auth/logout")
async def logout(request: Request, user: dict = Depends(require_auth)):
    """Logout and clear cookie."""
    log_action(request, "LOGOUT", user_id=user.get("user_id"), user_email=user.get("sub"))
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie("access_token")
    return response


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    """Get current user info."""
    return {
        "email": user.get("sub"),
        "name": user.get("name"),
        "role": user.get("role"),
        "user_id": user.get("user_id")
    }


# =============================================================================
# User Management (Admin only)
# =============================================================================

@app.get("/api/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all users."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, name, role, is_active, created_at, last_login FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


@app.post("/api/users")
async def create_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    role: str = Form("viewer"),
    admin: dict = Depends(require_admin)
):
    """Create a new user."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)",
            (email, hash_password(password), name, role)
        )
        user_id = cursor.lastrowid
        conn.commit()
        
        log_action(
            request, "USER_CREATED",
            user_id=admin.get("user_id"),
            user_email=admin.get("sub"),
            resource_type="user",
            resource_id=user_id,
            resource_name=email
        )
        
        return {"id": user_id, "email": email, "name": name, "role": role}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already exists")
    finally:
        conn.close()


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """Deactivate a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    
    log_action(
        request, "USER_DEACTIVATED",
        user_id=admin.get("user_id"),
        user_email=admin.get("sub"),
        resource_type="user",
        resource_id=user_id,
        resource_name=user["email"]
    )
    
    conn.close()
    return {"message": "User deactivated"}


# =============================================================================
# File Management
# =============================================================================

@app.get("/api/files")
async def list_files(request: Request, user: dict = Depends(require_auth)):
    """List files accessible to current user."""
    conn = get_db()
    cursor = conn.cursor()
    
    user_id = user.get("user_id")
    role = user.get("role")
    
    if role == "admin":
        # Admins see all files
        cursor.execute("""
            SELECT f.*, u.name as uploaded_by_name 
            FROM files f 
            LEFT JOIN users u ON f.uploaded_by = u.id
            ORDER BY f.created_at DESC
        """)
    else:
        # Regular users see only permitted files
        cursor.execute("""
            SELECT f.*, u.name as uploaded_by_name, fp.can_download
            FROM files f
            JOIN file_permissions fp ON f.id = fp.file_id
            LEFT JOIN users u ON f.uploaded_by = u.id
            WHERE fp.user_id = ?
            ORDER BY f.created_at DESC
        """, (user_id,))
    
    files = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    log_action(request, "FILES_LISTED", user_id=user_id, user_email=user.get("sub"))
    
    return files


@app.post("/api/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Form("/"),
    admin: dict = Depends(require_admin)
):
    """Upload a file (admin only)."""
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._-")
    unique_name = f"{timestamp}_{safe_name}"
    file_path = UPLOADS_DIR / unique_name
    
    # Save file
    content = await file.read()
    file_path.write_bytes(content)
    
    # Get mime type
    mime_type = file.content_type or "application/octet-stream"
    
    # Save to database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO files (filename, original_name, file_path, file_size, mime_type, folder, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (unique_name, file.filename, str(file_path), len(content), mime_type, folder, admin.get("user_id")))
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    log_action(
        request, "FILE_UPLOADED",
        user_id=admin.get("user_id"),
        user_email=admin.get("sub"),
        resource_type="file",
        resource_id=file_id,
        resource_name=file.filename,
        details=f"Size: {len(content)} bytes"
    )
    
    return {"id": file_id, "filename": file.filename, "size": len(content)}


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: int, request: Request, user: dict = Depends(require_auth)):
    """Download a file."""
    conn = get_db()
    cursor = conn.cursor()
    
    user_id = user.get("user_id")
    role = user.get("role")
    
    # Check access
    if role != "admin":
        cursor.execute(
            "SELECT can_download FROM file_permissions WHERE file_id = ? AND user_id = ?",
            (file_id, user_id)
        )
        perm = cursor.fetchone()
        if not perm or not perm["can_download"]:
            log_action(
                request, "FILE_ACCESS_DENIED",
                user_id=user_id,
                user_email=user.get("sub"),
                resource_type="file",
                resource_id=file_id
            )
            raise HTTPException(status_code=403, detail="Access denied")
    
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file = cursor.fetchone()
    conn.close()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = Path(file["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    log_action(
        request, "FILE_DOWNLOADED",
        user_id=user_id,
        user_email=user.get("sub"),
        resource_type="file",
        resource_id=file_id,
        resource_name=file["original_name"]
    )
    
    return FileResponse(
        file_path,
        filename=file["original_name"],
        media_type=file["mime_type"]
    )


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: int, request: Request, admin: dict = Depends(require_admin)):
    """Delete a file (admin only)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file = cursor.fetchone()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Delete from disk
    file_path = Path(file["file_path"])
    if file_path.exists():
        file_path.unlink()
    
    # Delete from database
    cursor.execute("DELETE FROM file_permissions WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    
    log_action(
        request, "FILE_DELETED",
        user_id=admin.get("user_id"),
        user_email=admin.get("sub"),
        resource_type="file",
        resource_id=file_id,
        resource_name=file["original_name"]
    )
    
    return {"message": "File deleted"}


# =============================================================================
# File Permissions (Admin only)
# =============================================================================

@app.post("/api/files/{file_id}/permissions")
async def grant_file_access(
    file_id: int,
    request: Request,
    user_id: int = Form(...),
    can_download: bool = Form(True),
    admin: dict = Depends(require_admin)
):
    """Grant user access to a file."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify file exists
    cursor.execute("SELECT original_name FROM files WHERE id = ?", (file_id,))
    file = cursor.fetchone()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Verify user exists
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO file_permissions (file_id, user_id, can_download, granted_by)
            VALUES (?, ?, ?, ?)
        """, (file_id, user_id, can_download, admin.get("user_id")))
        conn.commit()
        
        log_action(
            request, "PERMISSION_GRANTED",
            user_id=admin.get("user_id"),
            user_email=admin.get("sub"),
            resource_type="file",
            resource_id=file_id,
            resource_name=file["original_name"],
            details=f"Granted to user {user['email']}"
        )
        
        return {"message": "Permission granted"}
    finally:
        conn.close()


@app.delete("/api/files/{file_id}/permissions/{user_id}")
async def revoke_file_access(
    file_id: int,
    user_id: int,
    request: Request,
    admin: dict = Depends(require_admin)
):
    """Revoke user access to a file."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT original_name FROM files WHERE id = ?", (file_id,))
    file = cursor.fetchone()
    
    cursor.execute("DELETE FROM file_permissions WHERE file_id = ? AND user_id = ?", (file_id, user_id))
    conn.commit()
    
    log_action(
        request, "PERMISSION_REVOKED",
        user_id=admin.get("user_id"),
        user_email=admin.get("sub"),
        resource_type="file",
        resource_id=file_id,
        resource_name=file["original_name"] if file else None,
        details=f"Revoked from user_id {user_id}"
    )
    
    conn.close()
    return {"message": "Permission revoked"}


@app.get("/api/files/{file_id}/permissions")
async def list_file_permissions(file_id: int, admin: dict = Depends(require_admin)):
    """List all users with access to a file."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fp.*, u.email, u.name 
        FROM file_permissions fp
        JOIN users u ON fp.user_id = u.id
        WHERE fp.file_id = ?
    """, (file_id,))
    perms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return perms


# =============================================================================
# Audit Log (Admin only)
# =============================================================================

@app.get("/api/audit")
async def get_audit_log(
    limit: int = 100,
    offset: int = 0,
    user_email: Optional[str] = None,
    action: Optional[str] = None,
    admin: dict = Depends(require_admin)
):
    """Get audit log entries."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    
    if user_email:
        query += " AND user_email = ?"
        params.append(user_email)
    if action:
        query += " AND action = ?"
        params.append(action)
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return logs


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "vc-dataroom", "timestamp": datetime.utcnow().isoformat()}


# =============================================================================
# Static Files and Frontend
# =============================================================================

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the login page or redirect to dashboard."""
    user = await get_current_user(request, None)
    if user:
        return RedirectResponse(url="/dashboard")
    
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VC Data Room - Login</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: rgba(255, 255, 255, 0.95);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 400px;
        }
        h1 {
            color: #1a1a2e;
            margin-bottom: 8px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 32px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            color: #333;
            margin-bottom: 6px;
            font-weight: 500;
            font-size: 14px;
        }
        input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #1a1a2e;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #1a1a2e;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #16213e;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .error {
            background: #fee;
            color: #c00;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            display: none;
        }
        .logo {
            text-align: center;
            margin-bottom: 24px;
        }
        .logo svg {
            width: 60px;
            height: 60px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="100" height="100" rx="20" fill="#1a1a2e"/>
                <path d="M30 70V30L50 50L70 30V70" stroke="white" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <h1>VC Data Room</h1>
        <p class="subtitle">Secure document access for investors</p>
        
        <div class="error" id="error"></div>
        
        <form id="loginForm">
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" required autocomplete="email">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" id="submitBtn">Sign In</button>
        </form>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const error = document.getElementById('error');
            
            btn.disabled = true;
            btn.textContent = 'Signing in...';
            error.style.display = 'none';
            
            const formData = new FormData(e.target);
            
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    window.location.href = '/dashboard';
                } else {
                    const data = await response.json();
                    error.textContent = data.detail || 'Login failed';
                    error.style.display = 'block';
                }
            } catch (err) {
                error.textContent = 'Connection error. Please try again.';
                error.style.display = 'block';
            }
            
            btn.disabled = false;
            btn.textContent = 'Sign In';
        });
    </script>
</body>
</html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(require_auth)):
    """Main dashboard page."""
    is_admin = user.get("role") == "admin"
    
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - VC Data Room</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
        }}
        .navbar {{
            background: #1a1a2e;
            color: white;
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .navbar h1 {{
            font-size: 20px;
        }}
        .user-info {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}
        .user-name {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .logout-btn {{
            background: rgba(255,255,255,0.1);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }}
        .logout-btn:hover {{
            background: rgba(255,255,255,0.2);
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
        }}
        .tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
        }}
        .tab {{
            padding: 12px 24px;
            background: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            color: #666;
        }}
        .tab.active {{
            background: #1a1a2e;
            color: white;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 24px;
            margin-bottom: 24px;
        }}
        .card h2 {{
            font-size: 18px;
            margin-bottom: 16px;
            color: #333;
        }}
        .file-list {{
            display: grid;
            gap: 12px;
        }}
        .file-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            background: #f9f9f9;
            border-radius: 8px;
        }}
        .file-info {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .file-icon {{
            width: 40px;
            height: 40px;
            background: #1a1a2e;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }}
        .file-name {{
            font-weight: 500;
            color: #333;
        }}
        .file-meta {{
            font-size: 12px;
            color: #999;
        }}
        .download-btn {{
            background: #1a1a2e;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }}
        .download-btn:hover {{
            background: #16213e;
        }}
        .admin-section {{
            display: {'block' if is_admin else 'none'};
        }}
        .upload-form {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 20px;
        }}
        .upload-form input[type="file"] {{
            flex: 1;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            font-weight: 600;
            color: #666;
            font-size: 12px;
            text-transform: uppercase;
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }}
        .badge-admin {{
            background: #e3f2fd;
            color: #1565c0;
        }}
        .badge-viewer {{
            background: #f3e5f5;
            color: #7b1fa2;
        }}
        .empty-state {{
            text-align: center;
            padding: 48px;
            color: #999;
        }}
        .section {{ display: none; }}
        .section.active {{ display: block; }}
    </style>
</head>
<body>
    <nav class="navbar">
        <h1>VC Data Room</h1>
        <div class="user-info">
            <span class="user-name">{user.get('name')} ({user.get('role')})</span>
            <button class="logout-btn" onclick="logout()">Sign Out</button>
        </div>
    </nav>
    
    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="showSection('files')">Files</button>
            <button class="tab admin-section" onclick="showSection('users')">Users</button>
            <button class="tab admin-section" onclick="showSection('audit')">Audit Log</button>
        </div>
        
        <div id="files-section" class="section active">
            <div class="card admin-section">
                <h2>Upload File</h2>
                <form class="upload-form" id="uploadForm">
                    <input type="file" name="file" required>
                    <button type="submit" class="download-btn">Upload</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Available Files</h2>
                <div class="file-list" id="fileList">
                    <div class="empty-state">Loading files...</div>
                </div>
            </div>
        </div>
        
        <div id="users-section" class="section admin-section">
            <div class="card">
                <h2>Add User</h2>
                <form id="addUserForm" style="display: flex; gap: 12px; flex-wrap: wrap;">
                    <input type="email" name="email" placeholder="Email" required style="flex: 1; min-width: 200px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px;">
                    <input type="text" name="name" placeholder="Name" required style="flex: 1; min-width: 150px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px;">
                    <input type="password" name="password" placeholder="Password" required style="flex: 1; min-width: 150px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px;">
                    <select name="role" style="padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px;">
                        <option value="viewer">Viewer</option>
                        <option value="admin">Admin</option>
                    </select>
                    <button type="submit" class="download-btn">Add User</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Users</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Role</th>
                            <th>Last Login</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="userList">
                        <tr><td colspan="5" class="empty-state">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="audit-section" class="section admin-section">
            <div class="card">
                <h2>Audit Log</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>User</th>
                            <th>Action</th>
                            <th>Resource</th>
                            <th>IP Address</th>
                        </tr>
                    </thead>
                    <tbody id="auditList">
                        <tr><td colspan="5" class="empty-state">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
        const isAdmin = {'true' if is_admin else 'false'};
        
        function showSection(name) {{
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(name + '-section').classList.add('active');
            event.target.classList.add('active');
            
            if (name === 'users') loadUsers();
            if (name === 'audit') loadAudit();
        }}
        
        async function logout() {{
            await fetch('/api/auth/logout', {{ method: 'POST' }});
            window.location.href = '/';
        }}
        
        async function loadFiles() {{
            const res = await fetch('/api/files');
            const files = await res.json();
            const list = document.getElementById('fileList');
            
            if (files.length === 0) {{
                list.innerHTML = '<div class="empty-state">No files available</div>';
                return;
            }}
            
            list.innerHTML = files.map(f => `
                <div class="file-item">
                    <div class="file-info">
                        <div class="file-icon">📄</div>
                        <div>
                            <div class="file-name">${{f.original_name}}</div>
                            <div class="file-meta">${{formatSize(f.file_size)}} • ${{formatDate(f.created_at)}}</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="download-btn" onclick="downloadFile(${{f.id}})">Download</button>
                        ${{isAdmin ? `<button class="download-btn" onclick="managePermissions(${{f.id}})" style="background: #666;">Permissions</button>` : ''}}
                        ${{isAdmin ? `<button class="download-btn" onclick="deleteFile(${{f.id}})" style="background: #c00;">Delete</button>` : ''}}
                    </div>
                </div>
            `).join('');
        }}
        
        function formatSize(bytes) {{
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
            return (bytes/1024/1024).toFixed(1) + ' MB';
        }}
        
        function formatDate(dateStr) {{
            return new Date(dateStr).toLocaleDateString();
        }}
        
        async function downloadFile(id) {{
            window.open('/api/files/' + id + '/download', '_blank');
        }}
        
        async function deleteFile(id) {{
            if (!confirm('Delete this file?')) return;
            await fetch('/api/files/' + id, {{ method: 'DELETE' }});
            loadFiles();
        }}
        
        async function managePermissions(fileId) {{
            const userId = prompt('Enter user ID to grant access:');
            if (!userId) return;
            
            const formData = new FormData();
            formData.append('user_id', userId);
            formData.append('can_download', 'true');
            
            await fetch(`/api/files/${{fileId}}/permissions`, {{
                method: 'POST',
                body: formData
            }});
            alert('Permission granted');
        }}
        
        async function loadUsers() {{
            const res = await fetch('/api/users');
            const users = await res.json();
            const list = document.getElementById('userList');
            
            list.innerHTML = users.map(u => `
                <tr>
                    <td>${{u.name}}</td>
                    <td>${{u.email}}</td>
                    <td><span class="badge badge-${{u.role}}">${{u.role}}</span></td>
                    <td>${{u.last_login ? formatDate(u.last_login) : 'Never'}}</td>
                    <td>
                        ${{u.is_active ? `<button onclick="deactivateUser(${{u.id}})" style="color: #c00; background: none; border: none; cursor: pointer;">Deactivate</button>` : '<span style="color: #999;">Inactive</span>'}}
                    </td>
                </tr>
            `).join('');
        }}
        
        async function deactivateUser(id) {{
            if (!confirm('Deactivate this user?')) return;
            await fetch('/api/users/' + id, {{ method: 'DELETE' }});
            loadUsers();
        }}
        
        async function loadAudit() {{
            const res = await fetch('/api/audit?limit=50');
            const logs = await res.json();
            const list = document.getElementById('auditList');
            
            list.innerHTML = logs.map(l => `
                <tr>
                    <td>${{new Date(l.timestamp).toLocaleString()}}</td>
                    <td>${{l.user_email || '-'}}</td>
                    <td>${{l.action}}</td>
                    <td>${{l.resource_name || '-'}}</td>
                    <td>${{l.ip_address}}</td>
                </tr>
            `).join('');
        }}
        
        document.getElementById('uploadForm')?.addEventListener('submit', async (e) => {{
            e.preventDefault();
            const formData = new FormData(e.target);
            await fetch('/api/files/upload', {{ method: 'POST', body: formData }});
            e.target.reset();
            loadFiles();
        }});
        
        document.getElementById('addUserForm')?.addEventListener('submit', async (e) => {{
            e.preventDefault();
            const formData = new FormData(e.target);
            const res = await fetch('/api/users', {{ method: 'POST', body: formData }});
            if (res.ok) {{
                e.target.reset();
                loadUsers();
            }} else {{
                const data = await res.json();
                alert(data.detail || 'Failed to create user');
            }}
        }});
        
        loadFiles();
    </script>
</body>
</html>
"""
