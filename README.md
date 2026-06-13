# 私密中心网站 - 项目文档

## 项目概述
私密中心（Private Hub）是一个基于Flask的私密网站，集成仪表盘、数据模块、启动页、文件管理、笔记系统等功能。

## 访问地址
- **网站地址**: https://private-hub-production-08d2.up.railway.app
- **管理员账号**: `001`
- **管理员密码**: `123456`

## 项目结构
```
F:\mimo\
├── app.py              # 主程序文件
├── wsgi.py             # WSGI入口（Railway部署用）
├── Procfile            # 启动命令（Render部署用）
├── requirements.txt    # Python依赖
├── deploy.bat          # 一键部署脚本
├── 网站一.py           # 本地运行版本
├── data/               # 数据目录
│   ├── config/         # 配置文件
│   │   └── users.json  # 用户账号数据
│   ├── data/           # 书签、笔记索引
│   ├── files/          # 上传的文件
│   └── notes/          # 笔记内容
└── .gitignore          # Git忽略文件
```

## 功能列表

### 1. 用户系统
- 多账号支持（管理员/普通用户）
- 管理员可创建/删除用户、重置密码
- 所有用户可修改自己的密码

### 2. 仪表盘
- 实时显示CPU、内存、磁盘使用情况
- 显示系统运行时间
- 快捷访问入口

### 3. 数据模块
- 站点统计（书签/笔记/文件数量）
- 服务器状态监控
- 操作日志
- 数据导出功能

### 4. 启动页
- 书签管理（添加/删除）
- 网址搜索
- 按分类显示

### 5. 文件管理
- 文件上传
- 文件下载
- 文件列表

### 6. 笔记系统
- 创建/编辑/删除笔记
- Markdown格式支持

### 7. 其他功能
- 全站水印（Private Hub）
- 统一导航栏
- 响应式设计

## 部署信息

### Railway部署
- **项目名**: private-hub
- **服务名**: private-hub
- **域名**: https://private-hub-production-08d2.up.railway.app
- **环境变量**: 无需设置（密码硬编码在代码中）

### Render部署（备用）
- 需要手动创建Web Service
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn wsgi:app`

## 本地运行

### 方法1：直接运行
```bash
cd F:\mimo
python 网站一.py
```
- 本地访问: http://localhost:8888
- 自动生成随机密码（查看控制台输出）

### 方法2：使用app.py
```bash
cd F:\mimo
$env:PYTHONIOENCODING='utf-8'
python app.py
```

## 重新部署

### 使用部署脚本
```bash
双击 F:\mimo\deploy.bat
```

### 手动部署
```bash
cd F:\mimo
git add app.py
git commit -m "更新说明"
git push origin master
```
Railway会自动检测代码变更并重新部署。

## 修改密码

### 管理员修改自己的密码
1. 登录网站
2. 点击导航栏"修改密码"
3. 输入原密码和新密码

### 管理员重置其他用户密码
1. 登录网站
2. 点击导航栏"用户管理"
3. 找到用户，点击"重置密码"
4. 系统会生成新密码并显示

## 注意事项

1. **数据持久化**: Railway免费套餐不支持Volume，重新部署后上传的文件和笔记会丢失
2. **密码存储**: 密码使用SHA256加密存储在users.json中
3. **Session**: 登录状态保持7天
4. **水印**: 全站显示半透明"Private Hub"水印

## 依赖包
- flask==3.0.0
- psutil==5.9.7
- gunicorn==21.2.0

## Git仓库
- **地址**: https://github.com/st6tttk2wy-tech/private-hub
- **分支**: master

## 常见问题

### Q: 网站打不开？
A: 检查Railway部署状态，可能正在重新部署中，等待1-2分钟。

### Q: 登录后显示"加载中"？
A: 检查浏览器控制台是否有JavaScript错误，刷新页面重试。

### Q: 上传的文件丢失？
A: Railway免费套餐不支持持久化存储，重新部署后文件会丢失。建议定期导出重要数据。

### Q: 如何修改管理员账号？
A: 目前管理员账号硬编码为`001`，需要修改app.py中的DEFAULT_USERS配置。
