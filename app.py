# -*- coding: utf-8 -*-
"""
私密中心 (Private Hub)
"""

import os
import sys
import json
import hashlib
import secrets
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
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
FILES_DIR = BASE_DIR / "files"
NOTES_DIR = BASE_DIR / "notes"

for d in [CONFIG_DIR, DATA_DIR, FILES_DIR, NOTES_DIR]:
    d.mkdir(exist_ok=True)

CONFIG_FILE = CONFIG_DIR / "auth.json"
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"
NOTES_INDEX = DATA_DIR / "notes_index.json"


def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    
    env_password = os.environ.get("HUB_PASSWORD")
    if env_password:
        config = {"password_hash": hash_password(env_password), "username": "admin"}
    else:
        password = secrets.token_urlsafe(8)
        config = {"password_hash": hash_password(password), "username": "admin"}
        print(f"\n{'='*50}")
        print(f"首次启动 - 自动生成密码: {password}")
        print(f"请妥善保存，下次登录需要使用此密码")
        print(f"{'='*50}\n")
    
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(password):
    config = load_config()
    return hash_password(password) == config.get("password_hash", "")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ============================================================================
# 路由
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password(password):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "密码错误"
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)


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
    return render_template_string(NOTES_HTML, notes=notes_list)


@app.route("/notes/<note_id>")
@login_required
def note_detail(note_id):
    note_file = NOTES_DIR / f"{note_id}.md"
    if not note_file.exists():
        abort(404)
    content = note_file.read_text(encoding="utf-8")
    return render_template_string(NOTE_DETAIL_HTML, content=content, note_id=note_id)


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
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐</h1>
        <p>私密中心</p>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="input-group">
                <label>密码</label>
                <input type="password" name="password" placeholder="请输入密码" autofocus>
            </div>
            <button type="submit" class="btn">登录</button>
        </form>
    </div>
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
        .container { max-width: 1200px; margin: 0 auto; padding: 30px; }
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
        .quick-links { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }
        .quick-link {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 20px; text-align: center; text-decoration: none; color: #fff;
            transition: all 0.2s;
        }
        .quick-link:hover { background: rgba(233,69,96,0.2); border-color: #e94560; }
        .quick-link .icon { font-size: 32px; margin-bottom: 10px; }
        .quick-link .name { font-size: 14px; color: rgba(255,255,255,0.8); }
        .section-title { font-size: 18px; margin-bottom: 20px; color: rgba(255,255,255,0.9); }
        #time { font-size: 48px; font-weight: 300; text-align: center; margin: 20px 0; }
        #date { text-align: center; color: rgba(255,255,255,0.5); }
    </style>
</head>
<body>
    <nav>
        <div class="logo">🏠 私密中心</div>
        <div class="links">
            <a href="/">仪表盘</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div id="time"></div>
        <div id="date"></div>
        
        <div class="grid" style="margin-top: 30px;">
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
        </div>
        
        <h2 class="section-title">快捷访问</h2>
        <div class="quick-links">
            <a href="/startpage" class="quick-link"><div class="icon">🚀</div><div class="name">启动页</div></a>
            <a href="/files" class="quick-link"><div class="icon">📁</div><div class="name">文件管理</div></a>
            <a href="/notes" class="quick-link"><div class="icon">📝</div><div class="name">笔记</div></a>
            <a href="https://github.com" class="quick-link" target="_blank"><div class="icon">🐙</div><div class="name">GitHub</div></a>
        </div>
    </div>
    
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
            } catch(e) {
                console.error('加载系统信息失败:', e);
            }
        }
        
        loadSystemInfo();
        setInterval(loadSystemInfo, 5000);
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
    </style>
</head>
<body>
    <nav>
        <div class="logo">🚀 启动页</div>
        <div class="links">
            <a href="/">仪表盘</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
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
    </style>
</head>
<body>
    <nav>
        <div class="logo">📁 文件管理</div>
        <div class="links">
            <a href="/">仪表盘</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
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
            </div>
            {% endfor %}
            {% if not items %}
            <div class="file-item"><div class="file-name" style="text-align:center;color:rgba(255,255,255,0.3);">暂无文件</div></div>
            {% endif %}
        </div>
    </div>
    
    <script>
        async function uploadFile(input) {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            await fetch('/api/upload', {method: 'POST', body: formData});
            location.reload();
        }
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
    </style>
</head>
<body>
    <nav>
        <div class="logo">📝 笔记</div>
        <div class="links">
            <a href="/">仪表盘</a>
            <a href="/startpage">启动页</a>
            <a href="/files">文件</a>
            <a href="/notes">笔记</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <button class="btn btn-primary" onclick="openModal()">+ 新建笔记</button>
        
        <div class="note-list">
            {% for note in notes %}
            <div class="note-card">
                <h3><a href="/notes/{{ note.id }}">{{ note.title }}</a></h3>
                <div class="meta">
                    <span>{{ note.created }}</span>
                    <button class="delete" onclick="deleteNote('{{ note.id }}')">删除</button>
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
                <button class="btn-secondary" onclick="closeModal()">取消</button>
                <button class="btn-primary" onclick="saveNote()">保存</button>
            </div>
        </div>
    </div>
    
    <script>
        function openModal() { document.getElementById('addModal').classList.add('active'); }
        function closeModal() { document.getElementById('addModal').classList.remove('active'); }
        
        async function saveNote() {
            await fetch('/api/notes', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: document.getElementById('noteTitle').value,
                    content: document.getElementById('noteContent').value
                })
            });
            location.reload();
        }
        
        async function deleteNote(id) {
            if (!confirm('确定删除？')) return;
            await fetch(`/api/notes/${id}`, {method: 'DELETE'});
            location.reload();
        }
    </script>
</body>
</html>'''


NOTE_DETAIL_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>笔记详情 - 私密中心</title>
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
        .content {
            background: rgba(255,255,255,0.05); border-radius: 12px; padding: 30px;
            white-space: pre-wrap; line-height: 1.8;
        }
    </style>
</head>
<body>
    <nav>
        <div class="logo">📝 笔记详情</div>
        <div class="links">
            <a href="/notes">返回列表</a>
            <a href="/">仪表盘</a>
            <a href="/logout">退出</a>
        </div>
    </nav>
    <div class="container">
        <div class="content">{{ content }}</div>
    </div>
</body>
</html>'''


# ============================================================================
# 启动
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("HUB_PORT", os.environ.get("PORT", 8888)))
    load_config()
    app.run(host="0.0.0.0", port=port, debug=False)