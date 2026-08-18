"""
文件透明加解密工具模块（隐私保护核心）。

用途：
    用户上传的文件在服务器上以「密文」形式落盘，即使服务器被入侵、
    或能访问服务器的运维人员，也无法直接读取用户文件内容。

设计要点：
    1. 基于 cryptography 的 Fernet（AES-128-CBC + HMAC-SHA256）对称加密。
    2. 密钥通过环境变量 FILE_ENCRYPTION_KEY 提供（Base64 URL-safe），
       未设置时自动生成并提示持久化，避免首次启动即报错。
    3. 提供 `encrypt_file_in_place` / `decrypt_file` 两个便捷函数，
       上传落盘 / 转换前 / 下载时统一调用，对业务代码透明。
    4. 开启开关 FILE_ENCRYPTION_ENABLED（默认开启），可一键回退。
"""
import os
import base64
import tempfile
import shutil

from utils.logger import get_logger

logger = get_logger(__name__)

# 缓存的 cipher 实例（进程内复用）
_cipher = None
_cipher_enabled = None


def _get_cipher():
    """获取（并缓存）Fernet 加密实例。"""
    global _cipher
    if _cipher is not None:
        return _cipher

    from config import Config

    key = getattr(Config, 'FILE_ENCRYPTION_KEY', None)
    if not key:
        # 未配置密钥：自动生成一个并给出持久化提示（仅记录一次日志）
        key = base64.urlsafe_b64encode(os.urandom(32)).decode('ascii')
        logger.warning(
            "未配置 FILE_ENCRYPTION_KEY，已临时生成。请在 .env 中设置，"
            "否则重启后旧密文将无法解密。建议值: %s", key
        )
    try:
        from cryptography.fernet import Fernet
        _cipher = Fernet(key.encode('utf-8'))
    except Exception as e:
        logger.error("初始化文件加密失败，将使用明文模式: %s", e)
        _cipher = None
    return _cipher


def is_enabled() -> bool:
    """判断文件加密是否开启（进程内缓存结果）。"""
    global _cipher_enabled
    if _cipher_enabled is not None:
        return _cipher_enabled

    from config import Config
    try:
        enabled = bool(getattr(Config, 'FILE_ENCRYPTION_ENABLED', True))
    except Exception:
        enabled = True
    _cipher_enabled = enabled
    return _cipher_enabled


def encrypt_bytes(data: bytes) -> bytes:
    """加密字节流，返回密文字节。"""
    cipher = _get_cipher()
    if cipher is None:
        return data
    return cipher.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """解密字节流，返回明文字节。"""
    cipher = _get_cipher()
    if cipher is None:
        return data
    return cipher.decrypt(data)


def encrypt_file_in_place(filepath: str) -> bool:
    """
    就地加密一个文件（将文件内容改写为密文）。
    用于上传落盘后调用，保证磁盘上只存密文。
    """
    if not is_enabled():
        return True
    cipher = _get_cipher()
    if cipher is None:
        return True
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        enc = cipher.encrypt(data)
        with open(filepath, 'wb') as f:
            f.write(enc)
        return True
    except Exception as e:
        logger.error("就地加密文件失败 %s: %s", filepath, e)
        return False


def decrypt_to_file(src_path: str, dst_path: str = None) -> str:
    """
    解密一个文件到临时明文文件，返回明文临时路径。
    调用方负责在使用后删除返回的临时文件。
    """
    if not is_enabled():
        return src_path
    cipher = _get_cipher()
    if cipher is None:
        return src_path
    if dst_path is None:
        # 生成与源文件同后缀的临时明文文件
        ext = os.path.splitext(src_path)[1]
        fd, tmp = tempfile.mkstemp(suffix=ext or '.tmp')
        os.close(fd)
        dst_path = tmp
    with open(src_path, 'rb') as f:
        data = f.read()
    dec = cipher.decrypt(data)
    with open(dst_path, 'wb') as f:
        f.write(dec)
    return dst_path


def decrypt_in_memory(filepath: str) -> bytes:
    """解密文件内容并返回明文字节（不落盘，用于下载场景）。"""
    if not is_enabled():
        with open(filepath, 'rb') as f:
            return f.read()
    cipher = _get_cipher()
    if cipher is None:
        with open(filepath, 'rb') as f:
            return f.read()
    with open(filepath, 'rb') as f:
        data = f.read()
    return cipher.decrypt(data)


def safe_delete(path: str):
    """安全删除文件（忽略错误）。"""
    if not path:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
