# 网站部署文件

## 文件说明
- `app.py` - 主程序文件（部署用）
- `requirements.txt` - Python依赖
- `Procfile` - 启动命令（Render需要）
- `runtime.txt` - Python版本（Render需要）

## 部署步骤

### Railway 部署
1. 访问 https://railway.app 注册账号（GitHub登录）
2. 点击 "New Project" → "Deploy from GitHub repo" 或 "Empty Project"
3. 上传这些文件
4. 设置环境变量 `HUB_PASSWORD`（你的密码）
5. 部署完成后获得公网URL

### Render 部署
1. 访问 https://render.com 注册账号
2. 点击 "New" → "Web Service"
3. 连接GitHub仓库或直接上传文件
4. 设置：
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
5. 设置环境变量 `HUB_PASSWORD`
6. 部署完成后获得公网URL

## 注意事项
- 云部署后，上传的文件和笔记在重启后可能丢失
- 建议设置环境变量 `HUB_PASSWORD` 来固定密码
