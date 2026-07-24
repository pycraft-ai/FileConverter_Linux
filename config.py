import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()


class Config:
    # Flask 密钥，用于 session
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # 上传文件配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    UPLOAD_MAX_SIZE = int(os.environ.get('UPLOAD_MAX_SIZE', 50))  # 单个文件大小上限（MB）
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 最大上传 100MB
    ALLOWED_EXTENSIONS = {
        'docx', 'pdf', 'jpg', 'jpeg', 'png', 'csv', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'html', 'htm'
    }

    # MySQL 数据库配置（添加连接超时和自动重连）
    DB_CONFIG = {
        'host': 'localhost',
        'port': int(os.getenv('DB_PORT', 3306)),
        'user': os.getenv('DB_ACCOUNT'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB'),
        'connection_timeout': 5,
        'autocommit': True,
        'pool_reset_session': False,
        'charset': 'utf8mb4',
        'use_pure': True
    }

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '123456')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    # 连接池配置
    DB_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', 10))
    FILE_CLEANUP_TTL = 1 * 24 * 3600  # 文件清理TTL（秒），默认1天

    # 验证码配置
    VERIFY_CODE_RESEND_INTERVAL = int(os.environ.get('VERIFY_CODE_RESEND_INTERVAL', 60))
    VERIFY_CODE_EXPIRE = int(os.environ.get('VERIFY_CODE_EXPIRE', 300))

    # CDN 静态资源地址（CDN 不稳定时请切换备用的静态文件 CDN）
    CDN_BASE_URL = os.environ.get('CDN_BASE_URL', 'https://cdn.staticfile.org')

    # IP 分析配置
    IP_ANALYSIS_DEFAULT_HOURS = int(os.environ.get('IP_ANALYSIS_DEFAULT_HOURS', 24))
    IP_BLOCKED_CACHE_TIME = int(os.environ.get('IP_BLOCKED_CACHE_TIME', 60))
    IP_LOCATION_API_TIMEOUT = int(os.environ.get('IP_LOCATION_API_TIMEOUT', 5))
    IP_LOCATION_REQUEST_INTERVAL = float(os.environ.get('IP_LOCATION_REQUEST_INTERVAL', 0.5))

    # ===== 邮箱 SMTP 配置（用于注册验证码） =====
    # 以 QQ 邮箱为例：登录 mail.qq.com → 设置 → 账户 → 开启 SMTP 服务 → 获取授权码
    MAIL_HOST = os.environ.get('MAIL_HOST')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USER = os.environ.get('MAIL_USER')       # 你的 QQ 邮箱
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')  # QQ 邮箱授权码（非登录密码）
    MAIL_USE_SSL = True

    # 确保上传和输出目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
