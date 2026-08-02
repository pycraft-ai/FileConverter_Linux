import os
import secrets
from dotenv import load_dotenv

# 加载 .env 文件（如果存在），使用绝对路径避免目录问题
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path)


class Config:
    # Flask 密钥，用于 session（未设置时自动生成随机密钥，重启后 session 失效）
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

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

    # ---- 管理员账号 ----
    # 生产环境必须通过 .env 设置强密码，不再提供弱默认值
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')        # 不再有默认值！
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')

    # 连接池配置
    DB_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', 10))
    FILE_CLEANUP_TTL = 1 * 24 * 3600  # 文件清理TTL（秒），改为7天以支持历史记录下载

    # ---- 游客模式 ----
    # 未登录游客可免费体验的转换次数（默认 1 次），用完提示登录解锁更多权益
    GUEST_MAX_TIMES = int(os.environ.get('GUEST_MAX_TIMES', 1))

    # ---- 游客防滥用（IP 维度限流）----
    # 注意：游客次数存在 session cookie，可通过无痕浏览/清 cookie 绕过。
    # 以下基于真实 IP 的限流，无论用户如何刷新/换浏览器都无法绕过。
    # 同一 IP 每小时最多可进行的游客转换次数
    GUEST_IP_HOURLY_LIMIT = int(os.environ.get('GUEST_IP_HOURLY_LIMIT', 5))
    # 同一 IP 每天最多可进行的游客转换次数（使用 24 小时滑动窗口近似"每天"）
    GUEST_IP_DAILY_LIMIT = int(os.environ.get('GUEST_IP_DAILY_LIMIT', 10))

    # 验证码配置
    VERIFY_CODE_RESEND_INTERVAL = int(os.environ.get('VERIFY_CODE_RESEND_INTERVAL', 60))
    VERIFY_CODE_EXPIRE = int(os.environ.get('VERIFY_CODE_EXPIRE', 300))

    # CDN 静态资源地址
    CDN_BASE_URL = os.environ.get('CDN_BASE_URL', 'https://cdn.staticfile.org')

    # IP 分析配置
    IP_ANALYSIS_DEFAULT_HOURS = int(os.environ.get('IP_ANALYSIS_DEFAULT_HOURS', 24))
    IP_BLOCKED_CACHE_TIME = int(os.environ.get('IP_BLOCKED_CACHE_TIME', 60))
    IP_LOCATION_API_TIMEOUT = int(os.environ.get('IP_LOCATION_API_TIMEOUT', 5))
    IP_LOCATION_REQUEST_INTERVAL = float(os.environ.get('IP_LOCATION_REQUEST_INTERVAL', 0.5))

    # ===== 安全配置 =====

    # -- CSRF --
    CSRF_ENABLED = os.environ.get('CSRF_ENABLED', '1') == '1'

    # -- 限流 --
    # 登录失败限制：同一 IP 或用户名在窗口期内最多尝试 N 次
    LOGIN_RATE_LIMIT = int(os.environ.get('LOGIN_RATE_LIMIT', 10))
    LOGIN_RATE_WINDOW = int(os.environ.get('LOGIN_RATE_WINDOW', 300))
    # 验证码发送限制：同一 IP 每小时最多 N 次
    VERIFY_CODE_IP_LIMIT = int(os.environ.get('VERIFY_CODE_IP_LIMIT', 5))
    VERIFY_CODE_IP_WINDOW = int(os.environ.get('VERIFY_CODE_IP_WINDOW', 3600))

    # -- 密码策略 --
    PASSWORD_MIN_LENGTH = int(os.environ.get('PASSWORD_MIN_LENGTH', 8))

    # -- 代理信任 --
    # 只有来自这些 IP 的请求才信任 X-Forwarded-For / CF-Connecting-IP 头
    TRUSTED_PROXY_IPS = [
        ip.strip() for ip in os.environ.get('TRUSTED_PROXY_IPS', '127.0.0.1,::1').split(',')
    ]

    # ===== 邮箱 SMTP 配置（用于注册验证码） =====
    MAIL_HOST = os.environ.get('MAIL_HOST')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USER = os.environ.get('MAIL_USER')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_SSL = True

    # 确保上传和输出目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
