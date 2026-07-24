# FileConverter (Linux/WSL 版) 🐧

**多格式文件在线转换工具** — 基于原项目的 WSL/Linux 适配版本。

使用 **LibreOffice** 替代 Windows COM 组件实现 Office 文档转换。

## 与原版的区别

| 特性 | Windows 版 | **Linux/WSL 版** |
|------|-----------|-----------------|
| Word/Excel/PPT → PDF | Microsoft Office COM | **LibreOffice** |
| MD/HTML → PDF | Word COM 中转 | **LibreOffice** |
| PDF → Word / 图片 | pdf2docx / pdf2image | ✅ 相同（跨平台） |
| 图片 → PDF / PPT | Pillow / python-pptx | ✅ 相同（跨平台） |
| CSV ↔ Excel | pandas | ✅ 相同（跨平台） |
| OCR 识别 | Tesseract | ✅ 相同（Linux 上更稳定） |
| PDF 合并 | PyPDF2 | ✅ 相同（跨平台） |

## 环境要求

- **Python 3.8+**
- **MySQL 8.0+** — `sudo apt install mysql-server`
- **LibreOffice**（Office 转 PDF 必须）：
  ```bash
  sudo apt install libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress
  ```
- **Tesseract OCR**（OCR 识别必须）：
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
  ```
- **中文字体**（PDF 中文正常显示）：
  ```bash
  sudo apt install fonts-noto-cjk fonts-wqy-zenhei
  ```

## 快速开始

```bash
# 1. 配置 MySQL（WSL 内安装）
sudo service mysql start
sudo mysql -e "CREATE USER 'fileconverter'@'localhost' IDENTIFIED BY '你的密码';"
sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'fileconverter'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"

# 2. 配置环境变量
cp .env.example .env
vim .env

# 3. 启动
chmod +x start.sh
./start.sh
```

访问 `http://localhost:5000`，系统会自动初始化数据库和表。

## 配置说明

编辑 `.env` 文件：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | Flask Session 签名密钥 | **必填** |
| `DB_ACCOUNT` | MySQL 用户名 | **必填** |
| `DB_PASSWORD` | MySQL 密码 | **必填** |
| `DB` | 数据库名 | **必填** |
| `MAIL_HOST` | SMTP 服务器 | `smtp.qq.com` |
| `MAIL_PORT` | SMTP 端口 | `465` |
| `MAIL_USER` | SMTP 邮箱 | **必填** |
| `MAIL_PASSWORD` | SMTP 授权码 | **必填** |
| `ADMIN_PASSWORD` | 管理员密码 | **必填** |
| `DB_PORT` | MySQL 端口 | `3306` |
| `PORT` | 服务端口 | `5000` |

## LibreOffice 转换说明

- 首次启动约 5-10 秒（LibreOffice 后台进程初始化）
- 所有 Office 转换使用互斥锁串行执行（防止 LibreOffice 实例冲突）
- 如转换中文 PDF 出现乱码，请安装中文字体后再试

## 注意事项

1. **路径分隔符** — Linux 使用 `/`，本版已全部适配
2. **文件权限** — `uploads/` 和 `outputs/` 目录需写入权限
3. **MySQL 连接** — 推荐 `localhost`（socket 连接，比 TCP 更快）
4. **生产环境** — 关闭调试模式：`export FLASK_DEBUG=0`
5. **后台运行** — `nohup ./start.sh > output.log 2>&1 &`
