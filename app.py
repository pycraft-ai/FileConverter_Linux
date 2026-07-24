from flask import Flask, request, abort
from config import Config
from database.db_manager import DatabaseManager
from utils import generate_csrf_token, validate_csrf, get_client_ip
import os
import time
import atexit
from concurrent.futures import ThreadPoolExecutor
# 导入蓝图
from routes.auth import auth_bp
from routes.converter import converter_bp
from routes.admin import admin_bp

app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(converter_bp)
app.register_blueprint(admin_bp)


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
    """清理超时的上传/输出文件"""
    import glob
    ttl = Config.FILE_CLEANUP_TTL
    now = time.time()
    for folder in [Config.UPLOAD_FOLDER, Config.OUTPUT_FOLDER]:
        if os.path.isdir(folder):
            for f in glob.glob(os.path.join(folder, '*')):
                try:
                    if os.path.isfile(f) and now - os.path.getmtime(f) > ttl:
                        os.remove(f)
                except Exception:
                    pass


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
    """请求后处理：异步记录访问日志（跳过静态资源）"""
    try:
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
        print(f"记录访问日志错误: {e}")

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
        print(f"异步记录IP访问日志失败: {e}")


@app.errorhandler(404)
def not_found(e):
    return '页面不存在', 404


@app.errorhandler(500)
def server_error(e):
    return '服务器内部错误', 500


if __name__ == '__main__':
    print("正在初始化数据库...")
    DatabaseManager.initialize_database()
    print("数据库初始化完成")

    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
