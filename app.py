# -*- coding: utf-8 -*-
"""
私密中心 (Private Hub) - 重构版
"""

import os
import sys
import json
import hashlib
import secrets
import platform
import shutil
from datetime import datetime
from pathlib import Path
from functools import wraps

import psutil
from flask import (
    Flask, render_template_string, request, redirect,
    url_for, session, send_file, jsonify, abort
)

# ============================================================================
# 配置
# ============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 7

BASE_DIR = Path(__file__).parent
PERSISTENT_DIR = Path(os.environ.get("PERSISTENT_DIR", BASE_DIR / "data"))
CONFIG_DIR = PERSISTENT_DIR / "config"
DATA_DIR = PERSISTENT_DIR / "data"
FILES_DIR = PERSISTENT_DIR / "files"
NOTES_DIR = PERSISTENT_DIR / "notes"

for d in [CONFIG_DIR, DATA_DIR, FILES_DIR, NOTES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

USERS_FILE = CONFIG_DIR / "users.json"
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"
NOTES_INDEX = DATA_DIR / "notes_index.json"
SHARES_FILE = CONFIG_DIR / "shares.json"


# ============================================================================
# 工具函数
# ============================================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


DEFAULT_USERS = {
    "001": {
        "password_hash": hash_password("123456"),
        "role": "admin",
        "created_at": "2026-01-01 00:00"
    }
}


def load_users():
    if USERS_FILE.exists():
        try:
            users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            if "001" not in users:
                users["001"] = DEFAULT_USERS["001"].copy()
                save_users(users)
            if users:
                return users
        except:
            pass
    save_users(DEFAULT_USERS)
    return DEFAULT_USERS.copy()


def save_users(users):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def get_current_user():
    username = session.get("username")
    if not username:
        return None
    users = load_users()
    return users.get(username)


def is_admin():
    user = get_current_user()
    return user and user.get("role") == "admin"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def load_bookmarks():
    if BOOKMARKS_FILE.exists():
        return json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
    return DEFAULT_BOOKMARKS


def save_bookmarks(bookmarks):
    BOOKMARKS_FILE.write_text(json.dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")


def load_notes_index():
    if NOTES_INDEX.exists():
        return json.loads(NOTES_INDEX.read_text(encoding="utf-8"))
    return []


def save_notes_index(notes):
    NOTES_INDEX.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


def load_shares():
    if SHARES_FILE.exists():
        try:
            return json.loads(SHARES_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def save_shares(shares):
    SHARES_FILE.write_text(json.dumps(shares, ensure_ascii=False, indent=2), encoding="utf-8")


DEFAULT_BOOKMARKS = [
    {"id": "github", "title": "GitHub", "url": "https://github.com", "icon": "🐙", "category": "开发"},
    {"id": "google", "title": "Google", "url": "https://google.com", "icon": "🔍", "category": "搜索"},
    {"id": "youtube", "title": "YouTube", "url": "https://youtube.com", "icon": "📺", "category": "娱乐"},
]


# ============================================================================
# 路由 - 认证
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        users = load_users()
        user = users.get(username)
        if user and hash_password(password) == user.get("password_hash", ""):
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("home"))
        error = "用户名或密码错误"
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    error = None
    success = None
    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        username = session.get("username")
        users = load_users()
        user = users.get(username)
        if not user or hash_password(old_password) != user.get("password_hash", ""):
            error = "原密码错误"
        elif new_password != confirm_password:
            error = "两次输入的新密码不一致"
        elif len(new_password) < 4:
            error = "密码长度不能少于4位"
        else:
            users[username]["password_hash"] = hash_password(new_password)
            save_users(users)
            success = "密码修改成功"
    return render_template_string(CHANGE_PWD_HTML, error=error, success=success)


# ============================================================================
# 路由 - 管理员
# ============================================================================

@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = load_users()
    return render_template_string(ADMIN_USERS_HTML, users=users, current_user=session.get("username"))


@app.route("/admin/users/add", methods=["POST"])
@login_required
@admin_required
def admin_add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    users = load_users()
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if username in users:
        return jsonify({"error": "用户名已存在"}), 400
    if role not in ["admin", "user"]:
        return jsonify({"error": "无效的角色"}), 400
    users[username] = {
        "password_hash": hash_password(password),
        "role": role,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_users(users)
    return jsonify({"success": True})


@app.route("/admin/users/<username>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_user(username):
    users = load_users()
    admin_user = os.environ.get("ADMIN_USER", "001")
    if username == admin_user:
        return jsonify({"error": "不能删除管理员账号"}), 400
    if username in users:
        del users[username]
        save_users(users)
    return jsonify({"success": True})


@app.route("/admin/users/<username>/reset-password", methods=["POST"])
@login_required
@admin_required
def admin_reset_password(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "用户不存在"}), 404
    new_password = secrets.token_urlsafe(8)
    users[username]["password_hash"] = hash_password(new_password)
    save_users(users)
    return jsonify({"success": True, "password": new_password})


# ============================================================================
# 路由 - 页面
# ============================================================================

@app.route("/")
@login_required
def home():
    return render_template_string(HOME_HTML)


@app.route("/startpage")
@login_required
def startpage():
    bookmarks = load_bookmarks()
    return render_template_string(STARTPAGE_HTML, bookmarks=bookmarks)


@app.route("/files")
@app.route("/files/<path:filepath>")
@login_required
def files(filepath=None):
    if filepath is None:
        filepath = ""
    base_path = FILES_DIR / filepath
    if not base_path.exists() or not base_path.is_relative_to(FILES_DIR):
        abort(404)
    if base_path.is_file():
        return send_file(base_path)
    items = []
    for item in sorted(base_path.iterdir()):
        rel_path = item.relative_to(FILES_DIR)
        items.append({
            "name": item.name,
            "path": str(rel_path),
            "is_dir": item.is_dir(),
            "size": item.stat().st_size if item.is_file() else 0,
            "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        })
    return render_template_string(FILES_HTML, items=items, current_path=filepath)


@app.route("/notes")
@login_required
def notes():
    notes_list = load_notes_index()
    query = request.args.get("q", "").strip()
    if query:
        filtered = []
        for note in notes_list:
            title_match = query.lower() in note.get("title", "").lower()
            note_file = NOTES_DIR / f"{note['id']}.md"
            content_match = False
            if note_file.exists():
                content = note_file.read_text(encoding="utf-8", errors="replace")
                content_match = query.lower() in content.lower()
            if title_match or content_match:
                filtered.append(note)
        notes_list = filtered
    return render_template_string(NOTES_HTML, notes=notes_list, query=query)


@app.route("/notes/<note_id>")
@login_required
def note_detail(note_id):
    note_file = NOTES_DIR / f"{note_id}.md"
    if not note_file.exists():
        abort(404)
    content = note_file.read_text(encoding="utf-8")
    notes_index = load_notes_index()
    note = next((n for n in notes_index if n["id"] == note_id), {})
    title = note.get("title", "无标题")
    return render_template_string(NOTE_DETAIL_HTML, content=content, note_id=note_id, title=title)


# ============================================================================
# 路由 - 文件API
# ============================================================================

@app.route("/download/<path:filepath>")
@login_required
def download(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not file_path.is_relative_to(FILES_DIR) or file_path.is_dir():
        abort(404)
    return send_file(file_path, as_attachment=True)


@app.route("/preview/<path:filepath>")
@login_required
def preview(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not file_path.is_relative_to(FILES_DIR) or file_path.is_dir():
        abort(404)
    ext = file_path.suffix.lower()
    text_exts = ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.log', '.ini', '.cfg', '.yml', '.yaml']
    img_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']
    if ext in img_exts:
        return send_file(file_path)
    elif ext in text_exts:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return render_template_string(PREVIEW_TEXT_HTML, content=content, filename=filepath, ext=ext)
    elif ext == '.pdf':
        return send_file(file_path, mimetype='application/pdf')
    else:
        content = file_path.read_bytes()[:5000]
        try:
            text = content.decode("utf-8", errors="replace")
            return render_template_string(PREVIEW_TEXT_HTML, content=text, filename=filepath, ext=ext)
        except:
            return send_file(file_path, as_attachment=True)


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400
    save_path = FILES_DIR / file.filename
    file.save(str(save_path))
    return jsonify({"success": True, "path": file.filename})


@app.route("/api/delete/<path:filepath>", methods=["DELETE"])
@login_required
def api_delete_file(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not file_path.is_relative_to(FILES_DIR):
        return jsonify({"error": "文件不存在"}), 404
    if file_path.is_dir():
        shutil.rmtree(file_path)
    else:
        file_path.unlink()
    return jsonify({"success": True})


@app.route("/api/rename/<path:filepath>", methods=["POST"])
@login_required
def api_rename_file(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not file_path.is_relative_to(FILES_DIR):
        return jsonify({"error": "文件不存在"}), 404
    new_name = request.json.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "新文件名不能为空"}), 400
    new_path = file_path.parent / new_name
    if new_path.exists():
        return jsonify({"error": "文件名已存在"}), 400
    file_path.rename(new_path)
    return jsonify({"success": True})


@app.route("/api/share/<path:filepath>", methods=["POST"])
@login_required
def api_share_file(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not file_path.is_relative_to(FILES_DIR):
        return jsonify({"error": "文件不存在"}), 404
    token = secrets.token_urlsafe(16)
    shares = load_shares()
    shares[token] = {"path": filepath, "type": "file", "created": datetime.now().isoformat()}
    save_shares(shares)
    return jsonify({"success": True, "token": token, "url": f"/s/{token}"})


# ============================================================================
# 路由 - 笔记API
# ============================================================================

@app.route("/api/bookmarks", methods=["GET", "POST"])
@login_required
def api_bookmarks():
    if request.method == "POST":
        data = request.json
        bookmarks = load_bookmarks()
        bookmarks.append({
            "id": secrets.token_hex(4),
            "title": data.get("title", ""),
            "url": data.get("url", ""),
            "icon": data.get("icon", "🔗"),
            "category": data.get("category", "未分类")
        })
        save_bookmarks(bookmarks)
        return jsonify({"success": True})
    return jsonify(load_bookmarks())


@app.route("/api/bookmarks/<bid>", methods=["DELETE"])
@login_required
def api_delete_bookmark(bid):
    bookmarks = load_bookmarks()
    bookmarks = [b for b in bookmarks if b.get("id") != bid]
    save_bookmarks(bookmarks)
    return jsonify({"success": True})


@app.route("/api/notes", methods=["POST"])
@login_required
def api_create_note():
    data = request.json
    note_id = secrets.token_hex(8)
    note_file = NOTES_DIR / f"{note_id}.md"
    note_file.write_text(data.get("content", ""), encoding="utf-8")
    notes_index = load_notes_index()
    notes_index.append({
        "id": note_id,
        "title": data.get("title", "无标题"),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_notes_index(notes_index)
    return jsonify({"success": True, "id": note_id})


@app.route("/api/notes/<note_id>", methods=["DELETE"])
@login_required
def api_delete_note(note_id):
    note_file = NOTES_DIR / f"{note_id}.md"
    if note_file.exists():
        note_file.unlink()
    notes_index = load_notes_index()
    notes_index = [n for n in notes_index if n.get("id") != note_id]
    save_notes_index(notes_index)
    return jsonify({"success": True})


@app.route("/api/notes/<note_id>/rename", methods=["POST"])
@login_required
def api_rename_note(note_id):
    new_title = request.json.get("title", "").strip()
    if not new_title:
        return jsonify({"error": "标题不能为空"}), 400
    notes_index = load_notes_index()
    for note in notes_index:
        if note["id"] == note_id:
            note["title"] = new_title
            break
    save_notes_index(notes_index)
    return jsonify({"success": True})


@app.route("/api/notes/<note_id>/share", methods=["POST"])
@login_required
def api_share_note(note_id):
    notes_index = load_notes_index()
    note = next((n for n in notes_index if n["id"] == note_id), None)
    if not note:
        return jsonify({"error": "笔记不存在"}), 404
    token = secrets.token_urlsafe(16)
    shares = load_shares()
    shares[token] = {"type": "note", "note_id": note_id, "title": note["title"], "created": datetime.now().isoformat()}
    save_shares(shares)
    return jsonify({"success": True, "token": token, "url": f"/s/{token}"})


@app.route("/api/notes/<note_id>/download")
@login_required
def api_download_note(note_id):
    note_file = NOTES_DIR / f"{note_id}.md"
    if not note_file.exists():
        abort(404)
    notes_index = load_notes_index()
    note = next((n for n in notes_index if n["id"] == note_id), None)
    title = note["title"] if note else note_id
    return send_file(note_file, as_attachment=True, download_name=f"{title}.md")


# ============================================================================
# 路由 - 系统API
# ============================================================================

@app.route("/api/system")
@login_required
def api_system():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    return jsonify({
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "platform": platform.system(),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "uptime": str(uptime).split(".")[0]
    })


@app.route("/api/data/stats")
@login_required
def api_data_stats():
    bookmarks = load_bookmarks()
    notes = load_notes_index()
    files_count = sum(1 for _ in FILES_DIR.rglob("*") if _.is_file()) if FILES_DIR.exists() else 0
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    return jsonify({
        "bookmarks": len(bookmarks),
        "notes": len(notes),
        "files": files_count,
        "uptime": str(uptime).split(".")[0]
    })


@app.route("/api/data/export")
@login_required
def api_data_export():
    data = {
        "bookmarks": load_bookmarks(),
        "notes": load_notes_index(),
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    return jsonify(data), 200, {
        "Content-Disposition": "attachment; filename=private_hub_export.json"
    }


# ============================================================================
# 路由 - 分享页面
# ============================================================================

@app.route("/s/<token>")
def shared_file(token):
    shares = load_shares()
    share = shares.get(token)
    if not share:
        abort(404)
    if share["type"] == "file":
        file_path = FILES_DIR / share["path"]
        if not file_path.exists():
            abort(404)
        return send_file(file_path, as_attachment=True)
    elif share["type"] == "note":
        note_file = NOTES_DIR / f"{share['note_id']}.md"
        if not note_file.exists():
            abort(404)
        content = note_file.read_text(encoding="utf-8")
        title = share.get("title", "笔记")
        return render_template_string(SHARED_NOTE_HTML, content=content, title=title)
    abort(404)


# ============================================================================
# HTML模板 - 通用CSS
# ============================================================================

NAV_CSS = '''
nav {
    background: rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(20px);
}
nav .logo { font-size: 18px; font-weight: bold; color: #fff; }
nav .links { display: flex; gap: 8px; align-items: center; }
nav .links a {
    color: rgba(255,255,255,0.6);
    text-decoration: none;
    padding: 6px 14px;
    border-radius: 8px;
    font-size: 13px;
    transition: all 0.2s;
}
nav .links a:hover { color: #fff; background: rgba(255,255,255,0.1); }
nav .links a.active { color: #e94560; background: rgba(233,69,96,0.1); }
'''

RESPONSIVE_CSS = '''
@media (max-width: 768px) {
    nav { flex-direction: column; gap: 10px; padding: 10px 15px; }
    nav .links { display: flex; flex-wrap: wrap; justify-content: center; gap: 4px; }
    nav .links a { padding: 5px 10px; font-size: 12px; }
    .container { padding: 15px; }
    .grid { grid-template-columns: 1fr !important; }
    .quick-links { grid-template-columns: repeat(2, 1fr) !important; }
}
'''

WATERMARK_CSS = '''
.watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
.watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
'''

WATERMARK_JS = '''
var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
'''


def nav_html(active=""):
    user = get_current_user()
    is_adm = user and user.get("role") == "admin"
    links = [
        ("/", "首页", "home"),
        ("/startpage", "启动页", "startpage"),
        ("/files", "文件", "files"),
        ("/notes", "笔记", "notes"),
        ("/change-password", "密码", "password"),
        ("/admin/users", "用户", "users"),
        ("/logout", "退出", "logout"),
    ]
    html = '<nav><div class="logo">Private Hub</div><div class="links">'
    for url, name, key in links:
        if key == "users" and not is_adm:
            continue
        cls = ' class="active"' if key == active else ''
        html += f'<a href="{url}"{cls}>{name}</a>'
    html += '</div></nav>'
    return html


# ============================================================================
# HTML模板 - 登录页
# ============================================================================

LOGIN_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        .login-box {
            background: rgba(255,255,255,0.08); backdrop-filter: blur(30px);
            border: 1px solid rgba(255,255,255,0.12); border-radius: 20px;
            padding: 40px; width: 360px; text-align: center;
        }
        .login-box h1 { font-size: 28px; margin-bottom: 8px; }
        .login-box p { color: rgba(255,255,255,0.5); margin-bottom: 30px; font-size: 14px; }
        .input-group { margin-bottom: 16px; text-align: left; }
        .input-group label { color: rgba(255,255,255,0.6); font-size: 12px; display: block; margin-bottom: 6px; }
        .input-group input {
            width: 100%; padding: 12px 16px; border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px; background: rgba(255,255,255,0.08); color: #fff;
            font-size: 14px; outline: none; transition: all 0.2s;
        }
        .input-group input:focus { border-color: #e94560; background: rgba(255,255,255,0.12); }
        .btn {
            width: 100%; padding: 12px; border: none; border-radius: 10px; margin-top: 8px;
            background: linear-gradient(135deg, #e94560, #c23152); color: #fff;
            font-size: 14px; cursor: pointer; transition: all 0.2s;
        }
        .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(233,69,96,0.3); }
        .error { color: #ff6b6b; font-size: 13px; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Private Hub</h1>
        <p>私密中心</p>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="input-group"><label>用户名</label><input type="text" name="username" placeholder="请输入用户名" autofocus></div>
            <div class="input-group"><label>密码</label><input type="password" name="password" placeholder="请输入密码"></div>
            <button type="submit" class="btn">登录</button>
        </form>
    </div>
</body>
</html>'''


# ============================================================================
# HTML模板 - 首页（合并仪表盘+数据统计）
# ============================================================================

HOME_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>首页 - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        .header { text-align: center; margin-bottom: 30px; }
        #time { font-size: 48px; font-weight: 300; margin: 10px 0; }
        #date { color: rgba(255,255,255,0.4); font-size: 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px; padding: 20px; transition: all 0.2s;
        }
        .card:hover { border-color: rgba(233,69,96,0.3); transform: translateY(-2px); }
        .card-title { color: rgba(255,255,255,0.5); font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
        .card-value { font-size: 28px; font-weight: 600; }
        .card-sub { color: rgba(255,255,255,0.4); font-size: 12px; margin-top: 4px; }
        .progress-bar { height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; margin-top: 12px; overflow: hidden; }
        .progress-fill { height: 100%; border-radius: 3px; transition: width 0.5s; }
        .green { background: linear-gradient(90deg, #00b894, #55efc4); }
        .yellow { background: linear-gradient(90deg, #fdcb6e, #f39c12); }
        .red { background: linear-gradient(90deg, #e94560, #ff6b6b); }
        .chart-card { grid-column: span 2; }
        .quick-section { margin-top: 24px; }
        .section-title { font-size: 14px; color: rgba(255,255,255,0.5); margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
        .quick-links { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
        .quick-link {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 16px; text-align: center; text-decoration: none; color: #fff;
            transition: all 0.2s;
        }
        .quick-link:hover { background: rgba(233,69,96,0.15); border-color: rgba(233,69,96,0.3); transform: translateY(-2px); }
        .quick-link .icon { font-size: 24px; margin-bottom: 8px; display: block; }
        .quick-link .name { font-size: 12px; color: rgba(255,255,255,0.6); }
        ''' + RESPONSIVE_CSS + '''
        @media (max-width: 768px) { .chart-card { grid-column: span 1; } }
        ''' + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("home") + '''
    <div class="container">
        <div class="header">
            <div id="time"></div>
            <div id="date"></div>
        </div>
        <div class="grid">
            <div class="card">
                <div class="card-title">CPU</div>
                <div class="card-value" id="cpu-val">--</div>
                <div class="progress-bar"><div class="progress-fill green" id="cpu-bar"></div></div>
            </div>
            <div class="card">
                <div class="card-title">内存</div>
                <div class="card-value" id="mem-val">--</div>
                <div class="progress-bar"><div class="progress-fill green" id="mem-bar"></div></div>
            </div>
            <div class="card">
                <div class="card-title">磁盘</div>
                <div class="card-value" id="disk-val">--</div>
                <div class="progress-bar"><div class="progress-fill green" id="disk-bar"></div></div>
            </div>
            <div class="card">
                <div class="card-title">运行时间</div>
                <div class="card-value" id="uptime-val" style="font-size:20px">--</div>
            </div>
            <div class="card">
                <div class="card-title">书签</div>
                <div class="card-value" id="bm-val">--</div>
            </div>
            <div class="card">
                <div class="card-title">笔记</div>
                <div class="card-value" id="note-val">--</div>
            </div>
            <div class="card">
                <div class="card-title">文件</div>
                <div class="card-value" id="file-val">--</div>
            </div>
            <div class="card chart-card">
                <div class="card-title">系统监控</div>
                <canvas id="usageChart" height="150"></canvas>
            </div>
        </div>
        <div class="quick-section">
            <div class="section-title">快捷访问</div>
            <div class="quick-links">
                <a href="/startpage" class="quick-link"><span class="icon">🚀</span><span class="name">启动页</span></a>
                <a href="/files" class="quick-link"><span class="icon">📁</span><span class="name">文件</span></a>
                <a href="/notes" class="quick-link"><span class="icon">📝</span><span class="name">笔记</span></a>
                <a href="/change-password" class="quick-link"><span class="icon">🔑</span><span class="name">密码</span></a>
                <a href="/admin/users" class="quick-link"><span class="icon">👥</span><span class="name">用户</span></a>
                <a href="#" class="quick-link" onclick="exportData()"><span class="icon">📥</span><span class="name">导出</span></a>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        function updateTime() {
            var now = new Date();
            document.getElementById('time').textContent = now.toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
            document.getElementById('date').textContent = now.toLocaleDateString('zh-CN', {year:'numeric', month:'long', day:'numeric', weekday:'long'});
        }
        updateTime(); setInterval(updateTime, 1000);
        function getColor(p) { return p > 80 ? 'red' : p > 60 ? 'yellow' : 'green'; }
        function setBar(id, pct) { var el = document.getElementById(id); el.style.width = pct + '%'; el.className = 'progress-fill ' + getColor(pct); }
        var cpuH=[], memH=[], diskH=[], labels=[];
        var ctx = document.getElementById('usageChart');
        var chart = new Chart(ctx, {
            type: 'line',
            data: { labels: labels, datasets: [
                { label: 'CPU', data: cpuH, borderColor: '#e94560', backgroundColor: 'rgba(233,69,96,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
                { label: '内存', data: memH, borderColor: '#00b894', backgroundColor: 'rgba(0,184,148,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
                { label: '磁盘', data: diskH, borderColor: '#fdcb6e', backgroundColor: 'rgba(253,203,110,0.1)', fill: true, tension: 0.3, pointRadius: 0 }
            ]},
            options: { responsive: true, animation: { duration: 300 },
                scales: { y: { beginAtZero: true, max: 100, ticks: { color: 'rgba(255,255,255,0.3)' }, grid: { color: 'rgba(255,255,255,0.05)' } }, x: { ticks: { display: false }, grid: { display: false } } },
                plugins: { legend: { labels: { color: 'rgba(255,255,255,0.5)', usePointStyle: true, pointStyle: 'circle' } } }
            }
        });
        async function loadSystem() {
            try {
                var r = await fetch('/api/system'); var d = await r.json();
                document.getElementById('cpu-val').textContent = d.cpu_percent + '%';
                document.getElementById('mem-val').textContent = d.memory_percent + '%';
                document.getElementById('disk-val').textContent = d.disk_percent + '%';
                document.getElementById('uptime-val').textContent = d.uptime;
                setBar('cpu-bar', d.cpu_percent); setBar('mem-bar', d.memory_percent); setBar('disk-bar', d.disk_percent);
                var t = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
                labels.push(t); cpuH.push(d.cpu_percent); memH.push(d.memory_percent); diskH.push(d.disk_percent);
                if (labels.length > 30) { labels.shift(); cpuH.shift(); memH.shift(); diskH.shift(); }
                chart.update();
            } catch(e) {}
        }
        async function loadStats() {
            try {
                var r = await fetch('/api/data/stats'); var d = await r.json();
                document.getElementById('bm-val').textContent = d.bookmarks;
                document.getElementById('note-val').textContent = d.notes;
                document.getElementById('file-val').textContent = d.files;
            } catch(e) {}
        }
        function exportData() { window.open('/api/data/export', '_blank'); }
        loadSystem(); loadStats();
        setInterval(loadSystem, 3000); setInterval(loadStats, 30000);
    </script>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 启动页
# ============================================================================

STARTPAGE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>启动页 - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .main { max-width: 800px; margin: 0 auto; padding: 60px 24px; text-align: center; }
        .search-box { margin-bottom: 40px; }
        .search-box input {
            width: 100%; padding: 16px 24px; border: 1px solid rgba(255,255,255,0.12);
            border-radius: 14px; background: rgba(255,255,255,0.08); color: #fff;
            font-size: 16px; outline: none; transition: all 0.2s;
        }
        .search-box input:focus { border-color: #e94560; background: rgba(255,255,255,0.12); }
        .bookmarks { text-align: left; }
        .category { margin-bottom: 30px; }
        .category-title { color: rgba(255,255,255,0.4); font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
        .bookmark-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 12px; }
        .bookmark {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 16px 12px; text-align: center; text-decoration: none; color: #fff;
            transition: all 0.2s; position: relative;
        }
        .bookmark:hover { background: rgba(233,69,96,0.15); border-color: rgba(233,69,96,0.3); transform: translateY(-2px); }
        .bookmark .icon { font-size: 28px; margin-bottom: 8px; display: block; }
        .bookmark .title { font-size: 11px; color: rgba(255,255,255,0.7); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .bookmark .delete {
            position: absolute; top: 4px; right: 4px; width: 18px; height: 18px;
            background: rgba(233,69,96,0.8); border: none; border-radius: 50%;
            color: #fff; cursor: pointer; font-size: 10px; display: none; align-items: center; justify-content: center;
        }
        .bookmark:hover .delete { display: flex; }
        .add-bookmark {
            background: rgba(255,255,255,0.03); border: 2px dashed rgba(255,255,255,0.15);
            border-radius: 12px; padding: 16px 12px; text-align: center; cursor: pointer; transition: all 0.2s;
        }
        .add-bookmark:hover { border-color: #e94560; background: rgba(233,69,96,0.08); }
        .add-bookmark .icon { font-size: 28px; margin-bottom: 8px; display: block; color: rgba(255,255,255,0.3); }
        .add-bookmark .title { font-size: 11px; color: rgba(255,255,255,0.3); }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-box { background: #1a1a2e; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 24px; width: 360px; }
        .modal-box h3 { margin-bottom: 16px; font-size: 16px; }
        .modal-box input { width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .btn-row { display: flex; gap: 8px; }
        .btn-row button { flex: 1; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        ''' + RESPONSIVE_CSS + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("startpage") + '''
    <div class="main">
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="搜索或输入网址..." onkeydown="if(event.key==='Enter'){var v=this.value;if(v.startsWith('http'))window.open(v);else window.open('https://www.google.com/search?q='+v)}">
        </div>
        <div class="bookmarks" id="bookmarksContainer"></div>
    </div>
    <div class="modal" id="addModal">
        <div class="modal-box">
            <h3>添加书签</h3>
            <input type="text" id="bmTitle" placeholder="标题">
            <input type="text" id="bmUrl" placeholder="网址">
            <input type="text" id="bmIcon" placeholder="图标 (emoji)">
            <input type="text" id="bmCategory" placeholder="分类">
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal()">取消</button>
                <button class="btn-primary" onclick="saveBookmark()">保存</button>
            </div>
        </div>
    </div>
    <script>
        var bookmarks = {{ bookmarks | tojson }};
        function render() {
            var c = document.getElementById('bookmarksContainer');
            var cats = {};
            bookmarks.forEach(function(bm) { var cat = bm.category || '未分类'; if (!cats[cat]) cats[cat] = []; cats[cat].push(bm); });
            var html = '';
            for (var cat in cats) {
                html += '<div class="category"><div class="category-title">' + cat + '</div><div class="bookmark-grid">';
                cats[cat].forEach(function(bm) {
                    html += '<a href="' + bm.url + '" class="bookmark" target="_blank"><button class="delete" onclick="event.preventDefault();deleteBookmark(\\'' + bm.id + '\\')">×</button><span class="icon">' + (bm.icon||'🔗') + '</span><span class="title">' + bm.title + '</span></a>';
                });
                html += '<div class="add-bookmark" onclick="openModal()"><span class="icon">+</span><span class="title">添加</span></div></div></div>';
            }
            c.innerHTML = html;
        }
        function openModal() { document.getElementById('addModal').classList.add('active'); }
        function closeModal() { document.getElementById('addModal').classList.remove('active'); }
        async function saveBookmark() {
            var data = { title: document.getElementById('bmTitle').value, url: document.getElementById('bmUrl').value, icon: document.getElementById('bmIcon').value||'🔗', category: document.getElementById('bmCategory').value||'未分类' };
            await fetch('/api/bookmarks', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
            location.reload();
        }
        async function deleteBookmark(id) { await fetch('/api/bookmarks/'+id, {method:'DELETE'}); location.reload(); }
        render();
    </script>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 文件管理
# ============================================================================

FILES_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件 - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .container { max-width: 1000px; margin: 0 auto; padding: 24px; }
        .breadcrumb { margin-bottom: 16px; font-size: 13px; }
        .breadcrumb a { color: #e94560; text-decoration: none; }
        .upload-area {
            border: 2px dashed rgba(255,255,255,0.15); border-radius: 12px;
            padding: 30px; text-align: center; margin-bottom: 20px; cursor: pointer; transition: all 0.2s;
        }
        .upload-area:hover { border-color: #e94560; background: rgba(233,69,96,0.08); }
        .upload-area input { display: none; }
        .upload-area p { color: rgba(255,255,255,0.5); font-size: 14px; }
        .file-list { background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; }
        .file-item {
            display: flex; align-items: center; padding: 12px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;
        }
        .file-item:hover { background: rgba(255,255,255,0.05); }
        .file-item:last-child { border: none; }
        .file-icon { font-size: 20px; margin-right: 12px; width: 28px; text-align: center; }
        .file-name { flex: 1; font-size: 14px; }
        .file-name a { color: #fff; text-decoration: none; }
        .file-name a:hover { color: #e94560; }
        .file-meta { color: rgba(255,255,255,0.3); font-size: 12px; margin-right: 12px; }
        .file-actions { display: flex; gap: 6px; }
        .action-btn {
            padding: 6px 10px; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
            background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.7); cursor: pointer;
            font-size: 12px; text-decoration: none; transition: all 0.2s;
        }
        .action-btn:hover { background: rgba(233,69,96,0.2); border-color: rgba(233,69,96,0.4); color: #fff; }
        .action-btn.danger:hover { background: rgba(233,69,96,0.3); }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-box { background: #1a1a2e; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 24px; width: 360px; }
        .modal-box h3 { margin-bottom: 16px; font-size: 16px; }
        .modal-box input { width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .btn-row { display: flex; gap: 8px; }
        .btn-row button { flex: 1; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .share-url { padding: 10px; background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); border-radius: 8px; word-break: break-all; font-size: 12px; margin-top: 10px; }
        ''' + RESPONSIVE_CSS + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("files") + '''
    <div class="container">
        <div class="breadcrumb"><a href="/files">根目录</a>{% if current_path %} / {{ current_path }}{% endif %}</div>
        <div class="upload-area" onclick="document.getElementById('fileInput').click()">
            <input type="file" id="fileInput" onchange="uploadFile(this)">
            <p>点击或拖拽上传文件</p>
        </div>
        <div class="file-list">
            {% if current_path %}
            <div class="file-item"><span class="file-icon">📂</span><div class="file-name"><a href="/files">.. 返回上级</a></div></div>
            {% endif %}
            {% for item in items %}
            <div class="file-item">
                <span class="file-icon">{{ '📂' if item.is_dir else '📄' }}</span>
                <div class="file-name"><a href="/files/{{ item.path }}">{{ item.name }}</a></div>
                <div class="file-meta">{{ item.modified }}{% if not item.is_dir %} | {{ "%.1f"|format(item.size / 1024) }}KB{% endif %}</div>
                <div class="file-actions">
                    {% if not item.is_dir %}
                    <a href="/preview/{{ item.path }}" class="action-btn" target="_blank">预览</a>
                    <a href="/download/{{ item.path }}" class="action-btn">下载</a>
                    <button class="action-btn" onclick="renameFile('{{ item.path }}', '{{ item.name }}')">重命名</button>
                    <button class="action-btn" onclick="shareFile('{{ item.path }}')">分享</button>
                    <button class="action-btn danger" onclick="deleteFile('{{ item.path }}')">删除</button>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
            {% if not items %}
            <div class="file-item"><div class="file-name" style="text-align:center;color:rgba(255,255,255,0.3);">暂无文件</div></div>
            {% endif %}
        </div>
    </div>
    <div class="modal" id="renameModal">
        <div class="modal-box">
            <h3>重命名</h3>
            <input type="text" id="newName" placeholder="新文件名">
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('renameModal')">取消</button>
                <button class="btn-primary" onclick="doRename()">确定</button>
            </div>
        </div>
    </div>
    <div class="modal" id="shareModal">
        <div class="modal-box">
            <h3>分享链接</h3>
            <div class="share-url" id="shareUrl">生成中...</div>
            <div class="btn-row" style="margin-top:12px">
                <button class="btn-primary" onclick="copyShare()">复制链接</button>
                <button class="btn-secondary" onclick="closeModal('shareModal')">关闭</button>
            </div>
        </div>
    </div>
    <script>
        var currentPath = '';
        async function uploadFile(input) {
            var file = input.files[0]; if (!file) return;
            var fd = new FormData(); fd.append('file', file);
            await fetch('/api/upload', {method:'POST', body:fd});
            location.reload();
        }
        async function deleteFile(path) {
            if (!confirm('确定删除 ' + path + '？')) return;
            await fetch('/api/delete/' + path, {method:'DELETE'});
            location.reload();
        }
        function renameFile(path, name) {
            currentPath = path;
            document.getElementById('newName').value = name;
            document.getElementById('renameModal').classList.add('active');
        }
        async function doRename() {
            var name = document.getElementById('newName').value;
            await fetch('/api/rename/' + currentPath, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name})});
            closeModal('renameModal'); location.reload();
        }
        async function shareFile(path) {
            document.getElementById('shareModal').classList.add('active');
            document.getElementById('shareUrl').textContent = '生成中...';
            var r = await fetch('/api/share/' + path, {method:'POST'});
            var d = await r.json();
            if (d.success) { document.getElementById('shareUrl').textContent = window.location.origin + d.url; }
        }
        function copyShare() {
            var text = document.getElementById('shareUrl').textContent;
            navigator.clipboard.writeText(text); alert('已复制');
        }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
    </script>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 笔记列表
# ============================================================================

NOTES_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>笔记 - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .container { max-width: 900px; margin: 0 auto; padding: 24px; }
        .toolbar { display: flex; gap: 10px; margin-bottom: 20px; }
        .toolbar input { flex: 1; padding: 10px 14px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .toolbar input:focus { border-color: #e94560; }
        .btn { padding: 10px 16px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-primary:hover { background: #c23152; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; text-decoration: none; display: inline-flex; align-items: center; }
        .note-list { display: grid; gap: 12px; }
        .note-card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 16px 20px; transition: all 0.2s;
        }
        .note-card:hover { border-color: rgba(233,69,96,0.3); }
        .note-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .note-title { font-size: 16px; font-weight: 500; }
        .note-title a { color: #fff; text-decoration: none; }
        .note-title a:hover { color: #e94560; }
        .note-meta { color: rgba(255,255,255,0.3); font-size: 12px; }
        .note-actions { display: flex; gap: 6px; }
        .action-btn {
            padding: 6px 10px; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
            background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.7); cursor: pointer;
            font-size: 12px; text-decoration: none; transition: all 0.2s;
        }
        .action-btn:hover { background: rgba(233,69,96,0.2); border-color: rgba(233,69,96,0.4); color: #fff; }
        .action-btn.danger:hover { background: rgba(233,69,96,0.3); }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-box { background: #1a1a2e; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 24px; width: 500px; max-height: 80vh; overflow-y: auto; }
        .modal-box h3 { margin-bottom: 16px; font-size: 16px; }
        .modal-box input, .modal-box textarea { width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .modal-box textarea { min-height: 200px; font-family: monospace; resize: vertical; }
        .btn-row { display: flex; gap: 8px; }
        .btn-row button { flex: 1; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; }
        .share-url { padding: 10px; background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); border-radius: 8px; word-break: break-all; font-size: 12px; margin-top: 10px; }
        ''' + RESPONSIVE_CSS + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("notes") + '''
    <div class="container">
        <div class="toolbar">
            <form action="/notes" method="GET" style="display:flex;gap:10px;flex:1">
                <input type="text" name="q" value="{{ query }}" placeholder="搜索笔记...">
                <button type="submit" class="btn btn-primary">搜索</button>
                {% if query %}<a href="/notes" class="btn btn-secondary">清除</a>{% endif %}
            </form>
            <button class="btn btn-primary" onclick="openModal('createModal')">+ 新建</button>
        </div>
        <div class="note-list">
            {% for note in notes %}
            <div class="note-card">
                <div class="note-header">
                    <div>
                        <div class="note-title"><a href="/notes/{{ note.id }}">{{ note.title }}</a></div>
                        <div class="note-meta">{{ note.created }}</div>
                    </div>
                    <div class="note-actions">
                        <a href="/notes/{{ note.id }}" class="action-btn">预览</a>
                        <a href="/api/notes/{{ note.id }}/download" class="action-btn">下载</a>
                        <button class="action-btn" onclick="renameNote('{{ note.id }}', '{{ note.title }}')">重命名</button>
                        <button class="action-btn" onclick="shareNote('{{ note.id }}')">分享</button>
                        <button class="action-btn danger" onclick="deleteNote('{{ note.id }}')">删除</button>
                    </div>
                </div>
            </div>
            {% endfor %}
            {% if not notes %}
            <div style="text-align:center;padding:40px;color:rgba(255,255,255,0.3);">暂无笔记</div>
            {% endif %}
        </div>
    </div>
    <div class="modal" id="createModal">
        <div class="modal-box">
            <h3>新建笔记</h3>
            <input type="text" id="noteTitle" placeholder="标题">
            <textarea id="noteContent" placeholder="内容 (支持Markdown)"></textarea>
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('createModal')">取消</button>
                <button class="btn-primary" onclick="createNote()">创建</button>
            </div>
        </div>
    </div>
    <div class="modal" id="renameModal">
        <div class="modal-box">
            <h3>重命名笔记</h3>
            <input type="text" id="newTitle" placeholder="新标题">
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('renameModal')">取消</button>
                <button class="btn-primary" onclick="doRenameNote()">确定</button>
            </div>
        </div>
    </div>
    <div class="modal" id="shareModal">
        <div class="modal-box">
            <h3>分享链接</h3>
            <div class="share-url" id="shareUrl">生成中...</div>
            <div class="btn-row" style="margin-top:12px">
                <button class="btn-primary" onclick="copyShare()">复制链接</button>
                <button class="btn-secondary" onclick="closeModal('shareModal')">关闭</button>
            </div>
        </div>
    </div>
    <script>
        var currentNoteId = '';
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        async function createNote() {
            var title = document.getElementById('noteTitle').value;
            var content = document.getElementById('noteContent').value;
            await fetch('/api/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:title, content:content})});
            closeModal('createModal'); location.reload();
        }
        async function deleteNote(id) {
            if (!confirm('确定删除此笔记？')) return;
            await fetch('/api/notes/' + id, {method:'DELETE'}); location.reload();
        }
        function renameNote(id, title) {
            currentNoteId = id;
            document.getElementById('newTitle').value = title;
            openModal('renameModal');
        }
        async function doRenameNote() {
            var title = document.getElementById('newTitle').value;
            await fetch('/api/notes/' + currentNoteId + '/rename', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:title})});
            closeModal('renameModal'); location.reload();
        }
        async function shareNote(id) {
            openModal('shareModal');
            document.getElementById('shareUrl').textContent = '生成中...';
            var r = await fetch('/api/notes/' + id + '/share', {method:'POST'});
            var d = await r.json();
            if (d.success) document.getElementById('shareUrl').textContent = window.location.origin + d.url;
        }
        function copyShare() { navigator.clipboard.writeText(document.getElementById('shareUrl').textContent); alert('已复制'); }
    </script>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 笔记详情
# ============================================================================

NOTE_DETAIL_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .container { max-width: 800px; margin: 0 auto; padding: 24px; }
        .note-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .note-title { font-size: 24px; font-weight: 600; }
        .note-actions { display: flex; gap: 8px; }
        .action-btn {
            padding: 8px 14px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px;
            background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.7); cursor: pointer;
            font-size: 13px; text-decoration: none; transition: all 0.2s;
        }
        .action-btn:hover { background: rgba(233,69,96,0.2); border-color: rgba(233,69,96,0.4); color: #fff; }
        .content {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 24px; white-space: pre-wrap; line-height: 1.8; font-size: 14px;
        }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-box { background: #1a1a2e; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 24px; width: 360px; }
        .modal-box h3 { margin-bottom: 16px; font-size: 16px; }
        .modal-box input { width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .btn-row { display: flex; gap: 8px; }
        .btn-row button { flex: 1; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .share-url { padding: 10px; background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); border-radius: 8px; word-break: break-all; font-size: 12px; margin-top: 10px; }
        ''' + RESPONSIVE_CSS + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("") + '''
    <div class="container">
        <div class="note-header">
            <div class="note-title">{{ title }}</div>
            <div class="note-actions">
                <a href="/api/notes/{{ note_id }}/download" class="action-btn">下载</a>
                <button class="action-btn" onclick="renameNote()">重命名</button>
                <button class="action-btn" onclick="shareNote()">分享</button>
                <button class="action-btn" onclick="deleteNote()">删除</button>
                <a href="/notes" class="action-btn">返回列表</a>
            </div>
        </div>
        <div class="content">{{ content }}</div>
    </div>
    <div class="modal" id="renameModal">
        <div class="modal-box">
            <h3>重命名笔记</h3>
            <input type="text" id="newTitle" value="{{ title }}" placeholder="新标题">
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('renameModal')">取消</button>
                <button class="btn-primary" onclick="doRename()">确定</button>
            </div>
        </div>
    </div>
    <div class="modal" id="shareModal">
        <div class="modal-box">
            <h3>分享链接</h3>
            <div class="share-url" id="shareUrl">生成中...</div>
            <div class="btn-row" style="margin-top:12px">
                <button class="btn-primary" onclick="copyShare()">复制链接</button>
                <button class="btn-secondary" onclick="closeModal('shareModal')">关闭</button>
            </div>
        </div>
    </div>
    <script>
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        async function deleteNote() {
            if (!confirm('确定删除此笔记？')) return;
            await fetch('/api/notes/{{ note_id }}', {method:'DELETE'});
            window.location = '/notes';
        }
        function renameNote() { openModal('renameModal'); }
        async function doRename() {
            var title = document.getElementById('newTitle').value;
            await fetch('/api/notes/{{ note_id }}/rename', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:title})});
            location.reload();
        }
        async function shareNote() {
            openModal('shareModal');
            document.getElementById('shareUrl').textContent = '生成中...';
            var r = await fetch('/api/notes/{{ note_id }}/share', {method:'POST'});
            var d = await r.json();
            if (d.success) document.getElementById('shareUrl').textContent = window.location.origin + d.url;
        }
        function copyShare() { navigator.clipboard.writeText(document.getElementById('shareUrl').textContent); alert('已复制'); }
    </script>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 分享笔记页面（无需登录）
# ============================================================================

SHARED_NOTE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - 分享</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        .header { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 16px 24px; text-align: center; }
        .header h1 { font-size: 18px; }
        .header p { color: rgba(255,255,255,0.4); font-size: 12px; margin-top: 4px; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 24px; }
        .content { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 24px; white-space: pre-wrap; line-height: 1.8; font-size: 14px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <p>由 Private Hub 分享</p>
    </div>
    <div class="container">
        <div class="content">{{ content }}</div>
    </div>
</body>
</html>'''


# ============================================================================
# HTML模板 - 修改密码
# ============================================================================

CHANGE_PWD_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>修改密码 - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .container { max-width: 400px; margin: 40px auto; padding: 0 24px; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 24px; }
        .card h2 { margin-bottom: 20px; font-size: 18px; }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; margin-bottom: 6px; color: rgba(255,255,255,0.5); font-size: 12px; }
        .form-group input { width: 100%; padding: 10px 14px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .form-group input:focus { border-color: #e94560; }
        .btn { width: 100%; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-primary:hover { background: #c23152; }
        .error { color: #ff6b6b; font-size: 13px; margin-bottom: 12px; }
        .success { color: #00b894; font-size: 13px; margin-bottom: 12px; }
        ''' + RESPONSIVE_CSS + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("password") + '''
    <div class="container">
        <div class="card">
            <h2>修改密码</h2>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            {% if success %}<div class="success">{{ success }}</div>{% endif %}
            <form method="POST">
                <div class="form-group"><label>原密码</label><input type="password" name="old_password" required></div>
                <div class="form-group"><label>新密码</label><input type="password" name="new_password" required></div>
                <div class="form-group"><label>确认新密码</label><input type="password" name="confirm_password" required></div>
                <button type="submit" class="btn btn-primary">确认修改</button>
            </form>
        </div>
    </div>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 用户管理
# ============================================================================

ADMIN_USERS_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>用户管理 - Private Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #fff; }
        ''' + NAV_CSS + '''
        .container { max-width: 900px; margin: 0 auto; padding: 24px; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 24px; margin-bottom: 16px; }
        .card h2 { margin-bottom: 16px; font-size: 16px; }
        .form-row { display: flex; gap: 8px; margin-bottom: 16px; }
        .form-row input, .form-row select { flex: 1; padding: 10px 14px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(255,255,255,0.08); color: #fff; font-size: 13px; outline: none; }
        .form-row select option { background: #1a1a2e; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }
        th { color: rgba(255,255,255,0.4); font-size: 12px; text-transform: uppercase; }
        .role-admin { color: #e94560; }
        .role-user { color: #00b894; }
        .action-btn {
            padding: 6px 10px; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
            background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.7); cursor: pointer;
            font-size: 12px; transition: all 0.2s; margin-right: 4px;
        }
        .action-btn:hover { background: rgba(233,69,96,0.2); color: #fff; }
        .action-btn.primary { background: #e94560; color: #fff; border-color: #e94560; }
        .msg { padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 12px; }
        .msg.error { background: rgba(233,69,96,0.15); color: #ff6b6b; }
        .msg.success { background: rgba(0,184,148,0.15); color: #00b894; }
        ''' + RESPONSIVE_CSS + WATERMARK_CSS + '''
    </style>
</head>
<body>
    ''' + nav_html("users") + '''
    <div class="container">
        <div class="card">
            <h2>添加用户</h2>
            <div id="msg"></div>
            <div class="form-row">
                <input type="text" id="newUsername" placeholder="用户名">
                <input type="password" id="newPassword" placeholder="密码">
                <select id="newRole"><option value="user">普通用户</option><option value="admin">管理员</option></select>
                <button class="action-btn primary" onclick="addUser()">添加</button>
            </div>
        </div>
        <div class="card">
            <h2>用户列表</h2>
            <table>
                <thead><tr><th>用户名</th><th>角色</th><th>创建时间</th><th>操作</th></tr></thead>
                <tbody>
                    {% for username, user in users.items() %}
                    <tr>
                        <td>{{ username }}</td>
                        <td class="role-{{ user.role }}">{{ '管理员' if user.role == 'admin' else '用户' }}</td>
                        <td>{{ user.created_at }}</td>
                        <td>
                            {% if username != '001' %}
                            <button class="action-btn" onclick="resetPassword('{{ username }}')">重置密码</button>
                            <button class="action-btn" onclick="deleteUser('{{ username }}')">删除</button>
                            {% else %}
                            <span style="color:rgba(255,255,255,0.2)">-</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    <script>
        function showMsg(text, type) { var m = document.getElementById('msg'); m.textContent = text; m.className = 'msg ' + type; setTimeout(function(){ m.className = 'msg'; }, 3000); }
        async function addUser() {
            var fd = new FormData(); fd.append('username', document.getElementById('newUsername').value); fd.append('password', document.getElementById('newPassword').value); fd.append('role', document.getElementById('newRole').value);
            var r = await fetch('/admin/users/add', {method:'POST', body:fd}); var d = await r.json();
            if (d.success) location.reload(); else showMsg(d.error, 'error');
        }
        async function deleteUser(u) { if (!confirm('确定删除 ' + u + '？')) return; await fetch('/admin/users/' + u, {method:'DELETE'}); location.reload(); }
        async function resetPassword(u) { var r = await fetch('/admin/users/' + u + '/reset-password', {method:'POST'}); var d = await r.json(); if (d.success) alert('新密码: ' + d.password); }
    </script>
    <script>''' + WATERMARK_JS + '''</script>
</body>
</html>'''


# ============================================================================
# HTML模板 - 文件预览
# ============================================================================

PREVIEW_TEXT_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ filename }} - 预览</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Consolas', 'Monaco', monospace; color: #fff; }
        .header { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 14px; color: #e94560; }
        .header a { color: rgba(255,255,255,0.6); text-decoration: none; padding: 6px 12px; background: rgba(255,255,255,0.08); border-radius: 6px; font-size: 12px; }
        .header a:hover { background: rgba(255,255,255,0.15); }
        .content { max-width: 1000px; margin: 24px auto; padding: 24px; background: rgba(255,255,255,0.05); border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); }
        pre { white-space: pre-wrap; word-wrap: break-word; line-height: 1.6; font-size: 13px; color: rgba(255,255,255,0.8); }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ filename }}</h1>
        <div><a href="/download/{{ filename }}">下载</a> <a href="/files">返回</a></div>
    </div>
    <div class="content"><pre>{{ content }}</pre></div>
</body>
</html>'''


# ============================================================================
# 启动
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("HUB_PORT", os.environ.get("PORT", 8888)))
    app.run(host="0.0.0.0", port=port, debug=False)
