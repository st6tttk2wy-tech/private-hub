# -*- coding: utf-8 -*-
"""
私密中心 (Private Hub)
"""

import os
import sys
import json
import hashlib
import secrets
import platform
import shutil
import threading
import time
import requests
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

LOGS_DIR = PERSISTENT_DIR / "logs"
NEWS_DIR = PERSISTENT_DIR / "news"

for d in [CONFIG_DIR, DATA_DIR, FILES_DIR, NOTES_DIR, LOGS_DIR, NEWS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = CONFIG_DIR / "auth.json"
USERS_FILE = CONFIG_DIR / "users.json"
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"
NOTES_INDEX = DATA_DIR / "notes_index.json"
OPS_LOG_FILE = LOGS_DIR / "operations.json"
NEWS_FILE = NEWS_DIR / "daily_news.json"
CONFIG_SETTINGS_FILE = CONFIG_DIR / "settings.json"



NEWS_SOURCES = {
    "weibo": {"name": "微博", "icon": "🔥", "api": "https://api.vvhan.com/api/hotlist/weibo"},
    "douyin": {"name": "抖音", "icon": "🎵", "api": "https://api.vvhan.com/api/hotlist/douyin"},
    "toutiao": {"name": "今日头条", "icon": "📰", "api": "https://api.vvhan.com/api/hotlist/toutiao"},
    "zhihu": {"name": "知乎", "icon": "💡", "api": "https://api.vvhan.com/api/hotlist/zhihuHot"},
    "bilibili": {"name": "B站", "icon": "📺", "api": "https://api.vvhan.com/api/hotlist/bili"},
    "baidu": {"name": "百度", "icon": "🔍", "api": "https://api.vvhan.com/api/hotlist/baiduRD"},
}

WATERMARK_CSS = '''
.watermark {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 9999; overflow: hidden;
}
.watermark span {
    position: absolute; font-size: 16px; color: rgba(255,255,255,0.03);
    transform: rotate(-30deg); white-space: nowrap; user-select: none;
}
'''

WATERMARK_JS = '''
function createWatermark(text) {
    var container = document.createElement('div');
    container.className = 'watermark';
    document.body.appendChild(container);
    for (var i = 0; i < 50; i++) {
        var span = document.createElement('span');
        span.textContent = text;
        span.style.left = (Math.random() * 100) + '%';
        span.style.top = (Math.random() * 100) + '%';
        container.appendChild(span);
    }
}
createWatermark('Private Hub');
'''



def load_ops_log():
    if OPS_LOG_FILE.exists():
        try:
            return json.loads(OPS_LOG_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return []

def save_ops_log(logs):
    OPS_LOG_FILE.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")

def add_log(action, detail="", user=None, reversible=False, reverse_data=None):
    logs = load_ops_log()
    logs.append({
        "id": secrets.token_hex(8),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user or session.get("username", "system"),
        "action": action,
        "detail": detail,
        "reversible": reversible,
        "reverse_data": reverse_data
    })
    if len(logs) > 500:
        logs = logs[-500:]
    save_ops_log(logs)

def load_news():
    if NEWS_FILE.exists():
        try:
            return json.loads(NEWS_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}

def save_news(data):
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_config_settings():
    if CONFIG_SETTINGS_FILE.exists():
        try:
            return json.loads(CONFIG_SETTINGS_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {"auto_news": True, "news_hour": 8, "news_minute": 0}

def save_config_settings(settings):
    CONFIG_SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_news():
    print("开始收集新闻...")
    all_news = {}
    for source_id, source in NEWS_SOURCES.items():
        try:
            resp = requests.get(source["api"], timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    items = data.get("data", [])[:20]
                    all_news[source_id] = {
                        "name": source["name"],
                        "icon": source["icon"],
                        "items": items,
                        "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
        except Exception as e:
            print(f"  [{source['name']}] 失败: {e}")
    if all_news:
        save_news(all_news)
    print("新闻收集完成")

def news_scheduler():
    while True:
        now = datetime.now()
        settings = load_config_settings()
        if now.hour == settings.get("news_hour", 8) and now.minute == settings.get("news_minute", 0):
            fetch_news()
            time.sleep(61)
        else:
            time.sleep(30)

# 启动新闻收集线程
news_thread = threading.Thread(target=news_scheduler, daemon=True)
news_thread.start()


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
            # 确保默认管理员账号存在
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



def get_nav(active=""):
    user = get_current_user()
    is_adm = user and user.get("role") == "admin"
    links = [
        ("/", "首页", "home"),
        ("/news", "信息管理", "news"),
        ("/data", "数据管理", "data"),
        ("/files", "文件管理", "files"),
        ("/notes", "笔记管理", "notes"),
    ]
    if is_adm:
        links.append(("/admin/users", "用户管理", "users"))
    links.extend([
        ("/change-password", "密码管理", "password"),
        ("/logout", "退出", "logout"),
    ])
    html = '<nav><div class="logo">Private Hub</div><div class="links">'
    for url, name, key in links:
        cls = ' class="active"' if key == active else ''
        html += '<a href="' + url + '"' + cls + '>' + name + '</a>'
    html += '</div></nav>'
    return html

def has_permission(perm):
    user = get_current_user()
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    perms = user.get("permissions", [])
    return "all" in perm or perm in perms


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


# ============================================================================
# 路由
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
            return redirect(url_for("dashboard"))
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
    return render_template_string(CHANGE_PWD_HTML, error=error, success=success, nav=get_nav("password"))


@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = load_users()
    return render_template_string(ADMIN_USERS_HTML, users=users, current_user=session.get("username"), nav=get_nav("users"))


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


@app.route("/data")
@login_required
def data_module():
    return render_template_string(DATA_HTML, nav=get_nav("data"))


@app.route("/")
@login_required
def home():
    return render_template_string(DASHBOARD_HTML)



@app.route("/news")
@login_required
def news_page():
    news = load_news()
    settings = load_config_settings()
    return render_template_string(NEWS_HTML, news=news, settings=settings, sources=NEWS_SOURCES, nav=get_nav("news"), is_admin=is_admin)

@app.route("/api/news/refresh", methods=["POST"])
@login_required
def refresh_news():
    fetch_news()
    return jsonify({"success": True})

@app.route("/api/news/settings", methods=["POST"])
@login_required
def update_news_settings():
    settings = load_config_settings()
    settings["auto_news"] = request.json.get("auto_news", settings.get("auto_news", True))
    settings["news_hour"] = int(request.json.get("news_hour", settings.get("news_hour", 8)))
    settings["news_minute"] = int(request.json.get("news_minute", settings.get("news_minute", 0)))
    save_config_settings(settings)
    return jsonify({"success": True})

@app.route("/logs")
@login_required
def logs_page():
    logs = load_ops_log()
    logs.reverse()
    return render_template_string(LOGS_HTML, logs=logs, nav=get_nav("logs"))

@app.route("/api/logs/undo/<log_id>", methods=["POST"])
@login_required
def undo_log(log_id):
    logs = load_ops_log()
    log_entry = None
    for log in logs:
        if log.get("id") == log_id:
            log_entry = log
            break
    if not log_entry:
        return jsonify({"error": "日志不存在"}), 404
    if not log_entry.get("reversible"):
        return jsonify({"error": "此操作不可撤销"}), 400
    log_entry["undone"] = True
    log_entry["undone_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_ops_log(logs)
    return jsonify({"success": True})


@app.route("/startpage")
@login_required
def startpage():
    bookmarks = load_bookmarks()
    return render_template_string(STARTPAGE_HTML, bookmarks=bookmarks, nav=get_nav("startpage"))


@app.route("/files")
@app.route("/files/<path:filepath>")
@login_required
def files(filepath=None):
    if filepath is None:
        filepath = ""
    base_path = FILES_DIR / filepath
    if not base_path.exists() or not str(base_path).startswith(str(FILES_DIR)):
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
    
    return render_template_string(FILES_HTML, items=items, current_path=filepath, nav=get_nav("files"))


@app.route("/download/<path:filepath>")
@login_required
def download(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not str(file_path).startswith(str(FILES_DIR)) or file_path.is_dir():
        abort(404)
    return send_file(file_path, as_attachment=True)


@app.route("/preview/<path:filepath>")
@login_required
def preview(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not str(file_path).startswith(str(FILES_DIR)) or file_path.is_dir():
        abort(404)
    
    file_size = file_path.stat().st_size
    ext = file_path.suffix.lower()
    
    MAX_PREVIEW_SIZE = 500 * 1024  # 500KB
    text_exts = ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.log', '.ini', '.cfg', '.yml', '.yaml']
    img_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']
    
    if ext in img_exts:
        return send_file(file_path)
    elif ext in text_exts:
        if file_size > MAX_PREVIEW_SIZE:
            content = file_path.read_text(encoding="utf-8", errors="replace")[:MAX_PREVIEW_SIZE] + "\n\n... (文件过大，仅显示前500KB)"
        else:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        return render_template_string(PREVIEW_TEXT_HTML, content=content, filename=filepath, ext=ext)
    elif ext == '.pdf':
        return send_file(file_path, mimetype='application/pdf')
    else:
        if file_size > MAX_PREVIEW_SIZE:
            return send_file(file_path, as_attachment=True)
        content = file_path.read_bytes()[:MAX_PREVIEW_SIZE]
        try:
            text = content.decode("utf-8", errors="replace")
            return render_template_string(PREVIEW_TEXT_HTML, content=text, filename=filepath, ext=ext)
        except:
            return send_file(file_path, as_attachment=True)


@app.route("/api/delete/<path:filepath>", methods=["DELETE"])
@login_required
def api_delete_file(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not str(file_path).startswith(str(FILES_DIR)):
        return jsonify({"error": "文件不存在"}), 404
    if file_path.is_dir():
        import shutil
        shutil.rmtree(file_path)
    else:
        file_path.unlink()
    return jsonify({"success": True})


@app.route("/api/rename/<path:filepath>", methods=["POST"])
@login_required
def api_rename_file(filepath):
    file_path = FILES_DIR / filepath
    if not file_path.exists() or not str(file_path).startswith(str(FILES_DIR)):
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
    if not file_path.exists() or not str(file_path).startswith(str(FILES_DIR)):
        return jsonify({"error": "文件不存在"}), 404
    token = secrets.token_urlsafe(16)
    shares_file = CONFIG_DIR / "shares.json"
    shares = {}
    if shares_file.exists():
        try:
            shares = json.loads(shares_file.read_text(encoding="utf-8"))
        except:
            pass
    shares[token] = {"path": filepath, "type": "file", "created": datetime.now().isoformat()}
    shares_file.write_text(json.dumps(shares, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"success": True, "token": token, "url": f"/s/{token}"})


@app.route("/s/<token>")
def shared_file(token):
    shares_file = CONFIG_DIR / "shares.json"
    if not shares_file.exists():
        abort(404)
    shares = json.loads(shares_file.read_text(encoding="utf-8"))
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
    return render_template_string(NOTES_HTML, notes=notes_list, query=query, nav=get_nav("notes"))


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
    return render_template_string(NOTE_DETAIL_HTML, content=content, note_id=note_id, title=title, nav=get_nav("notes"))


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


@app.route("/api/notes/<note_id>/edit", methods=["POST"])
@login_required
def api_edit_note(note_id):
    note_file = NOTES_DIR / f"{note_id}.md"
    if not note_file.exists():
        return jsonify({"error": "笔记不存在"}), 404
    content = request.json.get("content", "")
    note_file.write_text(content, encoding="utf-8")
    return jsonify({"success": True})


@app.route("/api/notes/<note_id>/share", methods=["POST"])
@login_required
def api_share_note(note_id):
    notes_index = load_notes_index()
    note = next((n for n in notes_index if n["id"] == note_id), None)
    if not note:
        return jsonify({"error": "笔记不存在"}), 404
    token = secrets.token_urlsafe(16)
    shares_file = CONFIG_DIR / "shares.json"
    shares = {}
    if shares_file.exists():
        try:
            shares = json.loads(shares_file.read_text(encoding="utf-8"))
        except:
            pass
    shares[token] = {"type": "note", "note_id": note_id, "title": note["title"], "created": datetime.now().isoformat()}
    shares_file.write_text(json.dumps(shares, ensure_ascii=False, indent=2), encoding="utf-8")
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


@app.route("/api/data/import", methods=["POST"])
@login_required
def api_data_import():
    data = request.json
    if not data:
        return jsonify({"error": "无效的数据"}), 400
    
    if "bookmarks" in data:
        save_bookmarks(data["bookmarks"])
    
    if "notes" in data:
        for note in data["notes"]:
            note_id = note.get("id")
            if note_id:
                note_file = NOTES_DIR / f"{note_id}.md"
                if not note_file.exists():
                    note_file.write_text(note.get("content", ""), encoding="utf-8")
        save_notes_index(data["notes"])
    
    return jsonify({"success": True})


# ============================================================================
# 数据操作
# ============================================================================

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


DEFAULT_BOOKMARKS = [
    {"id": "github", "title": "GitHub", "url": "https://github.com", "icon": "🐙", "category": "开发"},
    {"id": "google", "title": "Google", "url": "https://google.com", "icon": "🔍", "category": "搜索"},
    {"id": "youtube", "title": "YouTube", "url": "https://youtube.com", "icon": "📺", "category": "娱乐"},
]


# ============================================================================
# HTML 模板
# ============================================================================

LOGIN_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            font-family: 'Microsoft YaHei', sans-serif;
        }
        .login-box {
            background: rgba(255,255,255,0.1); backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.2); border-radius: 20px;
            padding: 40px; width: 380px; text-align: center;
        }
        .login-box h1 { color: #fff; margin-bottom: 10px; font-size: 28px; }
        .login-box p { color: rgba(255,255,255,0.6); margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; text-align: left; }
        .input-group label { color: rgba(255,255,255,0.8); font-size: 14px; display: block; margin-bottom: 8px; }
        .input-group input {
            width: 100%; padding: 14px 18px; border: 1px solid rgba(255,255,255,0.2);
            border-radius: 10px; background: rgba(255,255,255,0.1); color: #fff;
            font-size: 16px; outline: none; transition: all 0.3s;
        }
        .input-group input:focus { border-color: #e94560; background: rgba(255,255,255,0.15); }
        .btn {
            width: 100%; padding: 14px; border: none; border-radius: 10px;
            background: linear-gradient(135deg, #e94560, #c23152); color: #fff;
            font-size: 16px; cursor: pointer; transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .error { color: #ff6b6b; margin-bottom: 15px; font-size: 14px; }
        .watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
        .watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐</h1>
        <p>私密中心</p>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="input-group">
                <label>用户名</label>
                <input type="text" name="username" placeholder="请输入用户名" autofocus>
            </div>
            <div class="input-group">
                <label>密码</label>
                <input type="password" name="password" placeholder="请输入密码">
            </div>
            <button type="submit" class="btn">登录</button>
        </form>
    </div>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            min-height: 100vh; background: #0f0f1a;
            font-family: 'Microsoft YaHei', sans-serif; color: #fff;
        }
        nav {
            background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 15px 30px; display: flex; justify-content: space-between; align-items: center;
        }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; transition: color 0.2s; }
        nav .links a:hover { color: #e94560; }
        .main-layout { display: flex; min-height: calc(100vh - 60px); }
        .sidebar {
            width: 200px; background: rgba(255,255,255,0.03); border-right: 1px solid rgba(255,255,255,0.08);
            padding: 20px 15px; flex-shrink: 0;
        }
        .sidebar-title { font-size: 12px; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; }
        .sidebar-link {
            display: flex; align-items: center; gap: 10px; padding: 12px 15px; margin-bottom: 5px;
            border-radius: 10px; text-decoration: none; color: rgba(255,255,255,0.7);
            transition: all 0.2s; font-size: 14px;
        }
        .sidebar-link:hover { background: rgba(233,69,96,0.15); color: #fff; }
        .sidebar-link .icon { font-size: 18px; }
        .container { flex: 1; padding: 30px; overflow-y: auto; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 25px; transition: transform 0.2s, border-color 0.2s;
        }
        .card:hover { transform: translateY(-3px); border-color: rgba(233,69,96,0.5); }
        .card h3 { color: #e94560; margin-bottom: 15px; font-size: 16px; }
        .stat { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .stat:last-child { border: none; }
        .stat .label { color: rgba(255,255,255,0.6); }
        .stat .value { font-weight: bold; }
        .progress-bar { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; margin-top: 8px; overflow: hidden; }
        .progress-fill { height: 100%; border-radius: 4px; transition: width 0.5s; }
        .progress-fill.green { background: linear-gradient(90deg, #00b894, #55efc4); }
        .progress-fill.yellow { background: linear-gradient(90deg, #fdcb6e, #f39c12); }
        .progress-fill.red { background: linear-gradient(90deg, #e94560, #ff6b6b); }
        .section-title { font-size: 18px; margin-bottom: 20px; color: rgba(255,255,255,0.9); }
        #time { font-size: 48px; font-weight: 300; text-align: center; margin: 20px 0; }
        #date { text-align: center; color: rgba(255,255,255,0.5); }
        .data-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }
        .data-card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 20px; text-align: center;
        }
        .data-card .icon { font-size: 28px; margin-bottom: 8px; }
        .data-card .count { font-size: 24px; font-weight: bold; color: #e94560; }
        .data-card .label { font-size: 12px; color: rgba(255,255,255,0.5); }
        .log-box { background: rgba(0,0,0,0.3); border-radius: 8px; padding: 15px; font-family: monospace; font-size: 13px; max-height: 200px; overflow-y: auto; color: rgba(255,255,255,0.7); }
        .log-entry { padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .log-time { color: rgba(255,255,255,0.4); margin-right: 10px; }
        .chart-card { grid-column: span 2; }
        .watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
        .watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">Private Hub</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/admin/users">用户管理</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="main-layout">
        <div class="sidebar">
            <div class="sidebar-title">快捷访问</div>
            <a href="/startpage" class="sidebar-link"><span class="icon">🚀</span>启动页</a>
            <a href="/files" class="sidebar-link"><span class="icon">📁</span>文件管理</a>
            <a href="/notes" class="sidebar-link"><span class="icon">📝</span>笔记</a>
            <a href="/change-password" class="sidebar-link"><span class="icon">🔑</span>修改密码</a>
            <a href="/admin/users" class="sidebar-link"><span class="icon">👥</span>用户管理</a>
            <a href="/data" class="sidebar-link"><span class="icon">📊</span>数据操作</a>
        </div>
        <div class="container">
            <div id="time"></div>
            <div id="date"></div>
            
            <div class="data-row" style="margin-top: 30px;">
                <div class="data-card"><div class="icon">🔗</div><div class="count" id="bm-val">--</div><div class="label">书签</div></div>
                <div class="data-card"><div class="icon">📝</div><div class="count" id="note-val">--</div><div class="label">笔记</div></div>
                <div class="data-card"><div class="icon">📁</div><div class="count" id="file-val">--</div><div class="label">文件</div></div>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>💻 CPU</h3>
                    <div id="cpu-info">加载中...</div>
                </div>
                <div class="card">
                    <h3>🧠 内存</h3>
                    <div id="mem-info">加载中...</div>
                </div>
                <div class="card">
                    <h3>💾 磁盘</h3>
                    <div id="disk-info">加载中...</div>
                </div>
                <div class="card">
                    <h3>ℹ️ 系统</h3>
                    <div id="sys-info">加载中...</div>
                </div>
                <div class="card chart-card">
                    <h3>📊 系统监控</h3>
                    <canvas id="usageChart" height="120"></canvas>
                </div>
                <div class="card">
                    <h3>📋 操作日志</h3>
                    <div class="log-box" id="log-box">
                        <div class="log-entry"><span class="log-time">--:--</span>系统启动</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        function updateTime() {
            const now = new Date();
            document.getElementById('time').textContent = now.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
            document.getElementById('date').textContent = now.toLocaleDateString('zh-CN', {year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'});
        }
        updateTime();
        setInterval(updateTime, 1000);
        
        function getProgressClass(percent) {
            if (percent > 80) return 'red';
            if (percent > 60) return 'yellow';
            return 'green';
        }
        
        function addLog(msg) {
            var now = new Date();
            var time = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
            var box = document.getElementById('log-box');
            box.innerHTML = '<div class="log-entry"><span class="log-time">' + time + '</span>' + msg + '</div>' + box.innerHTML;
        }
        
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
        
        async function loadSystemInfo() {
            try {
                const res = await fetch('/api/system');
                const data = await res.json();
                
                document.getElementById('cpu-info').innerHTML = `
                    <div class="stat"><span class="label">使用率</span><span class="value">${data.cpu_percent}%</span></div>
                    <div class="progress-bar"><div class="progress-fill ${getProgressClass(data.cpu_percent)}" style="width:${data.cpu_percent}%"></div></div>
                `;
                
                document.getElementById('mem-info').innerHTML = `
                    <div class="stat"><span class="label">已用</span><span class="value">${data.memory_used_gb}GB / ${data.memory_total_gb}GB</span></div>
                    <div class="progress-bar"><div class="progress-fill ${getProgressClass(data.memory_percent)}" style="width:${data.memory_percent}%"></div></div>
                `;
                
                document.getElementById('disk-info').innerHTML = `
                    <div class="stat"><span class="label">已用</span><span class="value">${data.disk_used_gb}GB / ${data.disk_total_gb}GB</span></div>
                    <div class="progress-bar"><div class="progress-fill ${getProgressClass(data.disk_percent)}" style="width:${data.disk_percent}%"></div></div>
                `;
                
                document.getElementById('sys-info').innerHTML = `
                    <div class="stat"><span class="label">系统</span><span class="value">${data.platform}</span></div>
                    <div class="stat"><span class="label">主机</span><span class="value">${data.hostname}</span></div>
                    <div class="stat"><span class="label">运行</span><span class="value">${data.uptime}</span></div>
                `;
                
                var t = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
                labels.push(t); cpuH.push(data.cpu_percent); memH.push(data.memory_percent); diskH.push(data.disk_percent);
                if (labels.length > 30) { labels.shift(); cpuH.shift(); memH.shift(); diskH.shift(); }
                chart.update();
            } catch(e) {
                console.error('加载系统信息失败:', e);
            }
        }
        
        async function loadStats() {
            try {
                var r = await fetch('/api/data/stats');
                var d = await r.json();
                document.getElementById('bm-val').textContent = d.bookmarks;
                document.getElementById('note-val').textContent = d.notes;
                document.getElementById('file-val').textContent = d.files;
            } catch(e) {}
        }
        
        loadSystemInfo();
        loadStats();
        setInterval(loadSystemInfo, 5000);
        setInterval(loadStats, 30000);
        addLog('加载首页');
    </script>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


STARTPAGE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>启动页 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh; display: flex; flex-direction: column;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            font-family: 'Microsoft YaHei', sans-serif; color: #fff;
        }
        nav {
            background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 15px 30px; display: flex; justify-content: space-between; align-items: center;
        }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .main { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; }
        .search-box { width: 100%; max-width: 600px; margin-bottom: 50px; }
        .search-box input {
            width: 100%; padding: 18px 24px; border: 1px solid rgba(255,255,255,0.2);
            border-radius: 15px; background: rgba(255,255,255,0.1); color: #fff;
            font-size: 18px; outline: none; backdrop-filter: blur(10px);
        }
        .search-box input:focus { border-color: #e94560; }
        .bookmarks { width: 100%; max-width: 900px; }
        .category { margin-bottom: 30px; }
        .category h3 { color: rgba(255,255,255,0.5); font-size: 14px; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 2px; }
        .bookmark-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 15px; }
        .bookmark {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 20px 15px; text-align: center; text-decoration: none; color: #fff;
            transition: all 0.2s; position: relative;
        }
        .bookmark:hover { background: rgba(233,69,96,0.2); border-color: #e94560; transform: translateY(-3px); }
        .bookmark .icon { font-size: 32px; margin-bottom: 10px; display: block; }
        .bookmark .title { font-size: 13px; color: rgba(255,255,255,0.8); }
        .bookmark .delete {
            position: absolute; top: 5px; right: 5px; width: 20px; height: 20px;
            background: rgba(233,69,96,0.8); border: none; border-radius: 50%;
            color: #fff; cursor: pointer; font-size: 12px; display: none;
        }
        .bookmark:hover .delete { display: block; }
        .add-bookmark {
            background: rgba(255,255,255,0.05); border: 2px dashed rgba(255,255,255,0.2);
            border-radius: 12px; padding: 20px 15px; text-align: center; cursor: pointer;
            transition: all 0.2s;
        }
        .add-bookmark:hover { border-color: #e94560; background: rgba(233,69,96,0.1); }
        .modal {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: #1a1a2e; border: 1px solid rgba(255,255,255,0.2);
            border-radius: 16px; padding: 30px; width: 400px;
        }
        .modal-content h3 { margin-bottom: 20px; }
        .modal-content input, .modal-content select {
            width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px; background: rgba(255,255,255,0.1); color: #fff; font-size: 14px;
        }
        .modal-content .btn-row { display: flex; gap: 10px; }
        .modal-content button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
        .watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">🚀 启动页</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/data">数据</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="main">
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="搜索或输入网址..." onkeydown="if(event.key==='Enter') window.open('https://www.google.com/search?q='+this.value)">
        </div>
        <div class="bookmarks" id="bookmarksContainer"></div>
    </div>
    
    <div class="modal" id="addModal">
        <div class="modal-content">
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
        let bookmarks = {{ bookmarks | tojson }};
        
        function render() {
            const container = document.getElementById('bookmarksContainer');
            const categories = {};
            bookmarks.forEach(bm => {
                const cat = bm.category || '未分类';
                if (!categories[cat]) categories[cat] = [];
                categories[cat].push(bm);
            });
            
            let html = '';
            for (const [cat, items] of Object.entries(categories)) {
                html += `<div class="category"><h3>${cat}</h3><div class="bookmark-grid">`;
                items.forEach(bm => {
                    html += `
                        <a href="${bm.url}" class="bookmark" target="_blank">
                            <button class="delete" onclick="event.preventDefault();deleteBookmark('${bm.id}')">×</button>
                            <span class="icon">${bm.icon || '🔗'}</span>
                            <span class="title">${bm.title}</span>
                        </a>`;
                });
                html += `<div class="add-bookmark" onclick="openModal()"><span class="icon">+</span><span class="title">添加</span></div>`;
                html += `</div></div>`;
            }
            container.innerHTML = html;
        }
        
        function openModal() { document.getElementById('addModal').classList.add('active'); }
        function closeModal() { document.getElementById('addModal').classList.remove('active'); }
        
        async function saveBookmark() {
            const data = {
                title: document.getElementById('bmTitle').value,
                url: document.getElementById('bmUrl').value,
                icon: document.getElementById('bmIcon').value || '🔗',
                category: document.getElementById('bmCategory').value || '未分类'
            };
            await fetch('/api/bookmarks', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
            location.reload();
        }
        
        async function deleteBookmark(id) {
            await fetch(`/api/bookmarks/${id}`, {method: 'DELETE'});
            location.reload();
        }
        
        render();
    </script>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


FILES_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件管理 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        nav {
            background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 15px 30px; display: flex; justify-content: space-between; align-items: center;
        }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .container { max-width: 1000px; margin: 0 auto; padding: 30px; }
        .breadcrumb { margin-bottom: 20px; color: rgba(255,255,255,0.5); }
        .breadcrumb a { color: #e94560; text-decoration: none; }
        .file-list { background: rgba(255,255,255,0.05); border-radius: 12px; overflow: hidden; }
        .file-item {
            display: flex; align-items: center; padding: 15px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;
        }
        .file-item:hover { background: rgba(255,255,255,0.05); }
        .file-item:last-child { border: none; }
        .file-icon { font-size: 24px; margin-right: 15px; width: 35px; text-align: center; }
        .file-name { flex: 1; }
        .file-name a { color: #fff; text-decoration: none; }
        .file-name a:hover { color: #e94560; }
        .file-meta { color: rgba(255,255,255,0.4); font-size: 13px; }
        .upload-area {
            border: 2px dashed rgba(255,255,255,0.2); border-radius: 12px;
            padding: 40px; text-align: center; margin-bottom: 20px; cursor: pointer;
            transition: all 0.2s;
        }
        .upload-area:hover { border-color: #e94560; background: rgba(233,69,96,0.1); }
        .upload-area input { display: none; }
        .download-btn {
            padding: 8px 12px; background: rgba(233,69,96,0.2); border: 1px solid rgba(233,69,96,0.5);
            border-radius: 8px; text-decoration: none; font-size: 14px; transition: all 0.2s;
        }
        .download-btn:hover { background: #e94560; }
        .action-btn {
            padding: 8px 12px; background: rgba(0,184,148,0.2); border: 1px solid rgba(0,184,148,0.5);
            border-radius: 8px; text-decoration: none; font-size: 14px; transition: all 0.2s; cursor: pointer; color: #fff;
        }
        .action-btn:hover { background: #00b894; }
        .action-btn.danger { background: rgba(233,69,96,0.2); border-color: rgba(233,69,96,0.5); }
        .action-btn.danger:hover { background: #e94560; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-box { background: #1a1a2e; border: 1px solid rgba(255,255,255,0.2); border-radius: 16px; padding: 30px; width: 400px; }
        .modal-box h3 { margin-bottom: 20px; }
        .modal-box input { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; background: rgba(255,255,255,0.1); color: #fff; font-size: 14px; }
        .btn-row { display: flex; gap: 10px; }
        .btn-row button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .share-url { padding: 10px; background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); border-radius: 8px; word-break: break-all; font-size: 12px; margin-top: 10px; }
        .watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
        .watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">📁 文件管理</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/data">数据</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div class="breadcrumb">
            <a href="/files">根目录</a>
            {% if current_path %} / {{ current_path }}{% endif %}
        </div>
        
        <div class="upload-area" onclick="document.getElementById('fileInput').click()">
            <input type="file" id="fileInput" onchange="uploadFile(this)">
            <p>📁 点击或拖拽上传文件</p>
        </div>
        
        <div class="file-list">
            {% if current_path %}
            <div class="file-item">
                <span class="file-icon">📂</span>
                <div class="file-name"><a href="/files">.. 返回上级</a></div>
            </div>
            {% endif %}
            {% for item in items %}
            <div class="file-item">
                <span class="file-icon">{{ '📂' if item.is_dir else '📄' }}</span>
                <div class="file-name">
                    <a href="/files/{{ item.path }}">{{ item.name }}</a>
                </div>
                <div class="file-meta">{{ item.modified }}{% if not item.is_dir %} | {{ "%.1f"|format(item.size / 1024) }} KB{% endif %}</div>
                {% if not item.is_dir %}
                <a href="/preview/{{ item.path }}" class="action-btn" target="_blank">预览</a>
                <a href="/download/{{ item.path }}" class="download-btn" title="下载">下载</a>
                <button class="action-btn" onclick="renameFile('{{ item.path }}', '{{ item.name }}')">重命名</button>
                <button class="action-btn" onclick="shareFile('{{ item.path }}')">分享</button>
                <button class="action-btn danger" onclick="deleteFile('{{ item.path }}')">删除</button>
                {% endif %}
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
            const file = input.files[0];
            if (!file) return;
            var btn = document.querySelector('.upload-area');
            btn.innerHTML = '<p>上传中...</p>';
            const formData = new FormData();
            formData.append('file', file);
            await fetch('/api/upload', {method: 'POST', body: formData});
            location.reload();
        }
        async function deleteFile(path) {
            if (!confirm('确定删除 ' + path + '？')) return;
            await fetch('/api/delete/' + path, {method: 'DELETE'});
            location.reload();
        }
        function renameFile(path, name) {
            currentPath = path;
            document.getElementById('newName').value = name;
            document.getElementById('renameModal').classList.add('active');
        }
        async function doRename() {
            var name = document.getElementById('newName').value;
            await fetch('/api/rename/' + currentPath, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name})});
            closeModal('renameModal');
            location.reload();
        }
        async function shareFile(path) {
            document.getElementById('shareModal').classList.add('active');
            document.getElementById('shareUrl').textContent = '生成中...';
            var r = await fetch('/api/share/' + path, {method: 'POST'});
            var d = await r.json();
            if (d.success) document.getElementById('shareUrl').textContent = window.location.origin + d.url;
        }
        function copyShare() {
            navigator.clipboard.writeText(document.getElementById('shareUrl').textContent);
            alert('已复制');
        }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
    </script>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


NOTES_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>笔记 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        nav {
            background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 15px 30px; display: flex; justify-content: space-between; align-items: center;
        }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .container { max-width: 800px; margin: 0 auto; padding: 30px; }
        .btn { padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #e94560; color: #fff; }
        .note-list { margin-top: 20px; }
        .note-card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 20px; margin-bottom: 15px; transition: all 0.2s;
        }
        .note-card:hover { border-color: rgba(233,69,96,0.5); }
        .note-card h3 { margin-bottom: 10px; }
        .note-card h3 a { color: #fff; text-decoration: none; }
        .note-card h3 a:hover { color: #e94560; }
        .note-card .meta { color: rgba(255,255,255,0.4); font-size: 13px; display: flex; justify-content: space-between; }
        .note-card .delete { background: none; border: none; color: #e94560; cursor: pointer; }
        .modal {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: #1a1a2e; border: 1px solid rgba(255,255,255,0.2);
            border-radius: 16px; padding: 30px; width: 600px;
        }
        .modal-content h3 { margin-bottom: 20px; }
        .modal-content input, .modal-content textarea {
            width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px; background: rgba(255,255,255,0.1); color: #fff; font-size: 14px;
        }
        .modal-content textarea { min-height: 200px; font-family: monospace; resize: vertical; }
        .btn-row { display: flex; gap: 10px; }
        .btn-row button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .action-btn {
            padding: 6px 12px; background: rgba(0,184,148,0.2); border: 1px solid rgba(0,184,148,0.5);
            border-radius: 6px; text-decoration: none; font-size: 12px; transition: all 0.2s; cursor: pointer; color: #fff; margin-left: 8px;
        }
        .action-btn:hover { background: #00b894; }
        .action-btn.danger { background: rgba(233,69,96,0.2); border-color: rgba(233,69,96,0.5); }
        .action-btn.danger:hover { background: #e94560; }
        .share-url { padding: 10px; background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); border-radius: 8px; word-break: break-all; font-size: 12px; margin-top: 10px; }
        .watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
        .watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">📝 笔记</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/data">数据</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div style="display: flex; gap: 10px; margin-bottom: 20px;">
            <form action="/notes" method="GET" style="display: flex; gap: 10px; flex: 1;">
                <input type="text" name="q" value="{{ query }}" placeholder="搜索笔记..." style="flex: 1; padding: 12px; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; background: rgba(255,255,255,0.1); color: #fff; font-size: 14px;">
                <button type="submit" class="btn btn-primary">搜索</button>
                {% if query %}<a href="/notes" class="btn btn-secondary" style="text-decoration:none;display:flex;align-items:center;">清除</a>{% endif %}
            </form>
            <button class="btn btn-primary" onclick="openModal('addModal')">+ 新建笔记</button>
            <button class="btn btn-secondary" onclick="document.getElementById('noteFileInput').click()" style="background:rgba(0,184,148,0.2);border:1px solid rgba(0,184,148,0.5);color:#fff;">上传笔记</button>
            <input type="file" id="noteFileInput" accept=".md,.txt" style="display:none" onchange="uploadNote(this)">
        </div>
        
        <div class="note-list">
            {% for note in notes %}
            <div class="note-card">
                <h3><a href="/notes/{{ note.id }}">{{ note.title }}</a></h3>
                <div class="meta">
                    <span>{{ note.created }}</span>
                    <div>
                        <a href="/notes/{{ note.id }}" class="action-btn">预览</a>
                        <button class="action-btn" onclick="editNote('{{ note.id }}')">编辑</button>
                        <a href="/api/notes/{{ note.id }}/download" class="action-btn">下载</a>
                        <button class="action-btn" onclick="renameNote('{{ note.id }}', '{{ note.title }}')">重命名</button>
                        <button class="action-btn" onclick="shareNote('{{ note.id }}')">分享</button>
                        <button class="action-btn danger" onclick="deleteNote('{{ note.id }}')">删除</button>
                    </div>
                </div>
            </div>
            {% endfor %}
            {% if not notes %}
            <p style="text-align:center;color:rgba(255,255,255,0.3);margin-top:50px;">暂无笔记</p>
            {% endif %}
        </div>
    </div>
    
    <div class="modal" id="addModal">
        <div class="modal-content">
            <h3>新建笔记</h3>
            <input type="text" id="noteTitle" placeholder="标题">
            <textarea id="noteContent" placeholder="内容 (支持 Markdown)"></textarea>
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('addModal')">取消</button>
                <button class="btn-primary" onclick="saveNote()">保存</button>
            </div>
        </div>
    </div>
    <div class="modal" id="renameModal">
        <div class="modal-content" style="width:400px">
            <h3>重命名笔记</h3>
            <input type="text" id="newTitle" placeholder="新标题">
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('renameModal')">取消</button>
                <button class="btn-primary" onclick="doRenameNote()">确定</button>
            </div>
        </div>
    </div>
    <div class="modal" id="shareModal">
        <div class="modal-content" style="width:400px">
            <h3>分享链接</h3>
            <div class="share-url" id="shareUrl">生成中...</div>
            <div class="btn-row" style="margin-top:12px">
                <button class="btn-primary" onclick="copyShare()">复制链接</button>
                <button class="btn-secondary" onclick="closeModal('shareModal')">关闭</button>
            </div>
        </div>
    </div>
    <div class="modal" id="editModal">
        <div class="modal-content">
            <h3>编辑笔记</h3>
            <input type="hidden" id="editNoteId">
            <textarea id="editContent" placeholder="内容 (支持 Markdown)" style="min-height:300px"></textarea>
            <div class="btn-row">
                <button class="btn-secondary" onclick="closeModal('editModal')">取消</button>
                <button class="btn-primary" onclick="saveEdit()">保存</button>
            </div>
        </div>
    </div>
    
    <script>
        var currentNoteId = '';
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        
        async function saveNote() {
            await fetch('/api/notes', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: document.getElementById('noteTitle').value,
                    content: document.getElementById('noteContent').value
                })
            });
            closeModal('addModal');
            location.reload();
        }
        
        async function uploadNote(input) {
            var file = input.files[0];
            if (!file) return;
            var content = await file.text();
            var title = file.name.replace(/\.(md|txt)$/, '');
            await fetch('/api/notes', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title, content: content})
            });
            location.reload();
        }
        
        async function deleteNote(id) {
            if (!confirm('确定删除？')) return;
            await fetch(`/api/notes/${id}`, {method: 'DELETE'});
            location.reload();
        }
        
        function renameNote(id, title) {
            currentNoteId = id;
            document.getElementById('newTitle').value = title;
            openModal('renameModal');
        }
        
        async function doRenameNote() {
            var title = document.getElementById('newTitle').value;
            await fetch('/api/notes/' + currentNoteId + '/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title})
            });
            closeModal('renameModal');
            location.reload();
        }
        
        async function shareNote(id) {
            openModal('shareModal');
            document.getElementById('shareUrl').textContent = '生成中...';
            var r = await fetch('/api/notes/' + id + '/share', {method: 'POST'});
            var d = await r.json();
            if (d.success) document.getElementById('shareUrl').textContent = window.location.origin + d.url;
        }
        
        function copyShare() {
            navigator.clipboard.writeText(document.getElementById('shareUrl').textContent);
            alert('已复制');
        }
        
        async function editNote(id) {
            document.getElementById('editNoteId').value = id;
            try {
                var r = await fetch('/notes/' + id);
                var html = await r.text();
                var match = html.match(/<div class="content">([\s\S]*?)<\/div>/);
                if (match) {
                    document.getElementById('editContent').value = match[1].trim();
                }
            } catch(e) {}
            openModal('editModal');
        }
        
        async function saveEdit() {
            var id = document.getElementById('editNoteId').value;
            var content = document.getElementById('editContent').value;
            await fetch('/api/notes/' + id + '/edit', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content: content})
            });
            closeModal('editModal');
            location.reload();
        }
    </script>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


NOTE_DETAIL_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        nav {
            background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 15px 30px; display: flex; justify-content: space-between; align-items: center;
        }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .container { max-width: 800px; margin: 0 auto; padding: 30px; }
        .note-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .note-title { font-size: 24px; font-weight: bold; }
        .note-actions { display: flex; gap: 10px; }
        .action-btn {
            padding: 8px 16px; background: rgba(0,184,148,0.2); border: 1px solid rgba(0,184,148,0.5);
            border-radius: 8px; text-decoration: none; font-size: 13px; transition: all 0.2s; cursor: pointer; color: #fff;
        }
        .action-btn:hover { background: #00b894; }
        .action-btn.danger { background: rgba(233,69,96,0.2); border-color: rgba(233,69,96,0.5); }
        .action-btn.danger:hover { background: #e94560; }
        .content {
            background: rgba(255,255,255,0.05); border-radius: 12px; padding: 30px;
            white-space: pre-wrap; line-height: 1.8;
        }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-box { background: #1a1a2e; border: 1px solid rgba(255,255,255,0.2); border-radius: 16px; padding: 30px; width: 400px; }
        .modal-box h3 { margin-bottom: 20px; }
        .modal-box input { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; background: rgba(255,255,255,0.1); color: #fff; font-size: 14px; }
        .btn-row { display: flex; gap: 10px; }
        .btn-row button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .share-url { padding: 10px; background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); border-radius: 8px; word-break: break-all; font-size: 12px; margin-top: 10px; }
        .watermark { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden; }
        .watermark span { position: absolute; font-size: 16px; color: rgba(255,255,255,0.03); transform: rotate(-30deg); white-space: nowrap; user-select: none; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">📝 笔记详情</div>
        <div class="links">
            <a href="/notes">返回列表</a>
            <a href="/">首页</a>
            <a href="/data">数据</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div class="note-header">
            <div class="note-title">{{ title }}</div>
            <div class="note-actions">
                <button class="action-btn" onclick="editNote()">编辑</button>
                <a href="/api/notes/{{ note_id }}/download" class="action-btn">下载</a>
                <button class="action-btn" onclick="renameNote()">重命名</button>
                <button class="action-btn" onclick="shareNote()">分享</button>
                <button class="action-btn danger" onclick="deleteNote()">删除</button>
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
    <div class="modal" id="editModal">
        <div class="modal-box" style="width:600px">
            <h3>编辑笔记</h3>
            <textarea id="editContent" style="width:100%;min-height:300px;padding:12px;border:1px solid rgba(255,255,255,0.2);border-radius:8px;background:rgba(255,255,255,0.1);color:#fff;font-size:14px;font-family:monospace;resize:vertical;">{{ content }}</textarea>
            <div class="btn-row" style="margin-top:12px">
                <button class="btn-secondary" onclick="closeModal('editModal')">取消</button>
                <button class="btn-primary" onclick="saveEdit()">保存</button>
            </div>
        </div>
    </div>
    
    <script>
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        async function deleteNote() {
            if (!confirm('确定删除此笔记？')) return;
            await fetch('/api/notes/{{ note_id }}', {method: 'DELETE'});
            window.location = '/notes';
        }
        function renameNote() { openModal('renameModal'); }
        function editNote() { openModal('editModal'); }
        async function doRename() {
            var title = document.getElementById('newTitle').value;
            await fetch('/api/notes/{{ note_id }}/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title})
            });
            location.reload();
        }
        async function shareNote() {
            openModal('shareModal');
            document.getElementById('shareUrl').textContent = '生成中...';
            var r = await fetch('/api/notes/{{ note_id }}/share', {method: 'POST'});
            var d = await r.json();
            if (d.success) document.getElementById('shareUrl').textContent = window.location.origin + d.url;
        }
        function copyShare() {
            navigator.clipboard.writeText(document.getElementById('shareUrl').textContent);
            alert('已复制');
        }
    </script>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


CHANGE_PWD_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>修改密码 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        nav { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .container { max-width: 500px; margin: 50px auto; padding: 30px; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 30px; }
        .card h2 { margin-bottom: 20px; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; color: rgba(255,255,255,0.7); }
        .form-group input { width: 100%; padding: 12px; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; background: rgba(255,255,255,0.1); color: #fff; font-size: 14px; }
        .btn { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #e94560; color: #fff; font-size: 16px; cursor: pointer; }
        .btn:hover { background: #c23152; }
        .error { color: #ff6b6b; margin-bottom: 15px; font-size: 14px; }
        .success { color: #00b894; margin-bottom: 15px; font-size: 14px; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">🔑 修改密码</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/data">数据</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div class="card">
            <h2>修改密码</h2>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            {% if success %}<div class="success">{{ success }}</div>{% endif %}
            <form method="POST">
                <div class="form-group">
                    <label>原密码</label>
                    <input type="password" name="old_password" required>
                </div>
                <div class="form-group">
                    <label>新密码</label>
                    <input type="password" name="new_password" required>
                </div>
                <div class="form-group">
                    <label>确认新密码</label>
                    <input type="password" name="confirm_password" required>
                </div>
                <button type="submit" class="btn">确认修改</button>
            </form>
        </div>
    </div>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


ADMIN_USERS_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>用户管理 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        nav { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .container { max-width: 800px; margin: 30px auto; padding: 30px; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 30px; margin-bottom: 20px; }
        .card h2 { margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { color: rgba(255,255,255,0.6); font-size: 14px; }
        .role-admin { color: #e94560; }
        .role-user { color: #00b894; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; margin-right: 5px; }
        .btn-danger { background: #e94560; color: #fff; }
        .btn-warning { background: #fdcb6e; color: #000; }
        .btn-primary { background: #0984e3; color: #fff; }
        .form-row { display: flex; gap: 10px; margin-bottom: 15px; }
        .form-row input, .form-row select { flex: 1; padding: 10px; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; background: rgba(255,255,255,0.1); color: #fff; }
        .msg { padding: 10px; border-radius: 6px; margin-bottom: 15px; display: none; }
        .msg.error { background: rgba(233,69,96,0.2); color: #ff6b6b; display: block; }
        .msg.success { background: rgba(0,184,148,0.2); color: #00b894; display: block; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">👥 用户管理</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/data">数据</a>
            <a href="/admin/users">用户管理</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div class="card">
            <h2>添加用户</h2>
            <div id="msg" class="msg"></div>
            <div class="form-row">
                <input type="text" id="newUsername" placeholder="用户名">
                <input type="password" id="newPassword" placeholder="密码">
                <select id="newRole">
                    <option value="user">普通用户</option>
                    <option value="admin">管理员</option>
                </select>
                <button class="btn btn-primary" onclick="addUser()">添加</button>
            </div>
        </div>
        <div class="card">
            <h2>用户列表</h2>
            <table>
                <thead>
                    <tr><th>用户名</th><th>角色</th><th>创建时间</th><th>操作</th></tr>
                </thead>
                <tbody>
                    {% for username, user in users.items() %}
                    <tr>
                        <td>{{ username }}</td>
                        <td class="role-{{ user.role }}">{{ '管理员' if user.role == 'admin' else '普通用户' }}</td>
                        <td>{{ user.created_at }}</td>
                        <td>
                            {% if username != 'admin' %}
                            <button class="btn btn-warning" onclick="resetPassword('{{ username }}')">重置密码</button>
                            <button class="btn btn-danger" onclick="deleteUser('{{ username }}')">删除</button>
                            {% else %}
                            <span style="color:rgba(255,255,255,0.3)">--</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    <script>
        function showMsg(text, type) {
            var msg = document.getElementById('msg');
            msg.textContent = text;
            msg.className = 'msg ' + type;
            setTimeout(function(){ msg.className = 'msg'; }, 3000);
        }
        async function addUser() {
            var data = new FormData();
            data.append('username', document.getElementById('newUsername').value);
            data.append('password', document.getElementById('newPassword').value);
            data.append('role', document.getElementById('newRole').value);
            var res = await fetch('/admin/users/add', {method: 'POST', body: data});
            var json = await res.json();
            if (json.success) { location.reload(); } else { showMsg(json.error, 'error'); }
        }
        async function deleteUser(username) {
            if (!confirm('确定删除用户 ' + username + '？')) return;
            await fetch('/admin/users/' + username, {method: 'DELETE'});
            location.reload();
        }
        async function resetPassword(username) {
            var res = await fetch('/admin/users/' + username + '/reset-password', {method: 'POST'});
            var json = await res.json();
            if (json.success) { alert('新密码: ' + json.password); } else { alert(json.error); }
        }
    </script>
    <script>
        var c=document.createElement('div');c.className='watermark';document.body.appendChild(c);
        for(var i=0;i<50;i++){var s=document.createElement('span');s.textContent='Private Hub';s.style.left=(Math.random()*100)+'%';s.style.top=(Math.random()*100)+'%';c.appendChild(s);}
    </script>
</body>
</html>'''


DATA_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据操作 - 私密中心</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        nav { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        nav .logo { font-size: 20px; font-weight: bold; }
        nav .links a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 25px; }
        nav .links a:hover { color: #e94560; }
        .container { max-width: 600px; margin: 50px auto; padding: 30px; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 30px; }
        .card h2 { color: #e94560; margin-bottom: 20px; font-size: 18px; }
        .btn { padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; margin-right: 10px; margin-bottom: 10px; transition: all 0.2s; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; }
        .btn:hover { opacity: 0.8; transform: translateY(-1px); }
        .info { margin-top: 15px; color: rgba(255,255,255,0.4); font-size: 13px; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">📊 数据操作</div>
        <div class="links">
            <a href="/">首页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/change-password">修改密码</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div class="card">
            <h2>数据操作</h2>
            <button class="btn btn-primary" onclick="exportData()">📥 导出所有数据</button>
            <button class="btn btn-secondary" onclick="importData()">📤 导入数据</button>
            <input type="file" id="importFile" accept=".json" style="display:none" onchange="doImport(this)">
            <div class="info">
                <p>导出：将书签和笔记数据导出为JSON文件</p>
                <p>导入：从JSON文件恢复数据</p>
            </div>
        </div>
    </div>
    <script>
        function exportData() {
            window.open('/api/data/export', '_blank');
        }
        function importData() {
            document.getElementById('importFile').click();
        }
        async function doImport(input) {
            var file = input.files[0];
            if (!file) return;
            var text = await file.text();
            try {
                var data = JSON.parse(text);
                var r = await fetch('/api/data/import', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                var d = await r.json();
                if (d.success) {
                    alert('导入成功');
                    location.reload();
                } else {
                    alert('导入失败: ' + (d.error || '未知错误'));
                }
            } catch(e) {
                alert('文件格式错误');
            }
        }
    </script>
</body>
</html>'''


SHARED_NOTE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - 分享</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        .header { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 15px 30px; text-align: center; }
        .header h1 { font-size: 18px; }
        .header p { color: rgba(255,255,255,0.4); font-size: 12px; margin-top: 5px; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 30px; }
        .content { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 25px; white-space: pre-wrap; line-height: 1.8; }
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


PREVIEW_TEXT_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ filename }} - 预览</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { min-height: 100vh; background: #0f0f1a; font-family: 'Microsoft YaHei', sans-serif; color: #fff; }
        .header { background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 16px; color: #e94560; }
        .header a { color: rgba(255,255,255,0.7); text-decoration: none; padding: 8px 16px; background: rgba(255,255,255,0.1); border-radius: 8px; font-size: 13px; }
        .header a:hover { background: rgba(233,69,96,0.3); }
        .container { max-width: 1000px; margin: 30px auto; padding: 0 30px; }
        .content { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 25px; }
        pre { white-space: pre-wrap; word-wrap: break-word; line-height: 1.6; font-size: 13px; color: rgba(255,255,255,0.8); font-family: monospace; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ filename }}</h1>
        <div>
            <a href="/download/{{ filename }}">下载</a>
            <a href="/files">返回</a>
        </div>
    </div>
    <div class="container">
        <div class="content"><pre>{{ content }}</pre></div>
    </div>
</body>
</html>'''


# ============================================================================
# 启动
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("HUB_PORT", os.environ.get("PORT", 8888)))
    app.run(host="0.0.0.0", port=port, debug=False)
