# 私密中心网站 - 项目文档

## 项目概述
私密中心（Private Hub）是一个基于Flask的私密网站，集成首页、信息管理、数据管理、文件管理、笔记管理、用户管理、密码管理、操作日志等功能。

## 访问地址
- **网站地址**: https://private-hub-production-08d2.up.railway.app
- **管理员账号**: `001`
- **管理员密码**: `123456`

## 功能列表

### 1. 首页 (`/`)
- 左侧快捷访问栏（240px宽度）
- 系统监控图表（CPU/内存/磁盘）
- 数据统计（书签/笔记/文件数量）
- 操作日志显示

### 2. 信息管理 (`/news`)
- 8个平台热榜数据
- 微博、抖音、今日头条、知乎、B站、百度、小红书、今日资讯
- 每日8:00自动收集
- 显示完整内容（标题+描述）

### 3. 数据管理 (`/data`)
- 数据导出（JSON格式）
- 数据导入

### 4. 文件管理 (`/files`)
- 文件上传
- 文件预览（支持图片/文本/PDF）
- 文件下载
- 文件重命名
- 文件删除（可撤销）
- 文件分享

### 5. 笔记管理 (`/notes`)
- 笔记创建
- 笔记编辑
- 笔记搜索
- 笔记预览
- 笔记下载
- 笔记重命名
- 笔记删除（可撤销）
- 笔记分享

### 6. 用户管理 (`/admin/users`)
- 添加用户
- 删除用户（可撤销）
- 重置密码（可撤销）
- 权限分配（首页/信息/文件/笔记/数据）

### 7. 密码管理 (`/change-password`)
- 修改密码（可撤销）

### 8. 操作日志 (`/logs`)
- 记录所有用户操作
- 撤销功能（删除笔记/文件/用户、修改密码）

## 导航栏和侧边栏

### 导航栏（固定内容）
首页、信息管理、数据管理、文件管理、笔记管理、用户管理、密码管理、退出

### 侧边栏（快捷访问）
信息管理、数据管理、文件管理、笔记管理、用户管理、密码管理、操作日志

## 新闻数据源
| 平台 | API |
|------|-----|
| 微博 | https://api.vvhan.com/api/hotlist/weibo |
| 抖音 | https://api.vvhan.com/api/hotlist/douyin |
| 今日头条 | https://api.vvhan.com/api/hotlist/toutiao |
| 知乎 | https://api.vvhan.com/api/hotlist/zhihuHot |
| B站 | https://api.vvhan.com/api/hotlist/bili |
| 百度 | https://api.vvhan.com/api/hotlist/baiduRD |
| 小红书 | https://api.vvhan.com/api/hotlist/xhsHot |
| 今日资讯 | https://api.vvhan.com/api/hotlist/qq-news |

## 项目结构
```
F:\mimo\
├── app.py              # 主程序文件
├── wsgi.py             # WSGI入口（Railway部署用）
├── Procfile            # 启动命令（Render部署用）
├── requirements.txt    # Python依赖
├── deploy.bat          # 一键部署脚本
├── README.md           # 项目文档
├── 续接文档.md          # 接续工作文档
├── data/               # 数据目录
│   ├── config/         # 配置文件
│   │   ├── users.json  # 用户账号数据
│   │   └── settings.json # 系统设置
│   ├── data/           # 书签、笔记索引
│   ├── files/          # 上传的文件
│   ├── logs/           # 操作日志
│   └── news/           # 新闻数据
└── .gitignore          # Git忽略文件
```

## 部署信息

### Railway部署
- **项目名**: private-hub
- **域名**: https://private-hub-production-08d2.up.railway.app
- **环境变量**: 无需设置（密码硬编码在代码中）

## 本地运行
```bash
cd F:\mimo
$env:PYTHONIOENCODING='utf-8'
python app.py
```
访问 http://localhost:8888

## 重新部署
```bash
cd F:\mimo
git add app.py
git commit -m "更新说明"
git push origin master
```

## 环境要求
- Python 3.7+
- Flask 3.0.0
- psutil 5.9.7
- requests 2.31.0（新闻收集）
- gunicorn 21.2.0（生产环境）

## Git仓库
- **地址**: https://github.com/st6tttk2wy-tech/private-hub
- **分支**: master

## 注意事项
1. app.py文件不能有null字节，否则Railway部署失败
2. is_relative_to在Python 3.7中不可用，已替换为startswith
3. Railway免费套餐不支持持久化存储，重新部署后数据可能丢失
4. 中文字符在Windows终端显示乱码，但浏览器正常显示
