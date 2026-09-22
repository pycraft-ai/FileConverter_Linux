# =============================================
# Gunicorn 生产部署配置
# 用法：
#   gunicorn -c gunicorn.conf.py app:app
# =============================================
import os
from dotenv import load_dotenv
load_dotenv()

# 绑定地址（由 Cloudflare Tunnel / Nginx 反代对外）。
# 默认仅本地回环，切勿绑定 0.0.0.0 直连公网，
# 否则攻击者可伪造 CF-Connecting-IP 绕过 IP 黑名单。
# Docker 容器内用 BIND_HOST=0.0.0.0 覆盖，让 cloudflared（同容器网络）能访问。
bind_host = os.environ.get('BIND_HOST', '127.0.0.1')
bind = f'{bind_host}:' + os.environ.get('PORT', '5000')

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

# =============================================
# 日志
# =============================================
# 为什么默认格式里的 IP 恒为 127.0.0.1：
#   gunicorn 只监听回环（见上方 bind），前面是 Cloudflare Tunnel（cloudflared），
#   TCP 对端永远是 127.0.0.1，而 gunicorn access log 的 %(h)s 取的就是对端地址。
#   真实用户 IP 由 Cloudflare 放在 CF-Connecting-IP 请求头里
#   （应用侧 get_client_ip() 也是读这个头），所以这里直接取该请求头，
#   而不是 %(h)s。同时去掉 UA / Referer，让单行从 ~250 字符缩到 ~80 字符。
from gunicorn.glogging import Logger as _GunicornLogger


def _short_device(user_agent: str) -> str:
    """把 User-Agent 压成 "平台/浏览器" 的短标签，例如 Win/Edge、iOS/Safari。

    只做粗粒度归类，目的是在日志里一眼看出"什么设备访问的"，
    不追求精确版本号（需要精确信息时查数据库里的完整 UA）。
    """
    if not user_agent:
        return 'Unknown'

    u = user_agent.lower()

    # 1) 爬虫与命令行工具（放在最前，避免被当成普通浏览器）
    if any(k in u for k in ('bot', 'spider', 'crawler', 'slurp',
                            'curl', 'wget', 'python-requests', 'httpx',
                            'headless', 'scrapy', 'okhttp')):
        return 'Bot'

    # 2) 操作系统（先判移动端与国产系统）
    if 'iphone' in u:
        os_name = 'iOS'
    elif 'ipad' in u:
        os_name = 'iPad'
    elif 'android' in u:
        os_name = 'Android'
    elif 'harmony' in u or 'huawei' in u:
        os_name = 'Harmony'
    elif 'windows' in u:
        os_name = 'Win'
    elif 'mac os x' in u or 'macintosh' in u:
        os_name = 'macOS'
    elif 'linux' in u:
        os_name = 'Linux'
    else:
        return 'Unknown'

    # 3) 浏览器（顺序重要：Edge/Opera 的 UA 里同样带 Chrome/Safari 字样）
    if 'micromessenger' in u:
        br = 'WeChat'
    elif 'edg/' in u or 'edga' in u or 'edgios' in u:
        br = 'Edge'
    elif 'opr/' in u or 'opera' in u:
        br = 'Opera'
    elif 'firefox' in u or 'fxios' in u:
        br = 'Firefox'
    elif 'chrome' in u or 'crios' in u:
        br = 'Chrome'
    elif 'safari' in u:
        br = 'Safari'
    else:
        br = 'Other'

    return '%s/%s' % (os_name, br)


class _DeviceAccessLogger(_GunicornLogger):
    """在 access log 里附带简短设备信息与紧凑路径。

    gunicorn 的日志格式只能引用「请求头」和「WSGI environ 变量」，
    不能解析 User-Agent。所以这里先把解析结果注入 environ，
    再由 access_log_format 通过 %({short_device}e)s 引用。
    environ 的键会被 gunicorn 统一转小写，因此格式串里写小写名。
    """

    def access(self, resp, req, environ, request_time):
        environ['short_device'] = _short_device(environ.get('HTTP_USER_AGENT', ''))
        # 紧凑路径：/login?next=%2F（默认 %(r)s 会多带 "HTTP/1.1"）
        query = environ.get('QUERY_STRING', '')
        environ['short_path'] = environ.get('PATH_INFO', '') + (('?' + query) if query else '')
        super().access(resp, req, environ, request_time)


logger_class = _DeviceAccessLogger

# 格式：时间 | 真实 IP | 设备 | 方法 路径 | 状态码 | 耗时
# 单行约 100 字符，比 gunicorn 默认 combined 格式（约 250 字符）短一半以上
access_log_format = (
    '%(t)s | %({cf-connecting-ip}i)s | %({short_device}e)s | '
    '%(m)s %({short_path}e)s | %(s)s | %(M)sms'
)

# 访问日志去向（GUNICORN_ACCESS_LOG 环境变量控制）：
#   '-'（默认）  输出到标准输出，随 docker logs / systemd journal 一起收集
#   文件路径     如 logs/access.log，只写文件，终端与 journal 仅保留应用日志
#   off/none/0   完全关闭（访问明细应用已异步写入数据库，
#                可在后台「IP 分析」查看；关闭后日志最干净、且少一次磁盘写）
_access_log_target = os.environ.get('GUNICORN_ACCESS_LOG', '-')
accesslog = None if _access_log_target.lower() in ('off', 'none', '0') else _access_log_target

errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# 进程名，便于识别
proc_name = 'fileconverter'

# 优雅启动 worker（逐个启动，避免瞬时压力）
preload_app = False
