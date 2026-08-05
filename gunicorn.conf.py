# =============================================
# Gunicorn 生产部署配置
# 用法：
#   gunicorn -c gunicorn.conf.py app:app
# =============================================
import os
from dotenv import load_dotenv
load_dotenv()

# 绑定仅本地回环地址（由 Cloudflare Tunnel / Nginx 反代对外）。
# 切勿绑定 0.0.0.0 直连公网，否则攻击者可伪造 CF-Connecting-IP 绕过 IP 黑名单。
bind = '127.0.0.1:' + os.environ.get('PORT', '5000')

# worker 数量：使用 gthread + 多线程模型，无需过多 worker。
# worker_class='gthread' 下每个 worker 可并发处理 threads 个请求，
# worker 过多会放大 MySQL 连接池占用（每 worker 独立池，DB_POOL_SIZE=10）。
# 默认 4 个 worker 即可支撑并发，如需更多可用 GUNICORN_WORKERS 覆盖。
workers = int(os.environ.get('GUNICORN_WORKERS', 4))

# 每个 worker 处理请求的线程数（gthread 模型下每个线程并发处理一个请求）
threads = int(os.environ.get('GUNICORN_THREADS', 4))

# 使用 gthread 类型，支持并发处理 IO 密集请求（文件转换、网络请求等）
worker_class = 'gthread'

# 单个请求最大处理时间（秒）。文件转换可能较慢，设为 300s，防止恶意慢请求占用 worker
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 300))

# 优雅超时（秒）：worker 收到 SIGTERM 后最多等待多久，超时强制 kill
graceful_timeout = 30

# keepalive：HTTP 连接复用时间（秒）
keepalive = 5

# 每个 worker 同时处理的最大连接数（防并发洪泛）
worker_connections = 1000

# 最大请求数后重启 worker，防止内存泄漏累积
max_requests = 1000
max_requests_jitter = 100

# 日志
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# 进程名，便于识别
proc_name = 'fileconverter'

# 优雅启动 worker（逐个启动，避免瞬时压力）
preload_app = False
