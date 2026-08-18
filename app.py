from flask import Flask, request, abort, send_from_directory, send_file
from config import Config
from database.db_manager import DatabaseManager
from utils import generate_csrf_token, validate_csrf, get_client_ip, setup_logger, get_logger
import os
import time
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor
# 导入蓝图
from routes.auth import auth_bp
from routes.converter import converter_bp
from routes.admin import admin_bp

import dotenv
from datetime import timedelta

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
dotenv.load_dotenv(_env_path)

# 初始化日志系统
logger = setup_logger()


app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PREFERRED_URL_SCHEME'] = 'https'  # Cloudflare 代理下保证 URL 正确

# ===== Session Cookie 安全属性（公网部署必须开启）=====
# SECURE：仅 HTTPS 传输（走 Cloudflare Tunnel 时为 True）
app.config['SESSION_COOKIE_SECURE'] = True
# HTTPONLY：禁止 JS 读取，降低 XSS 窃取 session 风险
app.config['SESSION_COOKIE_HTTPONLY'] = True
# SAMESITE：防御 CSRF
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# 会话过期时间，避免永久有效
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(converter_bp)
app.register_blueprint(admin_bp)


# 自定义 Jinja2 过滤器：计算剩余时间
@app.template_filter('time_remaining')
def time_remaining_filter(expiration_str):
    """根据过期时间字符串返回 'X天X时' 格式的剩余时间"""
    from datetime import datetime
    if not expiration_str:
        return '--'
    try:
        expiration = datetime.strptime(str(expiration_str), '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        delta = expiration - now
        if delta.total_seconds() <= 0:
            return '已过期'
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f'{days}天{hours}时'
        else:
            minutes = (delta.seconds % 3600) // 60
            return f'{hours}时{minutes}分'
    except (ValueError, TypeError):
        return str(expiration_str)


# 全局模板变量：CSRF token + CDN URL
@app.context_processor
def inject_global_vars():
    return {
        'CDN_BASE_URL': Config.CDN_BASE_URL,
        'csrf_token': generate_csrf_token,
    }

# 全局线程池，复用线程执行异步日志写入
log_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='log_writer')


@atexit.register
def cleanup():
    """应用退出时清理资源"""
    try:
        _stop_periodic_cleanup()
    except Exception:
        pass
    try:
        log_executor.shutdown(wait=True, timeout=5)
    except Exception:
        pass
    try:
        DatabaseManager.shutdown_pool()
    except Exception:
        pass


# 静态资源路径列表，跳过日志记录以减少数据库压力
_SKIP_LOG_PATHS = frozenset([
    '/static/', '/favicon.ico', '/admin/unread_count',
    '/api/user_unread_replies'
])

# CSRF 豁免路径（第三方回调等）
_CSRF_EXEMPT_PATHS = frozenset([
    '/send_verify_code',   # 注册/找回密码时尚未登录，CSRF token 仍可用于表单
])


def _should_skip_log(path):
    """判断是否跳过该路径的访问日志记录"""
    if path.startswith('/static/'):
        return True
    return path in _SKIP_LOG_PATHS


@atexit.register
def cleanup_old_files():
    """清理超时的上传/输出文件（含子目录）"""
    _do_cleanup_old_files()


_cleanup_event = None  # 用于通知清理线程退出

# ===== 惰性初始化（兼容 gunicorn 多 worker 与开发模式）=====
# gunicorn 通过 import app 加载，不会执行 if __name__=='__main__' 中的代码。
# 因此数据库初始化、后台清理线程改为在首个请求到来时惰性启动，保证两种方式都可用。
_lazy_init_done = False
_lazy_init_lock = None


def _ensure_initialized():
    """确保数据库已初始化、后台清理线程已启动（线程安全，只执行一次）。

    gunicorn 的每个 worker 进程独立，各自会在首个请求时执行一次初始化。
    """
    global _lazy_init_done, _lazy_init_lock
    if _lazy_init_done:
        return
    if _lazy_init_lock is None:
        _lazy_init_lock = threading.Lock()
    with _lazy_init_lock:
        if _lazy_init_done:
            return
        try:
            logger.info("正在初始化数据库...")
            DatabaseManager.initialize_database()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.error("数据库初始化失败: %s", e)

        _start_periodic_cleanup()
        logger.info("后台文件清理任务已启动（间隔 1 小时）")

        _lazy_init_done = True


def _is_plaintext_residual(filepath):
    """判断文件是否为明文残留（非加密文件）。

    当文件加密功能开启时，正常的落盘文件（上传/输出）都应为 Fernet 密文，
    其特征是 base64 开头为 'gAAAAA'。若文件不是密文，则属于明文残留，应清理。
    当加密功能关闭时，文件本就是明文，不视为残留。
    """
    try:
        if not Config.FILE_ENCRYPTION_ENABLED:
            return False
        with open(filepath, 'rb') as f:
            head = f.read(6)
        # Fernet token 固定以 base64 'gAAAAA' 开头
        return head != b'gAAAAA'
    except Exception:
        return False


def _do_cleanup_old_files():
    """执行一次文件清理"""
    import shutil
    ttl = Config.FILE_CLEANUP_TTL
    now = time.time()
    for folder in [Config.UPLOAD_FOLDER, Config.OUTPUT_FOLDER]:
        if not os.path.isdir(folder):
            continue
        for entry in os.listdir(folder):
            entry_path = os.path.join(folder, entry)
            try:
                if os.path.isfile(entry_path):
                    # 隐私保护：若文件是明文残留（未加密），无论是否超时都立即清除，
                    # 防止加密功能启用前的旧明文文件在磁盘上滞留。
                    if _is_plaintext_residual(entry_path) or now - os.path.getmtime(entry_path) > ttl:
                        os.remove(entry_path)
                elif os.path.isdir(entry_path) and now - os.path.getmtime(entry_path) > ttl:
                    shutil.rmtree(entry_path, ignore_errors=True)
            except Exception:
                pass


def _start_periodic_cleanup():
    """启动后台定时清理线程（每小时执行一次）"""
    global _cleanup_event
    _cleanup_event = threading.Event()

    def _loop():
        while not _cleanup_event.wait(3600):  # 每小时检查一次
            try:
                _do_cleanup_old_files()
            except Exception:
                pass
            # 清理过期的登录尝试记录，防止表无限膨胀（数据库 DoS 防护）
            try:
                DatabaseManager.cleanup_old_login_attempts(retention_hours=24)
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True, name='file_cleanup')
    t.start()


def _stop_periodic_cleanup():
    """停止后台清理线程"""
    global _cleanup_event
    if _cleanup_event:
        _cleanup_event.set()


@app.before_request
def before_request():
    """请求前处理：惰性初始化 + CSRF 校验 + IP 黑名单检查 + 记录开始时间 + 生成 CSP nonce"""
    # 0. 惰性初始化（首次请求时建表并启动后台清理线程；gunicorn/开发模式均适用）
    _ensure_initialized()

    # 0.5 提前生成 CSP nonce（模板渲染发生在 after_request 之前）
    import secrets
    from flask import g
    g.csp_nonce = secrets.token_hex(16)

    # 1. CSRF 防护（跳过 GET/HEAD/OPTIONS）
    if Config.CSRF_ENABLED and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.path not in _CSRF_EXEMPT_PATHS:
            if not validate_csrf():
                return {'success': False, 'message': 'CSRF 校验失败，请刷新页面后重试'}, 403

    # 2. 安全获取真实 IP（只信任可信代理）
    ip_address = get_client_ip()

    # 3. 检查 IP 是否在黑名单中
    is_blocked, block_info = DatabaseManager.is_ip_blocked(ip_address)
    if is_blocked:
        reason = block_info.get('reason', '未知原因') if block_info else '未知原因'
        return f'您的IP已被封禁，原因：{reason}', 403

    # 4. 记录请求开始时间
    request.start_time = time.time()


@app.after_request
def after_request(response):
    """请求后处理：设置安全响应头 + 异步记录访问日志（跳过静态资源）"""
    try:
        # ===== 安全响应头 =====
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        # 防 XSS 兜底。动态放行 Config.CDN_BASE_URL 的域名（模板所有 CDN 资源都走它），
        # 避免 CSP 误拦静态资源导致图标/样式失效。
        try:
            from urllib.parse import urlparse
            cdn_host = urlparse(Config.CDN_BASE_URL).netloc
        except Exception:
            cdn_host = 'cdn.staticfile.org'
        if not cdn_host:
            cdn_host = 'cdn.staticfile.org'
        cdn_src = f'https://{cdn_host}'
        # 注意：script-src / style-src 中保留 'unsafe-inline'，并且**不能再带 nonce**。
        # 模板大量使用内联 style="..." 属性与 onclick/onchange 等内联事件处理器，
        # 这些属于 HTML 属性而非 <style>/<script> 标签，nonce 无法放行，
        # 必须靠 'unsafe-inline'。
        # CSP 规范：一旦 source list 中出现 nonce 或 hash，浏览器会**忽略** 'unsafe-inline'，
        # 导致内联属性依然被拦截，页面所有默认隐藏区域会被错误显示出来。
        response.headers['Content-Security-Policy'] = (
            f"default-src 'self'; "
            f"script-src 'self' 'unsafe-inline' {cdn_src} https://cdn.jsdelivr.net; "
            f"style-src 'self' 'unsafe-inline' {cdn_src} https://cdn.jsdelivr.net; "
            # 文件预览使用 blob: URL（本地图片/PDF），需在对应指令放行 blob:
            # - img-src blob:   支持本地图片预览（previewFile 用 URL.createObjectURL）
            # - frame-src blob: 支持 iframe 内嵌本地 PDF（Chrome 内置 PDF 查看器走 frame-src）
            # 保留 object-src 'none'，禁止外部插件加载，降低风险
            f"img-src 'self' data: blob: https:; "
            f"font-src 'self' {cdn_src} https://cdn.jsdelivr.net data:; "
            f"connect-src 'self' https:; "
            f"frame-src 'self' blob:; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"frame-ancestors 'none'"
        )
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=()'
        )
        # HSTS：强制浏览器仅经 HTTPS 访问（仅当全站 HTTPS 时开启）
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
        # 记录访问日志前先设置安全头，保证跳过日志时安全头仍生效
        if _should_skip_log(request.path):
            return response

        # 安全获取真实 IP
        ip_address = get_client_ip()

        # 计算响应时间
        response_time = 0
        if hasattr(request, 'start_time'):
            response_time = round(time.time() - request.start_time, 4)

        # 提前获取所有数据，避免请求上下文问题
        log_data = {
            'ip_address': ip_address,
            'request_url': request.url,
            'request_method': request.method,
            'user_agent': request.user_agent.string[:500] if request.user_agent else '',
            'referer': (request.referrer or '')[:500],
            'status_code': response.status_code,
            'response_time': response_time
        }

        log_executor.submit(_log_access, log_data)

    except Exception as e:
        logger.warning("记录访问日志失败: %s", e)

    return response


def _log_access(data):
    """线程池任务：记录 IP 访问日志"""
    try:
        DatabaseManager.log_ip_access(
            ip_address=data['ip_address'],
            request_url=data['request_url'],
            request_method=data['request_method'],
            user_agent=data['user_agent'],
            referer=data['referer'],
            status_code=data['status_code'],
            response_time=data['response_time']
        )
    except Exception as e:
        logger.error("异步记录IP访问日志失败: %s", e)


@app.route('/favicon.ico')
def favicon():
    """根路径 favicon 兜底（浏览器会主动请求 /favicon.ico，不走 /static/）。"""
    return send_from_directory(
        os.path.join(app.static_folder, ''),
        'favicon.ico',
        mimetype='image/x-icon',
        max_age=86400,  # 1 天缓存；CDN/浏览器自身会再缓存
    )


# ===== 站点所有权验证文件（白名单机制）=====
# 用于 Bing / Google / 百度等站长平台的站点验证文件。
# 直接把验证文件放到项目根目录，BingSiteAuth.xml 等会自动被映射到根路径。
# 严格白名单：仅允许已知的验证文件名，防止任意文件泄露。
_VERIFICATION_FILE_WHITELIST = {
    'BingSiteAuth.xml',                  # Bing 站长工具
    'google-site-verification.html',     # Google 部分验证方式
}
# 百度验证文件名以前缀 baidu_verify_ 开头、以 .html 结尾（实际文件名由百度随机生成，无法枚举）
_BAIDU_VERIFY_PREFIX = 'baidu_verify_'


@app.route('/<path:filename>')
def site_verification_file(filename):
    """根路径静态文件兜底（仅服务于站点所有权验证文件）。

    仅当请求文件名命中白名单、且文件确实存在于项目根目录时，才返回。
    其他情况一律走 404，保证不暴露项目其他文件。
    """
    # 1. 拒绝路径穿越（防止 ../app.py 之类）
    if '..' in filename or filename.startswith('/') or '\\' in filename:
        abort(404)
    # 2. 必须是白名单内的文件名（百度验证文件用前缀匹配）
    is_whitelisted = (
        filename in _VERIFICATION_FILE_WHITELIST
        or (filename.startswith(_BAIDU_VERIFY_PREFIX) and filename.endswith('.html'))
    )
    if not is_whitelisted:
        abort(404)
    # 3. 文件必须真实存在
    project_root = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(project_root, filename)
    if not os.path.isfile(file_path):
        abort(404)
    # 4. serve
    return send_file(file_path, max_age=300)


@app.errorhandler(404)
def not_found(e):
    return '页面不存在', 404


@app.errorhandler(500)
def server_error(e):
    return '服务器内部错误', 500


if __name__ == '__main__':
    # 开发模式：与 gunicorn 一致，走惰性初始化（建表 + 启动后台清理线程）
    _ensure_initialized()

    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    # 公网部署必须：bind 仅本地回环，由 Cloudflare Tunnel / Nginx 反代对外。
    # 若直连 0.0.0.0 暴露 5000 端口，攻击者可伪造 CF-Connecting-IP 绕过 IP 黑名单。
    bind_host = os.environ.get('BIND_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    logger.info("应用启动 | host=%s port=%s debug=%s", bind_host, port, debug_mode)
    app.run(host=bind_host, port=port, debug=debug_mode)
