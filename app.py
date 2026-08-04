from flask import Flask, request, abort
from config import Config
from database.db_manager import DatabaseManager
from utils import generate_csrf_token, validate_csrf, get_client_ip, setup_logger, get_logger
import os
import time
import atexit
from concurrent.futures import ThreadPoolExecutor
# 导入蓝图
from routes.auth import auth_bp
from routes.converter import converter_bp
from routes.admin import admin_bp

import dotenv

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
dotenv.load_dotenv(_env_path)

# 初始化日志系统
logger = setup_logger()


app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PREFERRED_URL_SCHEME'] = 'https'  # Cloudflare 代理下保证 URL 正确

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
                if os.path.isfile(entry_path) and now - os.path.getmtime(entry_path) > ttl:
                    os.remove(entry_path)
                elif os.path.isdir(entry_path) and now - os.path.getmtime(entry_path) > ttl:
                    shutil.rmtree(entry_path, ignore_errors=True)
            except Exception:
                pass


def _start_periodic_cleanup():
    """启动后台定时清理线程（每小时执行一次）"""
    import threading
    global _cleanup_event
    _cleanup_event = threading.Event()

    def _loop():
        while not _cleanup_event.wait(3600):  # 每小时检查一次
            try:
                _do_cleanup_old_files()
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
    """请求前处理：CSRF 校验 + IP 黑名单检查 + 记录开始时间"""
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
        # 防 XSS 兜底（内联脚本较多，采用宽松策略：允许自身脚本，禁外部注入）
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "connect-src 'self' https: http:"
        )
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=()'
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


@app.errorhandler(404)
def not_found(e):
    return '页面不存在', 404


@app.errorhandler(500)
def server_error(e):
    return '服务器内部错误', 500


if __name__ == '__main__':
    logger.info("正在初始化数据库...")
    DatabaseManager.initialize_database()
    logger.info("数据库初始化完成")

    # 启动后台定时文件清理（每小时执行一次）
    _start_periodic_cleanup()
    logger.info("后台文件清理任务已启动（间隔 1 小时）")

    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 5000))
    logger.info("应用启动 | port=%s debug=%s", port, debug_mode)
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
