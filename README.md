# FileConverter (Linux/WSL 版) 🐧

**多格式文件在线转换工具** — 基于 Flask 的 Web 应用，支持 16 种文件转换模式。

使用 **LibreOffice** 替代 Windows COM 组件实现 Office 文档转换，适配 WSL/Linux 环境。

## 功能总览 ✨

### 文件转换 (16 种模式)

| 类别 | 模式 | 说明 |
|------|------|------|
| 📎 Office 文档 | Word 转 PDF | .docx → .pdf |
| | PDF 转 Word | .pdf → .docx |
| | Excel 转 PDF | .xlsx/.xls → .pdf |
| | PPT 转 PDF | .pptx/.ppt → .pdf |
| | CSV 转 Excel | .csv → .xlsx |
| | Excel 转 CSV | .xlsx/.xls → .csv |
| 📝 文本 / OCR | MD 转 PDF | Markdown → .pdf |
| | HTML 转 PDF | .html/.htm → .pdf |
| | PDF OCR 识别 | 提取 PDF 中文字 → .txt |
| | 图片 OCR 识别 | 图片文字识别 → .txt |
| 🖼️ 图片 / 媒体 | 图片转 PDF | 多张图片合并为 .pdf |
| | PDF 转图片 | PDF 每页转 .jpg（打包 zip） |
| | 图片转 PPT | 图片逐页插入 .pptx |
| | **PDF 合并** | 多个 PDF 按序合并（支持拖拽排序） |
| 🔐 安全 | PDF 加密 | 设置打开密码 |
| | PDF 解密 | 移除密码保护 |

### 批量处理
- 单次可上传多个文件，批量转换自动打包 zip 下载
- 图片转 PDF / 图片转 PPT 支持最多 100 张
- PDF 合并最多 50 个文件

### 用户系统
- 邮箱注册 + 验证码
- 双模式计费：**按次** 或 **按有效期**
- 密码找回（邮箱验证码）
- IP 访问记录与封禁

### 管理后台
- 用户管理（充值次数、延长期限、封禁/解封）
- 公告管理
- 联系留言管理
- IP 分析与地域封禁
- 转换日志查询

### 安全特性
- CSRF 防护
- 登录限流（防暴力破解）
- 验证码发送限流
- IP 黑名单 + 地域封禁
- 文件双重扩展名检测
- 文件内容（幻数）校验
- X-Forwarded-For 信任代理白名单

## 与原版的区别

| 特性 | Windows 版 | **Linux/WSL 版** |
|------|-----------|-----------------|
| Word/Excel/PPT → PDF | Microsoft Office COM | **LibreOffice** |
| MD/HTML → PDF | Word COM 中转 | **LibreOffice** |
| PDF → Word / 图片 | pdf2docx / pdf2image | ✅ 相同（跨平台） |
| 图片 → PDF / PPT | Pillow / python-pptx | ✅ 相同（跨平台） |
| CSV ↔ Excel | pandas | ✅ 相同（跨平台） |
| OCR 识别 | Tesseract | ✅ 相同（Linux 上更稳定） |
| PDF 合并 / 加密 | PyPDF2 | ✅ 相同（跨平台） |

## 环境要求

- **Python 3.8+**
- **MySQL 8.0+**
- **LibreOffice**（Office 转换必须）
- **Tesseract OCR**（OCR 识别必须）
- **中文字体**（PDF 中文正常显示）

### 安装依赖

```bash
# MySQL
sudo apt install mysql-server

# LibreOffice
sudo apt install libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress

# Tesseract OCR 及中文语言包
sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng

# 中文字体（防 PDF 乱码）
sudo apt install fonts-noto-cjk fonts-wqy-zenhei
```

## 快速开始

```bash
# 1. 克隆并进入项目
git clone <your-repo-url> && cd FileConverter_Linux

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装 Python 依赖
pip install -r requirements

# 4. 配置 MySQL
sudo service mysql start
sudo mysql -e "CREATE USER 'fileconverter'@'localhost' IDENTIFIED BY 'your_password';"
sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'fileconverter'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"
sudo mysql -e "CREATE DATABASE IF NOT EXISTS fileconverter DEFAULT CHARSET utf8mb4;"

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置（见下方说明）
vim .env

# 6. 启动（自动初始化数据库表）
chmod +x start.sh
./start.sh
```

访问 `http://localhost:5000`，注册账号即可使用。

系统首次启动时自动创建数据库表和管理员账号。

## 配置说明

编辑 `.env` 文件：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | Flask Session 签名密钥 | **必填** |
| `DB_ACCOUNT` | MySQL 用户名 | **必填** |
| `DB_PASSWORD` | MySQL 密码 | **必填** |
| `DB` | 数据库名 | **必填** |
| `MAIL_HOST` | SMTP 服务器（注册验证码用） | `smtp.qq.com` |
| `MAIL_PORT` | SMTP 端口 | `465` |
| `MAIL_USER` | SMTP 邮箱 | **必填** |
| `MAIL_PASSWORD` | SMTP 授权码 | **必填** |
| `ADMIN_PASSWORD` | 管理员密码 | **必填** |
| `ADMIN_USERNAME` | 管理员用户名 | `admin` |
| `ADMIN_EMAIL` | 管理员邮箱 | `admin@example.com` |
| `DB_PORT` | MySQL 端口 | `3306` |
| `PORT` | 服务端口 | `5000` |
| `UPLOAD_MAX_SIZE` | 单文件大小上限 (MB) | `50` |
| `CDN_BASE_URL` | 前端 CDN 资源地址 | `https://cdn.staticfile.org` |

### 安全相关

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CSRF_ENABLED` | 是否启用 CSRF 防护 | `1` |
| `LOGIN_RATE_LIMIT` | 登录失败阈值 | `10` |
| `LOGIN_RATE_WINDOW` | 登录限流窗口 (秒) | `300` |
| `PASSWORD_MIN_LENGTH` | 最小密码长度 | `8` |
| `VERIFY_CODE_RESEND_INTERVAL` | 验证码重发间隔 (秒) | `60` |
| `VERIFY_CODE_EXPIRE` | 验证码过期时间 (秒) | `300` |

## LibreOffice 转换说明

- 首次转换约 5-10 秒（LibreOffice 后台进程初始化）
- 所有 Office 转换使用互斥锁串行执行（防止 LibreOffice 实例冲突）
- 如转换中文 PDF 出现乱码，请安装中文字体后再试

## 项目结构

```
├── app.py                  # Flask 应用入口、中间件（CSRF、IP 封禁、访问日志）
├── config.py               # 配置类
├── utils.py                # 工具函数（CSRF、IP、文件校验）
├── requirements            # Python 依赖
├── start.sh                # 启动脚本
├── converter/
│   ├── converter_engine.py # 所有转换引擎（LibreOffice、OCR、PDF 等）
│   └── __init__.py
├── database/
│   ├── db_manager.py       # 数据库操作（用户、日志、IP 等）
│   └── __init__.py
├── routes/
│   ├── auth.py             # 登录/注册/找回密码
│   ├── converter.py        # 文件上传/转换/下载
│   └── admin.py            # 管理后台
├── templates/               # Jinja2 模板
├── static/                  # 静态资源（CSS/JS）
├── uploads/                 # 上传文件（临时）
└── outputs/                 # 转换结果（临时，超时清理）
```

## API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（文件转换） |
| `/convert` | POST | 执行文件转换 |
| `/download/<filename>` | GET | 下载转换后的文件 |
| `/login` | GET/POST | 登录 |
| `/register` | GET/POST | 注册 |
| `/forgot_password` | GET/POST | 找回密码 |
| `/send_verify_code` | POST | 发送邮箱验证码 |
| `/logout` | GET | 退出登录 |
| `/contact` | GET/POST | 联系/留言 |
| `/my_logs` | GET | 个人转换记录 |
| `/admin` | GET | 管理后台 |
| `/admin/<action>` | POST | 用户管理操作 |

## 注意事项

1. **路径分隔符** — Linux 使用 `/`，已全部适配
2. **文件清理** — `uploads/` 和 `outputs/` 中的超时文件（默认 7 天）在应用退出时自动清理
3. **MySQL 连接** — 推荐 `localhost`（socket 连接，比 TCP 更快）
4. **生产环境** — 关闭调试模式：`export FLASK_DEBUG=0`
5. **后台运行** — `nohup ./start.sh > output.log 2>&1 &`
6. **代理环境** — 如使用 Nginx / Cloudflare，配置 `TRUSTED_PROXY_IPS` 以获取真实 IP
