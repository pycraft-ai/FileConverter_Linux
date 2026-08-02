# FileConverter (Linux/WSL 版) 🐧

**多格式文件在线转换工具** — 基于 Flask 的 Web 应用，支持 **28 种**文件转换模式。

使用 **LibreOffice** 替代 Windows COM 组件实现 Office 文档转换，完整适配 Linux/WSL 环境。

## 功能总览 ✨

### 文件转换（28 种模式）

| 类别 | 模式 | 说明 |
|------|------|------|
| 📎 Office 文档 | Word 转 PDF | .docx → .pdf |
| | PDF 转 Word | .pdf → .docx |
| | Excel 转 PDF | .xlsx/.xls → .pdf |
| | PPT 转 PDF | .pptx/.ppt → .pdf |
| | PPT 转 Word | .pptx/.ppt → .docx |
| | CSV 转 Excel | .csv → .xlsx |
| | Excel 转 CSV | .xlsx/.xls → .csv |
| 📝 文本 / OCR | MD 转 PDF | Markdown → .pdf |
| | MD 转 HTML | Markdown → .html |
| | HTML 转 PDF | .html/.htm → .pdf |
| | PDF OCR 识别 | 提取 PDF 中文字 → .txt |
| | 图片 OCR 识别 | 图片文字识别 → .txt |
| | 文字转语音 | .txt → .mp3（基于 edge-tts） |
| 🖼️ 图片 / 媒体 | 图片转 PDF | 多张图片合并为 .pdf |
| | PDF 转图片 | PDF 每页转 .jpg（打包 zip） |
| | 图片转 PPT | 图片逐页插入 .pptx |
| | 图片格式互转 | JPG/PNG/WebP/BMP/GIF/TIFF 互转 |
| | 图片压缩 | 调整质量/尺寸压缩图片 |
| 🔧 PDF 工具箱 | PDF 合并 | 多个 PDF 按序合并（支持拖拽排序） |
| | PDF 压缩 | 压缩 PDF 文件体积 |
| | PDF 分割 | 按页码范围分割 PDF |
| | PDF 转 Excel | 提取 PDF 表格 → .xlsx |
| | PDF 转 PPT | .pdf → .pptx |
| | PDF 转 HTML | .pdf → .html |
| 🔐 安全 | PDF 加密 | 设置打开密码 |
| | PDF 解密 | 移除密码保护 |
| 📦 压缩归档 | 文件压缩 | 多文件打包为 ZIP/TAR.GZ/7z |
| | 文件解压 | 解压 ZIP/TAR.GZ/7z/TAR |
| | 压缩包解密 | 解密有密码的 ZIP/7z 压缩包 |

### 批量处理
- 单次可上传多个文件，批量转换自动打包 zip 下载
- 图片转 PDF / 图片转 PPT 支持最多 100 张
- PDF 合并最多 50 个文件

### 用户系统
- 邮箱注册 + 验证码
- 双模式计费：**按次** 或 **按有效期**
- 密码找回（邮箱验证码）
- 个人仪表盘（转换统计、模式分析、趋势图表）
- 转换历史记录查询
- 重复文件智能检测（避免误操作浪费次数）

### 游客模式（免登录体验）
- 未登录用户可直接访问主页，以**游客身份**使用全部转换功能
- 游客默认可体验 **1 次**转换（`GUEST_MAX_TIMES` 可配置），用完提示登录解锁更多权益
- 游客无需注册即可下载转换结果
- **防滥用机制**：游客次数存于 session cookie，可被无痕浏览/清 cookie 绕过，因此额外基于**真实 IP** 做双重限流（每小时 + 每日），换浏览器也无法绕过

### 管理后台
- 数据仪表盘（Chart.js 图表：模式饼图、趋势折线图、用户排行）
- 用户管理（充值次数、延长期限、封禁/解封）
- 公告管理（CRUD）
- 联系留言管理（支持多轮回复）
- IP 访问分析与地域分布（支持地图可视化）
- **转换来源分析**（登录用户 / 游客分层统计，IP 维度，可一键封禁或查看其日志）
- 转换日志查询（含 IP 列，支持按 IP / 用户名过滤，游客显示专属徽章）
- 存储空间统计

### 主题切换
- 日间模式 / 夜间模式 / 护眼模式（三档切换，持久化存储）

### 安全特性
- CSRF 防护（所有 POST 请求）
- 登录限流（IP + 用户名双维度，防暴力破解）
- 验证码三重限流（session + IP + 邮箱）
- IP 黑名单 + 地域封禁
- 文件双重扩展名检测
- 文件内容幻数校验（PDF/DOCX/XLSX/PPTX/JPG/PNG/GIF/BMP/TIFF/WebP）
- 可执行文件检测（PE/ELF/Mach-O/Shell Script/Java Class 黑名单）
- PDF 危险结构深度扫描（`/JS`、`/JavaScript`、`/Launch`、`/EmbeddedFile` 等）
- Office 文档安全检测（OOXML 结构校验 + 嵌入可执行文件 + VBA 宏检测）
- HTML 危险内容扫描（`<script>`、`<iframe>`、`javascript:`、`eval()` 等）
- 路径穿越防护（文件下载路径安全验证）
- X-Forwarded-For 信任代理白名单
- **游客防滥用**（真实 IP 维度限流：每小时 `GUEST_IP_HOURLY_LIMIT` 次 + 每日 `GUEST_IP_DAILY_LIMIT` 次）
- **转换日志 IP 溯源**（所有转换记录真实来源 IP，含游客）

## 环境要求

- **Python 3.8+**
- **MySQL 8.0+**
- **LibreOffice**（Office 转换必须）
- **Tesseract OCR**（OCR 识别必须）
- **中文字体**（PDF 中文正常显示）

### 安装系统依赖

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
| `DB_POOL_SIZE` | 数据库连接池大小 | `10` |
| `PORT` | 服务端口 | `5000` |
| `UPLOAD_MAX_SIZE` | 单文件大小上限 (MB) | `50` |
| `CDN_BASE_URL` | 前端 CDN 资源地址 | `https://cdn.staticfile.org` |

### 游客模式

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GUEST_MAX_TIMES` | 游客可免费体验的转换次数 | `1` |
| `GUEST_IP_HOURLY_LIMIT` | 同一 IP 每小时最多游客转换次数（防滥用） | `5` |
| `GUEST_IP_DAILY_LIMIT` | 同一 IP 每天（24h 滑动窗口）最多游客转换次数（防滥用） | `10` |

### 安全相关

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CSRF_ENABLED` | 是否启用 CSRF 防护 | `1` |
| `LOGIN_RATE_LIMIT` | 登录失败阈值 | `10` |
| `LOGIN_RATE_WINDOW` | 登录限流窗口 (秒) | `300` |
| `PASSWORD_MIN_LENGTH` | 最小密码长度 | `8` |
| `VERIFY_CODE_RESEND_INTERVAL` | 验证码重发间隔 (秒) | `60` |
| `VERIFY_CODE_EXPIRE` | 验证码过期时间 (秒) | `300` |
| `VERIFY_CODE_IP_LIMIT` | 验证码 IP 限流次数 | `5` |
| `VERIFY_CODE_IP_WINDOW` | 验证码 IP 限流窗口 (秒) | `3600` |
| `TRUSTED_PROXY_IPS` | 代理信任白名单（逗号分隔） | `127.0.0.1,::1` |

## LibreOffice 转换说明

- 首次转换约 5-10 秒（LibreOffice 后台进程初始化）
- 所有 Office 转换使用互斥锁串行执行（防止 LibreOffice 实例冲突）
- 如转换中文 PDF 出现乱码，请安装中文字体后再试

## 项目结构

```
├── app.py                     # Flask 应用入口、中间件（CSRF、IP 封禁、访问日志）
├── config.py                  # 配置类（所有配置从 .env 读取）
├── requirements               # Python 依赖清单
├── start.sh                   # 启动脚本
├── converter/
│   ├── __init__.py
│   └── converter_engine.py    # 核心转换引擎（LibreOffice、OCR、PDF、图片、压缩等）
├── database/
│   ├── __init__.py
│   └── db_manager.py          # 数据库管理器（连接池、用户、日志、IP、公告等）
├── routes/
│   ├── __init__.py
│   ├── auth.py                # 用户认证（登录/注册/找回密码）
│   ├── converter.py           # 核心业务（文件上传/转换/下载/仪表盘）
│   └── admin.py               # 管理后台
├── utils/
│   ├── __init__.py            # 安全工具集（CSRF、限流、IP 获取、文件幻数校验）
│   ├── logger.py              # 统一日志配置（按天轮转，保留 30 天）
│   └── mail.py                # SMTP 邮件发送
├── templates/                 # Jinja2 模板（13 个页面）
├── static/                    # 静态资源（CSS/JS）
├── uploads/                   # 上传文件（临时，超时自动清理）
├── outputs/                   # 转换结果（临时，超时自动清理）
└── logs/                      # 日志文件
```

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `users` | 用户表（密码哈希、角色、过期时间、剩余次数） |
| `conversion_logs` | 转换日志（用户、模式、状态、来源 IP，游客用户名为 `guest`） |
| `announcements` | 系统公告 |
| `ip_access_logs` | IP 访问日志（含地理位置） |
| `ip_blacklist` | IP 黑名单 |
| `contact_messages` | 联系留言 |
| `contact_replies` | 留言回复（支持多轮） |
| `login_attempts` | 登录尝试记录（用于限流） |

## API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（文件转换，未登录以游客身份访问） |
| `/convert` | POST | 执行文件转换 |
| `/download/<filename>` | GET | 下载转换后的文件 |
| `/dashboard` | GET | 用户个人仪表盘 |
| `/api/dashboard_stats` | GET | 仪表盘统计数据 API |
| `/my_logs` | GET | 个人转换记录 |
| `/login` | GET/POST | 登录 |
| `/register` | GET/POST | 注册 |
| `/forgot_password` | GET/POST | 找回密码 |
| `/send_verify_code` | POST | 发送邮箱验证码 |
| `/logout` | GET | 退出登录 |
| `/contact` | GET/POST | 联系/留言 |
| `/admin` | GET | 管理后台主页 |
| `/admin/dashboard` | GET | 管理后台全屏图表 |
| `/admin/<action>` | POST | 用户管理操作（封禁/解封/续期/充值） |
| `/admin/announcements` | GET/POST | 公告管理 |
| `/admin/ip_analysis` | GET | IP 访问分析（含用户/游客转换来源分析） |
| `/admin/contacts` | GET | 联系留言管理 |

## 技术栈

| 层次 | 技术 |
|------|------|
| Web 框架 | Flask（Jinja2 模板引擎） |
| 数据库 | MySQL 8.0+（mysql-connector-python，连接池） |
| 前端 | Bootstrap 5.3 + Font Awesome 6.4 + jQuery 3.7 + Chart.js 4.4（CDN 引入） |
| 转换引擎 | LibreOffice（headless）、pdf2docx、PyPDF2、pdf2image、pdfplumber、pandas、Pillow、pytesseract、python-pptx、markdown、pyzipper、py7zr、edge-tts |
| 安全 | werkzeug 密码哈希（pbkdf2:sha256）、CSRF Token、IP 限流、文件幻数校验、双重扩展名检测 |
| 日志 | Python logging + TimedRotatingFileHandler（按天轮转，保留 30 天） |
| 邮件 | SMTP（SSL） |

## 注意事项

1. **路径分隔符** — Linux 使用 `/`，已全部适配
2. **文件清理** — `uploads/` 和 `outputs/` 中的超时文件（默认 7 天）在应用退出时自动清理
3. **MySQL 连接** — 推荐 `localhost`（socket 连接，比 TCP 更快）
4. **生产环境** — 关闭调试模式：`export FLASK_DEBUG=0`
5. **后台运行** — `nohup ./start.sh > output.log 2>&1 &`
6. **代理环境** — 如使用 Nginx / Cloudflare，配置 `TRUSTED_PROXY_IPS` 以获取真实 IP
7. **LibreOffice 互斥锁** — 所有 Office 相关转换使用线程锁串行执行，避免 LibreOffice 实例冲突
8. **OCR 超时控制** — 使用 `ThreadPoolExecutor` + `future.result(timeout)` 实现跨平台线程安全超时，避免卡死
9. **游客防滥用** — 游客次数存于 cookie，可用无痕浏览/清 cookie 绕过；管理员可在 **IP 分析 → 转换来源分析** 中按真实 IP 监控游客转换行为，异常高频 IP 建议封禁
