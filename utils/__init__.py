"""
安全工具模块：CSRF 防护、限流、安全 IP 获取、密码哈希、恶意文件检测、日志
"""
from utils.logger import setup_logger, get_logger
import os
import re
import struct
import time
import secrets
import zipfile
import functools
from collections import defaultdict
from threading import Lock

from flask import session, request, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash


# ==============================
# CSRF 防护
# ==============================

def generate_csrf_token():
    """生成并存储 CSRF token（每个 session 一个）"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf():
    """
    校验 CSRF token。
    跳过 GET/HEAD/OPTIONS 请求；从 form 或 X-CSRF-Token header 读取 token。
    返回 True 表示通过。
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return True

    token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
    stored = session.get('_csrf_token')

    if not token or not stored:
        return False
    # 常量时间比较，防止时序攻击
    return secrets.compare_digest(token, stored)


# ==============================
# 限流（内存实现，单进程适用）
# ==============================

_rate_limits: dict = defaultdict(list)
_rate_lock = Lock()


def check_rate_limit(key: str, max_requests: int, window_seconds: int):
    """
    检查是否超过速率限制（线程安全）。

    Args:
        key: 限流键（如 f"login:{ip}"）
        max_requests: 窗口内最大请求数
        window_seconds: 时间窗口（秒）

    Returns:
        (allowed: bool, remaining: int)
    """
    now = time.time()
    with _rate_lock:
        # 清理过期记录
        _rate_limits[key] = [t for t in _rate_limits[key] if now - t < window_seconds]
        current = len(_rate_limits[key])
        if current >= max_requests:
            return False, 0
        _rate_limits[key].append(now)
        return True, max_requests - current - 1


# ==============================
# 安全 IP 获取
# ==============================

def _is_loopback_or_private(ip_str):
    """
    判断给定 IP 字符串是否为回环/内网/链路本地地址（IPv4/IPv6 通用）。
    用于过滤 cloudflared 通过回环地址转发时误拿到的 ::1 / 127.0.0.1 等。
    """
    if not ip_str:
        return True
    ip_str = ip_str.strip()
    try:
        import ipaddress
        obj = ipaddress.ip_address(ip_str)
        return obj.is_loopback or obj.is_private or obj.is_link_local or obj.is_multicast or obj.is_unspecified
    except ValueError:
        return True  # 解析失败视为无效地址


def get_client_ip():
    """
    安全获取客户端真实 IP。
    优先使用可信代理头（CF-Connecting-IP / X-Forwarded-For）还原真实用户 IP，
    否则回退到 request.remote_addr。
    信任规则：
      1. 来自 TRUSTED_PROXY_IPS 白名单的请求（如本机回环）；
      2. 开启 TRUST_CF_CONNECTING_IP 时（cloudflared 与 Flask 同机部署），
         无论来源如何都优先信任 CF-Connecting-IP 头。

    增强：当 CF-Connecting-IP / X-Forwarded-For 返回的是回环/内网地址时
    （说明 cloudflared 未正确透传真实 IP，回退到了 ::1 / 127.0.0.1），
    会继续尝试下一个可信来源，而不是把回环地址当作真实用户 IP。
    """
    from config import Config

    candidates = []
    # 1. Cloudflare 透传的真实用户 IP 头
    cf_ip = request.headers.get('CF-Connecting-IP')
    if cf_ip:
        candidates.append(('cf', cf_ip.strip()))
    # 2. X-Forwarded-For（取最左侧原始客户端 IP）
    xff = request.headers.getlist('X-Forwarded-For')
    if xff:
        first = xff[0].split(',')[0].strip()
        if first:
            candidates.append(('xff', first))
    # 3. Cloudflare 附加的真实客户端端口（辅助，仅用于判断是否有 CF 头）
    has_cf_header = bool(request.headers.get('CF-IPCountry'))

    trust_cf = bool(Config.TRUST_CF_CONNECTING_IP)
    trust_remote = bool(request.remote_addr and request.remote_addr in Config.TRUSTED_PROXY_IPS)

    # 无条件信任 CF 头（cloudflared 与 Flask 同机部署且仅通过隧道暴露）
    if trust_cf:
        for _, ip in candidates:
            if not _is_loopback_or_private(ip):
                return ip
        # 兜底：如果 CF 头存在但取到的是回环/内网地址，说明透传有问题
        # 此时仍返回 CF 头的原始值，交由上层定位逻辑判断；同时若只有回环地址则回退 remote_addr
        if candidates:
            return candidates[0][1]

    # 只有来自可信代理的请求才信任代理头
    if trust_remote or has_cf_header:
        for _, ip in candidates:
            if not _is_loopback_or_private(ip):
                return ip
        if candidates:
            return candidates[0][1]

    return request.remote_addr or '0.0.0.0'


# ==============================
# 密码工具（werkzeug + 旧格式兼容）
# ==============================

def hash_password_secure(password: str) -> str:
    """
    使用 werkzeug 内置算法生成密码哈希（pbkdf2:sha256:…）。
    """
    return generate_password_hash(password)


def check_password_secure(password: str, stored_hash: str) -> bool:
    """
    验证密码（werkzeug 格式，支持 pbkdf2/scrypt）。
    旧版 SHA-256 格式返回 None 表示需要旧方法验证。
    """
    if stored_hash is None:
        return False
    # werkzeug 哈希特征：以算法名开头
    if stored_hash.startswith('pbkdf2:') or stored_hash.startswith('scrypt:'):
        return check_password_hash(stored_hash, password)
    # 旧格式：64 位 hex (SHA-256)，返回 None 让调用方用 salt 验证
    if len(stored_hash) == 64:
        try:
            int(stored_hash, 16)  # 验证是否为 hex
            return None  # 需要旧方法
        except ValueError:
            pass
    return False


# ==============================
# 恶意文件检测
# ==============================

# 幻数签名：(偏移量, 魔数十六进制)
# 用于验证文件扩展名与实际内容是否匹配
MAGIC_SIGNATURES = {
    'pdf': [
        (0, b'%PDF-'),
    ],
    'docx': [
        (0, b'PK\x03\x04'),    # Office Open XML (ZIP-based)
    ],
    'xlsx': [
        (0, b'PK\x03\x04'),    # Office Open XML
    ],
    'xls': [
        (0, b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'),  # OLE2 (旧格式)
    ],
    'pptx': [
        (0, b'PK\x03\x04'),    # Office Open XML
    ],
    'ppt': [
        (0, b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'),  # OLE2
    ],
    'jpg': [
        (0, b'\xFF\xD8\xFF'),
    ],
    'jpeg': [
        (0, b'\xFF\xD8\xFF'),
    ],
    'png': [
        (0, b'\x89PNG\r\n\x1A\n'),
    ],
    'gif': [
        (0, b'GIF87a'),
        (0, b'GIF89a'),
    ],
    'bmp': [
        (0, b'BM'),
    ],
    'tiff': [
        (0, b'II*\x00'),   # Little-endian
        (0, b'MM\x00*'),   # Big-endian
    ],
    'webp': [
        (0, b'RIFF'),      # RIFF 容器
    ],
    'csv': None,   # 纯文本格式，无固定幻数
    'md': None,    # 纯文本格式
    'txt': None,   # 纯文本格式
    'html': None,  # 文本格式，但会做内容检查
    'htm': None,   # 同 html
}

# PDF 危险关键字（可能包含嵌入式脚本或恶意动作）
_PDF_DANGEROUS_PATTERNS = [
    (b'/JS ', 'JavaScript 脚本'),
    (b'/JavaScript ', 'JavaScript 脚本'),
    (b'/Launch ', '启动动作'),
    (b'/EmbeddedFile ', '嵌入式文件'),
    (b'/OpenAction ', '自动打开动作'),
    (b'/AA ', '自动动作'),
    (b'/RichMedia ', '富媒体内容'),
    (b'/XFA ', 'XFA 表单（可能有动态内容）'),
]

# 可执行文件幻数黑名单（绝对不能上传）
_EXECUTABLE_SIGNATURES = [
    (0, b'MZ'),                  # Windows PE/EXE/DLL
    (0, b'\x7FELF'),             # Linux ELF
    (0, b'\xCF\xFA\xED\xFE'),    # Mach-O 64-bit (反向字节序)
    (0, b'\xFE\xED\xFA\xCE'),    # Mach-O 32-bit
    (0, b'\xFE\xED\xFA\xCF'),    # Mach-O 64-bit
    (0, b'#!'),                  # Shell script
    (0, b'\xCA\xFE\xBA\xBE'),    # Java class
]


def _read_file_bytes(filepath, num_bytes=12):
    """安全读取文件头字节"""
    try:
        with open(filepath, 'rb') as f:
            return f.read(num_bytes)
    except Exception:
        return None


def _check_executable(header):
    """检查文件头是否匹配可执行文件签名"""
    for offset, magic in _EXECUTABLE_SIGNATURES:
        end = offset + len(magic)
        if len(header) >= end and header[offset:end] == magic:
            return True
    return False


def validate_file_content(filepath: str, expected_ext: str) -> tuple[bool, str]:
    """
    通过文件幻数验证文件真实类型是否与扩展名匹配。

    Args:
        filepath: 文件路径
        expected_ext: 期望的扩展名（不含点）

    Returns:
        (is_valid: bool, error_message: str)
    """
    ext = expected_ext.lower()

    # 1. 检查是否存在
    if not os.path.exists(filepath):
        return False, '文件不存在'

    # 2. 读取文件头
    header = _read_file_bytes(filepath, 64)
    if header is None or len(header) == 0:
        return False, '无法读取文件内容'

    # 3. 可执行文件检测（所有文件类型都要检查）
    if _check_executable(header):
        return False, '检测到可执行文件格式，已拒绝'

    # 4. 幻数匹配
    signatures = MAGIC_SIGNATURES.get(ext)

    if signatures is None:
        # 无固定幻数的文本格式，做二进制/文本检测
        return _validate_text_file(filepath, header, ext)

    # 5. 检查幻数
    for offset, magic in signatures:
        end = offset + len(magic)
        if len(header) >= end and header[offset:end] == magic:
            # 对特定格式做深度检查
            if ext == 'pdf':
                return _validate_pdf_content(filepath)
            if ext in ('docx', 'xlsx', 'pptx'):
                return _validate_ooxml(filepath, ext)
            if ext in ('xls', 'ppt'):
                return _validate_ole2(filepath, ext)
            return True, ''

    return False, f'文件内容与 .{ext} 格式不匹配'


def _validate_text_file(filepath, header, ext):
    """
    验证文本类文件（csv, md, txt, html）。
    检查是否为二进制内容（包含过多 null 字节或控制字符）。
    """
    # HTML 文件需要检查 script 标签
    if ext in ('html', 'htm'):
        return _validate_html_file(filepath)

    # 检查是否为纯文本（非二进制）
    try:
        with open(filepath, 'rb') as f:
            content = f.read(4096)  # 读前4KB
    except Exception:
        return False, '无法读取文件'

    # 检测 null 字节（二进制文件的强烈信号）
    null_count = content.count(b'\x00')
    if null_count > len(content) * 0.01:  # 超过1%是null字节
        return False, '文件包含大量二进制数据，可能是恶意文件'

    # 检测是否为有效的文本编码
    try:
        content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            content.decode('latin-1')
        except UnicodeDecodeError:
            return False, '文件不是有效的文本格式'

    return True, ''


def _validate_html_file(filepath):
    """
    HTML 文件安全检查。
    检测潜在的恶意脚本、外部资源引用、iframe 等。
    """
    dangerous_tags = [
        (b'<script', 'script 标签'),
        (b'<iframe', 'iframe 标签'),
        (b'<object', 'object 标签'),
        (b'<embed', 'embed 标签'),
        (b'onerror=', '事件处理器 onerror'),
        (b'onload=', '事件处理器 onload'),
        (b'javascript:', 'javascript: 伪协议'),
        (b'eval(', 'eval() 调用'),
        (b'document.cookie', 'cookie 访问'),
    ]

    try:
        with open(filepath, 'rb') as f:
            content = f.read(65536).lower()  # 读前64KB并转小写
    except Exception:
        return False, '无法读取文件'

    for pattern, label in dangerous_tags:
        if pattern in content:
            return False, f'HTML 文件包含危险内容：{label}，已拒绝'

    return True, ''


def _validate_pdf_content(filepath):
    """PDF 文件深度安全扫描"""
    try:
        with open(filepath, 'rb') as f:
            # 只读前 128KB 做快速扫描
            content = f.read(131072)
    except Exception:
        return False, '无法读取 PDF 文件'

    # 查找危险 PDF 结构
    for pattern, label in _PDF_DANGEROUS_PATTERNS:
        if pattern in content:
            # 跳过大文件（全量扫描可能有开销）
            return False, f'PDF 包含潜在危险内容：{label}，已拒绝'

    return True, ''


def _validate_ooxml(filepath, ext):
    """
    验证 Office Open XML 文件（.docx, .xlsx, .pptx）。
    确认 ZIP 中包含预期的 Office 结构文件。
    """
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        return False, '文件不是有效的 ZIP 归档（Office 文档必须是 ZIP 格式）'
    except Exception:
        return False, '无法解析 Office 文档'

    # 检查核心结构文件
    has_content_types = any('[Content_Types].xml' in n for n in names)

    if not has_content_types:
        return False, 'ZIP 文件中缺少 Office 文档结构'

    # 检查是否有隐藏的可执行文件
    for name in names:
        lower_name = name.lower()
        if lower_name.endswith(('.exe', '.dll', '.vbs', '.js', '.ps1', '.bat', '.cmd', '.sh')):
            return False, f'Office 文档中包含可执行文件：{name}'

        # 检查是否有 OLE 对象（可能包含嵌入的恶意对象）
        if 'oleobject' in lower_name or 'embeddings' in lower_name:
            # 允许 OLE 对象，但记录警告
            pass

    return True, ''


def _validate_ole2(filepath, ext):
    """
    验证 OLE2 格式文件（旧版 .xls, .ppt）。
    检查宏病毒风险。
    """
    try:
        with open(filepath, 'rb') as f:
            content = f.read(65536)
    except Exception:
        return False, '无法读取文件'

    # OLE2 文件可能包含 VBA 宏
    # 检查宏签名（这只是一个基础检查）
    macro_indicators = [
        b'VBA_',           # VBA 项目
        b'_VBA_PROJECT',   # VBA 项目签名
        b'PROJECTwm',      # 旧格式 VBA
    ]

    for indicator in macro_indicators:
        if indicator in content:
            return False, f'文件包含 VBA 宏代码，存在安全风险，已拒绝'

    return True, ''


def validate_file_extension_extended(filename: str, filepath: str, expected_ext: str) -> tuple[bool, str]:
    """
    扩展验证：先检查扩展名白名单，再验证文件内容。

    这是一个便捷函数，组合了扩展名检查和内容验证。

    Returns:
        (is_valid: bool, error_message: str)
    """
    # 检查扩展名
    allowed_extensions = {'docx', 'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp',
                          'csv', 'xlsx', 'xls', 'pptx', 'ppt', 'txt', 'md', 'html', 'htm'}

    if '.' not in filename:
        return False, '文件缺少扩展名'

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return False, f'不支持的文件类型 .{ext}'

    # double extension attack: file.pdf.exe
    base = filename.rsplit('.', 1)[0]
    if '.' in base:
        inner_ext = base.rsplit('.', 1)[1].lower()
        if inner_ext in allowed_extensions and ext != inner_ext:
            return False, '检测到双重扩展名伪装攻击，已拒绝'

    # 内容验证
    return validate_file_content(filepath, ext)


# ==============================
# 输入清理
# ==============================

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除路径分隔符和危险字符。
    配合 werkzeug.utils.secure_filename 使用。
    """
    from werkzeug.utils import secure_filename
    return secure_filename(filename)


# ==============================
# 管理员权限装饰器
# ==============================

def admin_required(func):
    """
    统一的管理员权限校验装饰器。
    用法：@admin_required 放在 @admin_bp.route(...) 之下、def 之上。
    未登录或非管理员时：
      - AJAX/JSON 请求 → 返回 403 JSON
      - 普通页面请求 → flash 并跳转到首页（converter.index）
    这样可消除各路由手抄权限判断的遗漏风险。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if 'username' not in session or not session.get('is_admin'):
            # 区分 AJAX 与页面请求
            wants_json = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.is_json
                or 'application/json' in (request.headers.get('Accept') or '')
            )
            if wants_json:
                return jsonify({'success': False, 'message': '权限不足，请先以管理员身份登录'}), 403
            from flask import flash, redirect, url_for
            flash('管理员权限不足', 'error')
            return redirect(url_for('converter.index'))
        return func(*args, **kwargs)
    return wrapper
