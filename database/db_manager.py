import hashlib
import hmac
import os
import re
import threading
import uuid
import subprocess
import ipaddress
from datetime import datetime, timedelta

import mysql.connector
from mysql.connector import Error, pooling
from werkzeug.security import generate_password_hash, check_password_hash

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """数据库管理器"""

    _cnx_pool = None
    _pool_lock = threading.Lock()

    @classmethod
    def _get_pool(cls):
        """懒加载获取连接池"""
        if cls._cnx_pool is None:
            with cls._pool_lock:
                if cls._cnx_pool is None:
                    try:
                        cls._cnx_pool = pooling.MySQLConnectionPool(
                            pool_name='fileconverter_pool',
                            pool_size=Config.DB_POOL_SIZE,
                            **Config.DB_CONFIG
                        )
                    except Error as e:
                        logger.error("创建连接池失败: %s", e)
                        return None
        return cls._cnx_pool

    @classmethod
    def check_mysql_service(cls):
        """检查 MySQL 服务是否运行"""
        try:
            if os.name == 'nt':
                result = subprocess.run(
                    ['sc', 'query', 'mysql'], capture_output=True, text=True
                )
                if result.returncode == 0 and 'RUNNING' in result.stdout:
                    return True
                return False
            else:
                try:
                    result = subprocess.run(
                        ['systemctl', 'is-active', '--quiet', 'mysql'],
                        capture_output=True, timeout=5
                    )
                    if result.returncode == 0:
                        return True
                except FileNotFoundError:
                    pass
                try:
                    env = os.environ.copy()
                    env['MYSQL_PWD'] = Config.DB_CONFIG.get("password", "")
                    result = subprocess.run(
                        ['mysqladmin', 'ping', '-u', Config.DB_CONFIG.get('user', 'root'),
                         '--silent'],
                        capture_output=True, timeout=5, text=True, env=env
                    )
                    if result.returncode == 0 or 'mysqld is alive' in result.stdout:
                        return True
                except FileNotFoundError:
                    pass
                return False
        except Exception as e:
            logger.error("检查MySQL服务状态错误: %s", e)
            return False

    @classmethod
    def get_connection(cls):
        """从连接池获取可用连接"""
        try:
            pool = cls._get_pool()
            if pool:
                return pool.get_connection()
            return cls.create_connection()
        except Error as e:
            logger.error("获取数据库连接错误: %s", e)
            try:
                return cls.create_connection()
            except Exception:
                return None

    @classmethod
    def return_connection(cls, conn):
        """将连接返回到连接池"""
        try:
            if conn:
                try:
                    if conn.is_connected():
                        conn.close()
                    else:
                        try:
                            conn.close()
                        except Exception:
                            pass
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.error("返回数据库连接错误: %s", e)

    @staticmethod
    def create_connection():
        """创建数据库连接"""
        try:
            conn = mysql.connector.connect(**Config.DB_CONFIG)
            return conn
        except Error as e:
            logger.error("数据库连接错误: %s", e)
            return None

    @classmethod
    def shutdown_pool(cls):
        """关闭连接池（释放所有池内连接）"""
        if cls._cnx_pool:
            try:
                # 尝试逐一关闭池中所有活跃连接
                if hasattr(cls._cnx_pool, '_cnx_queue'):
                    while not cls._cnx_pool._cnx_queue.empty():
                        try:
                            conn = cls._cnx_pool._cnx_queue.get_nowait()
                            conn.close()
                        except Exception:
                            pass
                cls._cnx_pool = None
            except Exception:
                pass

    # ========================
    # 密码处理（werkzeug + 旧格式兼容）
    # ========================

    @staticmethod
    def _hash_password(password: str) -> str:
        """使用 werkzeug 哈希密码（pbkdf2:sha256:…）"""
        return generate_password_hash(password)

    @staticmethod
    def _check_password(password: str, stored_hash: str, salt: str = '') -> bool:
        """
        验证密码，兼容新旧格式。

        1. 先尝试 werkzeug 格式（pbkdf2:… / scrypt:…）
        2. 如果是 64 位 hex 旧格式，用 SHA-256(password + salt) 验证

        Returns:
            (is_valid: bool, needs_upgrade: bool)
        """
        if stored_hash is None:
            return False, False

        # werkzeug 格式
        if stored_hash.startswith('pbkdf2:') or stored_hash.startswith('scrypt:'):
            return check_password_hash(stored_hash, password), False

        # 旧格式：64 位 hex (SHA-256)
        if len(stored_hash) == 64:
            try:
                int(stored_hash, 16)
                old_hash = hashlib.sha256((password + (salt or '')).encode()).hexdigest()
                if hmac.compare_digest(old_hash, stored_hash):
                    return True, True  # 需要升级
            except ValueError:
                pass

        return False, False

    @staticmethod
    def _upgrade_password_if_needed(user_id, password):
        """登录成功后，如果密码是旧格式则自动升级为 werkzeug 格式"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                new_hash = DatabaseManager._hash_password(password)
                cursor.execute(
                    "UPDATE users SET password = %s, salt = %s WHERE id = %s",
                    (new_hash, '', user_id)
                )
                conn.commit()
                cursor.close()
        except Error as e:
            logger.error("密码升级失败: %s", e)
            if conn:
                conn.rollback()
        finally:
            if conn:
                DatabaseManager.return_connection(conn)

    # ========================
    # 数据库初始化
    # ========================

    @staticmethod
    def initialize_database():
        """初始化数据库和表"""
        conn = None
        try:
            conn = DatabaseManager.create_connection()
            if conn:
                cursor = conn.cursor()
                DB = Config.DB_CONFIG.get('database')
                if not re.match(r'^[a-zA-Z0-9_]+$', str(DB)):
                    logger.error("非法的数据库名: %s", DB)
                    return
                cursor.execute("SHOW DATABASES LIKE %s", (DB,))
                database_exists = cursor.fetchone()

                if not database_exists:
                    cursor.execute(f"CREATE DATABASE `{DB}`")

                cursor.execute(f"USE `{DB}`")

                # --- 用户表 ---
                cursor.execute("SHOW TABLES LIKE 'users'")
                table_exists = cursor.fetchone()
                if not table_exists:
                    cursor.execute("""
                        CREATE TABLE users (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            username        VARCHAR(50) UNIQUE NOT NULL,
                            email           VARCHAR(255) UNIQUE NOT NULL,
                            password        VARCHAR(255) NOT NULL,
                            salt            VARCHAR(255) NOT NULL,
                            is_admin        BOOLEAN DEFAULT FALSE,
                            is_block        BOOLEAN DEFAULT FALSE,
                            expiration_date DATETIME,
                            remaining_times INT DEFAULT 20,
                            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_username (username),
                            INDEX idx_email (email)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)

                # --- 日志表 ---
                cursor.execute("SHOW TABLES LIKE 'conversion_logs'")
                log_table_exists = cursor.fetchone()
                if not log_table_exists:
                    cursor.execute("""
                        CREATE TABLE conversion_logs (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            username        VARCHAR(50) NOT NULL,
                            mode            VARCHAR(100) NOT NULL,
                            filename        TEXT,
                            success         BOOLEAN NOT NULL,
                            message         TEXT,
                            operation_time  DATETIME DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_username (username),
                            INDEX idx_operation_time (operation_time),
                            INDEX idx_user_time (username, operation_time)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                else:
                    for stmt in [
                        "ALTER TABLE conversion_logs ADD INDEX idx_user_time (username, operation_time)",
                        "ALTER TABLE conversion_logs ADD COLUMN output_path VARCHAR(500) DEFAULT '' AFTER message"
                    ]:
                        try:
                            cursor.execute(stmt)
                        except Error:
                            pass

                # --- 公告表 ---
                cursor.execute("SHOW TABLES LIKE 'announcements'")
                announce_table_exists = cursor.fetchone()
                if not announce_table_exists:
                    cursor.execute("""
                        CREATE TABLE announcements (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            title           VARCHAR(200) NOT NULL,
                            content         TEXT NOT NULL,
                            type            VARCHAR(20) DEFAULT 'info',
                            is_active       BOOLEAN DEFAULT TRUE,
                            priority        INT DEFAULT 0,
                            created_by      VARCHAR(50),
                            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_active (is_active),
                            INDEX idx_active_priority (is_active, priority)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)

                # --- IP访问记录表 ---
                cursor.execute("SHOW TABLES LIKE 'ip_access_logs'")
                ip_log_table_exists = cursor.fetchone()
                if not ip_log_table_exists:
                    cursor.execute("""
                        CREATE TABLE ip_access_logs (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            ip_address      VARCHAR(45) NOT NULL,
                            request_url     VARCHAR(500),
                            request_method  VARCHAR(10),
                            user_agent      TEXT,
                            referer         VARCHAR(500),
                            access_time     DATETIME DEFAULT CURRENT_TIMESTAMP,
                            status_code     INT,
                            response_time   FLOAT,
                            country         VARCHAR(100),
                            city            VARCHAR(100),
                            latitude        DECIMAL(10, 6),
                            longitude       DECIMAL(10, 6),
                            INDEX idx_ip (ip_address),
                            INDEX idx_access_time (access_time),
                            INDEX idx_ip_time (ip_address, access_time),
                            INDEX idx_access_time_loc (access_time, latitude, longitude)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                else:
                    for col, col_type in [
                        ('country', 'VARCHAR(100)'),
                        ('city', 'VARCHAR(100)'),
                        ('latitude', 'DECIMAL(10, 6)'),
                        ('longitude', 'DECIMAL(10, 6)')
                    ]:
                        cursor.execute(f"SHOW COLUMNS FROM ip_access_logs LIKE '{col}'")
                        if not cursor.fetchone():
                            try:
                                cursor.execute(f"ALTER TABLE ip_access_logs ADD COLUMN {col} {col_type}")
                            except Error:
                                pass
                    for stmt in [
                        "ALTER TABLE ip_access_logs ADD INDEX idx_ip_time (ip_address, access_time)",
                        "ALTER TABLE ip_access_logs ADD INDEX idx_access_time_loc (access_time, latitude, longitude)"
                    ]:
                        try:
                            cursor.execute(stmt)
                        except Error:
                            pass

                # --- IP黑名单表 ---
                cursor.execute("SHOW TABLES LIKE 'ip_blacklist'")
                ip_blacklist_exists = cursor.fetchone()
                if not ip_blacklist_exists:
                    cursor.execute("""
                        CREATE TABLE ip_blacklist (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            ip_address      VARCHAR(45) UNIQUE NOT NULL,
                            reason          TEXT,
                            blocked_by      VARCHAR(50),
                            blocked_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                            expires_at      DATETIME,
                            is_active       BOOLEAN DEFAULT TRUE,
                            INDEX idx_ip (ip_address),
                            INDEX idx_active (is_active),
                            INDEX idx_active_expires (is_active, expires_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                else:
                    for stmt in [
                        "ALTER TABLE ip_blacklist ADD INDEX idx_active_expires (is_active, expires_at)"
                    ]:
                        try:
                            cursor.execute(stmt)
                        except Error:
                            pass

                # --- 联系消息表 ---
                cursor.execute("SHOW TABLES LIKE 'contact_messages'")
                contact_table_exists = cursor.fetchone()
                if not contact_table_exists:
                    cursor.execute("""
                        CREATE TABLE contact_messages (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            username        VARCHAR(50),
                            name            VARCHAR(100) NOT NULL DEFAULT '',
                            email           VARCHAR(255) NOT NULL DEFAULT '',
                            subject         VARCHAR(200) NOT NULL,
                            message         TEXT NOT NULL,
                            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                            is_read         BOOLEAN DEFAULT FALSE,
                            reply           TEXT,
                            replied_at      DATETIME,
                            INDEX idx_read (is_read),
                            INDEX idx_created (created_at),
                            INDEX idx_username (username),
                            INDEX idx_username_created (username, created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)

                # --- 回复记录表（支持多次双向回复） ---
                cursor.execute("SHOW TABLES LIKE 'contact_replies'")
                if not cursor.fetchone():
                    cursor.execute("""
                        CREATE TABLE contact_replies (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            message_id      INT NOT NULL,
                            author_type     ENUM('user', 'admin') NOT NULL,
                            content         TEXT NOT NULL,
                            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_message_id (message_id),
                            INDEX idx_created_at (created_at),
                            FOREIGN KEY (message_id) REFERENCES contact_messages(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                else:
                    cursor.execute("SHOW COLUMNS FROM contact_messages LIKE 'username'")
                    if not cursor.fetchone():
                        try:
                            cursor.execute("ALTER TABLE contact_messages ADD COLUMN username VARCHAR(50)")
                        except Error:
                            pass
                    for stmt in [
                        "ALTER TABLE contact_messages ADD INDEX idx_username (username)",
                        "ALTER TABLE contact_messages ADD INDEX idx_username_created (username, created_at)"
                    ]:
                        try:
                            cursor.execute(stmt)
                        except Error:
                            pass

                # --- 登录失败记录表（用于限流） ---
                cursor.execute("SHOW TABLES LIKE 'login_attempts'")
                login_attempts_exists = cursor.fetchone()
                if not login_attempts_exists:
                    cursor.execute("""
                        CREATE TABLE login_attempts (
                            id              INT AUTO_INCREMENT PRIMARY KEY,
                            identifier      VARCHAR(100) NOT NULL,
                            ip_address      VARCHAR(45),
                            success         BOOLEAN DEFAULT FALSE,
                            attempt_time    DATETIME DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_identifier (identifier),
                            INDEX idx_ip (ip_address),
                            INDEX idx_ident_time (identifier, attempt_time),
                            INDEX idx_ip_time (ip_address, attempt_time)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)

                # 创建默认管理员
                ADMIN_NAME = Config.ADMIN_USERNAME
                ADMIN_PASSWORD = Config.ADMIN_PASSWORD
                ADMIN_EMAIL = Config.ADMIN_EMAIL

                # 安全检查：管理员密码必须通过环境变量设置
                if not ADMIN_PASSWORD:
                    logger.warning("=" * 60)
                    logger.warning("未设置 ADMIN_PASSWORD 环境变量！")
                    logger.warning("管理员账号将不会被创建/更新。")
                    logger.warning("请在 .env 中设置 ADMIN_PASSWORD=<强密码>")
                    logger.warning("=" * 60)

                cursor.execute("SELECT * FROM users WHERE username = %s", (ADMIN_NAME,))
                admin_exists = cursor.fetchone()

                if not admin_exists and ADMIN_PASSWORD:
                    # 使用 werkzeug 哈希（salt 字段保留为空字符串）
                    password = DatabaseManager._hash_password(ADMIN_PASSWORD)
                    cursor.execute(
                        """INSERT INTO users
                        (username, email, password, salt, is_admin, is_block, expiration_date, remaining_times)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (ADMIN_NAME, ADMIN_EMAIL, password, '',
                         True, False,
                         os.getenv('ADMIN_EXPIRATION', '2099-12-31 23:59:59'),
                         int(os.getenv('ADMIN_REMAINING_TIMES', 9999)))
                    )
                elif admin_exists and ADMIN_PASSWORD:
                    # 如果管理员已存在，检查是否需要升级密码哈希
                    stored_hash = admin_exists[2]  # password 列
                    stored_salt = admin_exists[3]   # salt 列
                    _, needs_upgrade = DatabaseManager._check_password(ADMIN_PASSWORD, stored_hash, stored_salt)
                    if needs_upgrade:
                        # 升级管理员密码哈希
                        new_hash = DatabaseManager._hash_password(ADMIN_PASSWORD)
                        cursor.execute(
                            "UPDATE users SET password = %s, salt = %s WHERE username = %s",
                            (new_hash, '', ADMIN_NAME)
                        )
                        logger.info("管理员密码哈希已自动升级为 werkzeug 格式")

                conn.commit()
                cursor.close()
                conn.close()

                # 预热连接池
                DatabaseManager._get_pool()

        except Error as e:
            logger.error("数据库初始化错误: %s", e)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ========================
    # 用户管理
    # ========================

    @staticmethod
    def register_user(username, email, password, is_admin=False,
                      is_block=False, expiration_days=30):
        """注册新用户（使用 werkzeug 密码哈希）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM users WHERE username = %s",
                    (username,)
                )
                if cursor.fetchone():
                    return False, "用户名已存在"

                if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    return False, "邮箱格式不正确"

                cursor.execute(
                    "SELECT * FROM users WHERE email = %s",
                    (email,)
                )
                if cursor.fetchone():
                    return False, "邮箱已存在"

                # 使用 werkzeug 哈希
                password_hash = DatabaseManager._hash_password(password)
                expiration_date = datetime.now() + timedelta(days=expiration_days)

                cursor.execute(
                    """INSERT INTO users
                    (username, email, password, salt, is_admin, is_block,
                     expiration_date, remaining_times)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (username, email, password_hash, '', is_admin,
                     is_block, expiration_date, 20)
                )

                conn.commit()
                cursor.close()
                return True, "注册成功"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"注册失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "注册失败"

    @staticmethod
    def authenticate_user(username_or_email, password, login_type='times'):
        """
        验证用户登录。
        兼容旧 SHA-256 密码格式，登录成功后自动升级哈希。
        """
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    """SELECT id, username, email, password, salt, is_admin,
                             is_block, expiration_date, remaining_times
                    FROM users
                    WHERE username = %s OR email = %s""",
                    (username_or_email, username_or_email)
                )
                user = cursor.fetchone()

                if not user:
                    return False, None, "用户名或邮箱不存在"

                # 验证密码（兼容新旧格式）
                is_valid, needs_upgrade = DatabaseManager._check_password(
                    password, user['password'], user.get('salt', '')
                )

                if not is_valid:
                    return False, None, "密码错误"

                # 自动升级旧格式密码
                if needs_upgrade:
                    DatabaseManager._upgrade_password_if_needed(user['id'], password)

                if user['is_block']:
                    return False, None, "账户被封禁，请联系管理员"

                if login_type == 'time':
                    if datetime.now() > user['expiration_date']:
                        return False, None, "账户已过期，请联系管理员续期"
                elif login_type == 'times':
                    if user['remaining_times'] <= 0:
                        return False, None, "剩余次数不足，请联系管理员充值"

                cursor.close()
                return True, user, "登录成功"
        except Error as e:
            return False, None, f"登录失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, None, "登录失败"

    @staticmethod
    def reset_password(email, new_password):
        """通过邮箱重置密码（使用 werkzeug 哈希）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
                if not user:
                    return False, "该邮箱未注册"

                password_hash = DatabaseManager._hash_password(new_password)
                cursor.execute(
                    "UPDATE users SET password = %s, salt = %s WHERE email = %s",
                    (password_hash, '', email)
                )
                conn.commit()
                cursor.close()
                return True, "密码重置成功"
        except Error as e:
            return False, f"重置失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "重置失败"

    @staticmethod
    def get_user_by_username(username):
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT id, username, email, is_admin, is_block,
                             expiration_date, remaining_times
                    FROM users WHERE username = %s""",
                    (username,)
                )
                user = cursor.fetchone()
                cursor.close()
                return user
        except Error as e:
            logger.error("获取用户信息错误: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return None

    @staticmethod
    def update_user_expiration(username, days_to_add):
        """更新用户过期时间"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE users
                       SET expiration_date = COALESCE(expiration_date, NOW()) + INTERVAL %s DAY
                       WHERE username = %s""",
                    (days_to_add, username)
                )
                conn.commit()
                affected = cursor.rowcount
                cursor.close()
                if affected == 0:
                    return False, "用户不存在"
                return True, f"成功更新用户 {username} 的过期时间"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"更新失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "更新失败"

    @staticmethod
    def block_user(username):
        """锁定/解锁用户"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET is_block = NOT is_block WHERE username = %s",
                    (username,)
                )
                conn.commit()
                affected = cursor.rowcount
                if affected == 0:
                    cursor.close()
                    return False, "用户不存在"
                cursor.execute(
                    "SELECT is_block FROM users WHERE username = %s",
                    (username,)
                )
                result = cursor.fetchone()
                status = '锁定' if result[0] == 1 else '解锁'
                cursor.close()
                return True, f"成功{status}用户 {username}"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"更新失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "更新失败"

    @staticmethod
    def get_all_users():
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT id, email, username, is_admin, is_block,
                             expiration_date, remaining_times
                    FROM users ORDER BY is_admin DESC, username"""
                )
                users = cursor.fetchall()
                cursor.close()
                return True, users
        except Error as e:
            return False, f"获取失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "获取失败"

    @staticmethod
    def increase_user_times(username, times_to_add):
        """增加用户剩余次数"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE users
                       SET remaining_times = COALESCE(remaining_times, 0) + %s
                       WHERE username = %s""",
                    (times_to_add, username)
                )
                conn.commit()
                affected = cursor.rowcount
                if affected > 0:
                    cursor.execute(
                        "SELECT remaining_times FROM users WHERE username = %s",
                        (username,)
                    )
                    new_times = cursor.fetchone()[0]
                    cursor.close()
                    return True, f"成功为用户 {username} 增加 {times_to_add} 次，当前剩余 {new_times} 次"
                cursor.close()
                return False, "用户不存在"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"增加次数失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "增加次数失败"

    @staticmethod
    def decrease_user_times(username, times_to_decrease=1):
        """减少用户剩余次数"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE users
                       SET remaining_times = GREATEST(COALESCE(remaining_times, 0) - %s, 0)
                       WHERE username = %s""",
                    (times_to_decrease, username)
                )
                conn.commit()
                affected = cursor.rowcount
                if affected > 0:
                    cursor.execute(
                        "SELECT remaining_times FROM users WHERE username = %s",
                        (username,)
                    )
                    new_times = cursor.fetchone()[0]
                    cursor.close()
                    return True, f"成功减少用户 {username} {times_to_decrease} 次，当前剩余 {new_times} 次"
                cursor.close()
                return False, "用户不存在"
        except Error as e:
            if conn:
                conn.rollback()
            logger.error("减少次数数据库错误: %s", e)
            return False, f"减少次数失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "减少次数失败"

    # ========================
    # 登录失败记录（限流用）
    # ========================

    @staticmethod
    def log_login_attempt(identifier, ip_address, success):
        """记录登录尝试"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO login_attempts (identifier, ip_address, success)
                    VALUES (%s, %s, %s)""",
                    (identifier, ip_address, success)
                )
                conn.commit()
                cursor.close()
                return True
        except Error as e:
            logger.error("记录登录尝试失败: %s", e)
            if conn:
                conn.rollback()
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False

    @staticmethod
    def get_login_failures(identifier, ip_address, window_seconds=300):
        """获取窗口期内的登录失败次数"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                since = datetime.now() - timedelta(seconds=window_seconds)
                cursor.execute(
                    """SELECT COUNT(*) FROM login_attempts
                    WHERE success = FALSE AND attempt_time >= %s
                    AND (identifier = %s OR ip_address = %s)""",
                    (since, identifier, ip_address)
                )
                count = cursor.fetchone()[0]
                cursor.close()
                return count
        except Error as e:
            logger.error("查询登录失败次数错误: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return 0

    # ========================
    # 日志
    # ========================

    @staticmethod
    def log_conversion(username, mode, filename, success, message="", output_path=""):
        """记录转换操作日志"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO conversion_logs
                    (username, mode, filename, success, message, output_path)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (username, mode, filename, success, message, output_path)
                )
                conn.commit()
                cursor.close()
                return True
        except Error as e:
            logger.error("记录日志错误: %s", e)
            if conn:
                conn.rollback()
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False

    @staticmethod
    def get_conversion_logs(username=None, limit=100, offset=0):
        """获取转换日志"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                if username:
                    cursor.execute(
                        """SELECT id, username, mode, filename, success, message, output_path, operation_time
                        FROM conversion_logs
                        WHERE username = %s
                        ORDER BY operation_time DESC
                        LIMIT %s OFFSET %s""",
                        (username, limit, offset)
                    )
                else:
                    cursor.execute(
                        """SELECT id, username, mode, filename, success, message, operation_time
                        FROM conversion_logs
                        ORDER BY operation_time DESC
                        LIMIT %s OFFSET %s""",
                        (limit, offset)
                    )
                logs = cursor.fetchall()
                cursor.close()
                return True, logs
        except Error as e:
            return False, f"获取日志失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    @staticmethod
    def get_log_count(username=None):
        """获取日志总数"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                if username:
                    cursor.execute(
                        "SELECT COUNT(*) FROM conversion_logs WHERE username = %s",
                        (username,)
                    )
                else:
                    cursor.execute("SELECT COUNT(*) FROM conversion_logs")
                count = cursor.fetchone()[0]
                cursor.close()
                return True, count
        except Error as e:
            return False, 0
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, 0

    @staticmethod
    def get_user_logs(username, limit=50, offset=0):
        """获取当前用户的转换记录（含输出文件路径）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT id, mode, filename, success, message, output_path, operation_time
                    FROM conversion_logs
                    WHERE username = %s
                    ORDER BY operation_time DESC
                    LIMIT %s OFFSET %s""",
                    (username, limit, offset)
                )
                logs = cursor.fetchall()
                for log in logs:
                    if log.get('operation_time'):
                        log['operation_time'] = str(log['operation_time'])
                    # 检查输出文件是否存在
                    if log.get('output_path'):
                        log['file_exists'] = os.path.exists(log['output_path'])
                    else:
                        log['file_exists'] = False
                cursor.execute(
                    """SELECT COUNT(*) as cnt FROM conversion_logs WHERE username = %s""",
                    (username,)
                )
                total = cursor.fetchone()['cnt']
                cursor.close()
                return True, logs, total
        except Error as e:
            return False, [], 0
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, [], 0

    # ========================
    # 公告
    # ========================

    @staticmethod
    def create_announcement(title, content, announce_type='info', priority=0, created_by='admin'):
        """创建公告"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO announcements
                    (title, content, type, priority, created_by)
                    VALUES (%s, %s, %s, %s, %s)""",
                    (title, content, announce_type, priority, created_by)
                )
                conn.commit()
                cursor.close()
                return True, "公告发布成功"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"发布失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "发布失败"

    @staticmethod
    def get_active_announcements(limit=10):
        """获取活跃公告"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT id, title, content, type, priority, created_by, created_at
                    FROM announcements
                    WHERE is_active = TRUE
                    ORDER BY priority DESC, created_at DESC
                    LIMIT %s""",
                    (limit,)
                )
                announcements = cursor.fetchall()
                for ann in announcements:
                    if ann.get('created_at'):
                        ann['created_at'] = str(ann['created_at'])
                cursor.close()
                return True, announcements
        except Error as e:
            return False, f"获取公告失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    @staticmethod
    def get_all_announcements():
        """获取所有公告"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT id, title, content, type, is_active, priority, created_by, created_at, updated_at
                    FROM announcements
                    ORDER BY priority DESC, created_at DESC"""
                )
                announcements = cursor.fetchall()
                for ann in announcements:
                    if ann.get('created_at'):
                        ann['created_at'] = str(ann['created_at'])
                    if ann.get('updated_at'):
                        ann['updated_at'] = str(ann['updated_at'])
                cursor.close()
                return True, announcements
        except Error as e:
            return False, f"获取公告失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    @staticmethod
    def toggle_announcement(announce_id):
        """切换公告激活状态"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE announcements SET is_active = NOT is_active WHERE id = %s",
                    (announce_id,)
                )
                conn.commit()
                affected = cursor.rowcount
                if affected == 0:
                    cursor.close()
                    return False, "公告不存在"
                cursor.execute(
                    "SELECT is_active FROM announcements WHERE id = %s",
                    (announce_id,)
                )
                result = cursor.fetchone()
                status = '激活' if result[0] == 1 else '停用'
                cursor.close()
                return True, f"已{status}公告"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"操作失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "操作失败"

    @staticmethod
    def delete_announcement(announce_id):
        """删除公告"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM announcements WHERE id = %s",
                    (announce_id,)
                )
                conn.commit()
                cursor.close()
                return True, "公告已删除"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"删除失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "删除失败"

    # ========================
    # IP 访问记录和黑名单
    # ========================

    @staticmethod
    def log_ip_access(ip_address, request_url='', request_method='GET',
                     user_agent='', referer='', status_code=200, response_time=0):
        """记录IP访问日志"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO ip_access_logs
                    (ip_address, request_url, request_method, user_agent, referer, status_code, response_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (ip_address, request_url, request_method, user_agent, referer, status_code, response_time)
                )
                conn.commit()
                cursor.close()
                return True
        except Error as e:
            logger.error("记录IP访问日志错误: %s", e)
            if conn:
                conn.rollback()
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False

    _ip_blocked_cache = {}
    _ip_blocked_cache_time = 0
    _ip_blocked_cache_lock = threading.Lock()

    @staticmethod
    def is_ip_blocked(ip_address):
        """检查IP是否在黑名单中（带缓存）"""
        now = datetime.now().timestamp()
        with DatabaseManager._ip_blocked_cache_lock:
            if now - DatabaseManager._ip_blocked_cache_time < Config.IP_BLOCKED_CACHE_TIME:
                cached = DatabaseManager._ip_blocked_cache.get(ip_address)
                if cached is not None:
                    return cached
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT * FROM ip_blacklist
                    WHERE ip_address = %s AND is_active = TRUE
                    AND (expires_at IS NULL OR expires_at > NOW())""",
                    (ip_address,)
                )
                result = cursor.fetchone()
                cursor.close()
                is_blocked = result is not None
                with DatabaseManager._ip_blocked_cache_lock:
                    # 如果缓存已过期，先清空旧条目再写入新数据
                    if now - DatabaseManager._ip_blocked_cache_time >= Config.IP_BLOCKED_CACHE_TIME:
                        DatabaseManager._ip_blocked_cache.clear()
                        DatabaseManager._ip_blocked_cache_time = now
                    DatabaseManager._ip_blocked_cache[ip_address] = (is_blocked, result)
                return is_blocked, result
        except Error as e:
            logger.error("检查IP黑名单错误: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, None

    @staticmethod
    def block_ip(ip_address, reason='', blocked_by='admin', expire_days=None):
        """封禁IP"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                expires_at = None
                if expire_days:
                    expires_at = datetime.now() + timedelta(days=expire_days)

                cursor.execute(
                    """INSERT INTO ip_blacklist (ip_address, reason, blocked_by, expires_at, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON DUPLICATE KEY UPDATE
                        reason = VALUES(reason),
                        blocked_by = VALUES(blocked_by),
                        blocked_at = NOW(),
                        expires_at = VALUES(expires_at),
                        is_active = TRUE""",
                    (ip_address, reason, blocked_by, expires_at)
                )
                conn.commit()
                cursor.close()
                with DatabaseManager._ip_blocked_cache_lock:
                    DatabaseManager._ip_blocked_cache.pop(ip_address, None)
                return True, f"IP {ip_address} 已被封禁"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"封禁失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "封禁失败"

    @staticmethod
    def unblock_ip(ip_address):
        """解封IP"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE ip_blacklist SET is_active = FALSE WHERE ip_address = %s",
                    (ip_address,)
                )
                conn.commit()
                cursor.close()
                with DatabaseManager._ip_blocked_cache_lock:
                    DatabaseManager._ip_blocked_cache.pop(ip_address, None)
                return True, f"IP {ip_address} 已解封"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"解封失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "解封失败"

    @staticmethod
    def get_ip_statistics(hours=24):
        """获取IP访问统计"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    """SELECT COUNT(*) as total_requests,
                             COUNT(DISTINCT ip_address) as unique_ips
                    FROM ip_access_logs
                    WHERE access_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)""",
                    (hours,)
                )
                stats = cursor.fetchone()

                cursor.execute(
                    """SELECT ip_address, COUNT(*) as visit_count,
                             MAX(access_time) as last_visit,
                             MIN(access_time) as first_visit
                    FROM ip_access_logs
                    WHERE access_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    GROUP BY ip_address
                    ORDER BY visit_count DESC
                    LIMIT 50""",
                    (hours,)
                )
                top_ips = cursor.fetchall()

                for ip in top_ips:
                    if ip.get('last_visit'):
                        ip['last_visit'] = str(ip['last_visit'])
                    if ip.get('first_visit'):
                        ip['first_visit'] = str(ip['first_visit'])

                cursor.execute(
                    """SELECT ip_address, reason, blocked_by, blocked_at, expires_at, is_active
                    FROM ip_blacklist
                    ORDER BY blocked_at DESC"""
                )
                blocked_ips = cursor.fetchall()

                for ip in blocked_ips:
                    if ip.get('blocked_at'):
                        ip['blocked_at'] = str(ip['blocked_at'])
                    if ip.get('expires_at'):
                        ip['expires_at'] = str(ip['expires_at'])

                cursor.close()

                return True, {
                    'stats': stats,
                    'top_ips': top_ips,
                    'blocked_ips': blocked_ips
                }
        except Error as e:
            return False, f"获取统计信息失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, {}

    @staticmethod
    def get_ip_access_timeline(hours=24, limit=100):
        """获取IP访问时间线"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    """SELECT DATE_FORMAT(access_time, '%Y-%m-%d %H:00:00') as time_slot,
                             COUNT(*) as request_count,
                             COUNT(DISTINCT ip_address) as unique_ips
                    FROM ip_access_logs
                    WHERE access_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    GROUP BY time_slot
                    ORDER BY time_slot ASC""",
                    (hours,)
                )
                timeline = cursor.fetchall()

                cursor.close()
                return True, timeline
        except Error as e:
            return False, f"获取时间线数据失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    @staticmethod
    def get_ip_location(ip_address):
        """获取IP地理位置"""
        try:
            import requests
            try:
                ip_obj = ipaddress.ip_address(ip_address)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                    return {
                        'country': '内网',
                        'city': '本地网络',
                        'latitude': float(os.getenv('DEFAULT_LATITUDE', 39.9042)),
                        'longitude': float(os.getenv('DEFAULT_LONGITUDE', 116.4074))
                    }
            except ValueError:
                pass

            response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=Config.IP_LOCATION_API_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                if data.get('error'):
                    return None

                return {
                    'country': data.get('country_name', '未知'),
                    'city': data.get('city', '未知'),
                    'latitude': float(data.get('latitude', 0)),
                    'longitude': float(data.get('longitude', 0))
                }
            return None
        except Exception as e:
            logger.error("获取IP位置失败 %s: %s", ip_address, e)
            return None

    @staticmethod
    def update_ip_location(ip_address, country, city, latitude, longitude):
        """更新IP地理位置"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE ip_access_logs
                    SET country = %s, city = %s, latitude = %s, longitude = %s
                    WHERE ip_address = %s AND (country IS NULL OR country = '')""",
                    (country, city, latitude, longitude, ip_address)
                )
                conn.commit()
                cursor.close()
                return True
        except Error as e:
            if conn:
                conn.rollback()
            logger.error("更新IP位置失败: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False

    @staticmethod
    def get_ip_map_data(hours=24):
        """获取地图数据"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    """SELECT ip_address, country, city, latitude, longitude,
                             COUNT(*) as visit_count,
                             MAX(access_time) as last_visit
                    FROM ip_access_logs
                    WHERE access_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                      AND latitude IS NOT NULL AND longitude IS NOT NULL
                    GROUP BY ip_address, country, city, latitude, longitude
                    ORDER BY visit_count DESC""",
                    (hours,)
                )
                ip_locations = cursor.fetchall()

                for ip in ip_locations:
                    if ip.get('last_visit'):
                        ip['last_visit'] = str(ip['last_visit'])
                    if ip.get('latitude'):
                        ip['latitude'] = float(ip['latitude'])
                    if ip.get('longitude'):
                        ip['longitude'] = float(ip['longitude'])

                cursor.close()
                return True, ip_locations
        except Error as e:
            return False, f"获取地图数据失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    # ========================
    # 联系消息管理
    # ========================

    @staticmethod
    def submit_contact_message(subject, message, username=None, name='', email=''):
        """提交联系消息"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO contact_messages (username, name, email, subject, message)
                    VALUES (%s, %s, %s, %s, %s)""",
                    (username, name, email, subject, message)
                )
                conn.commit()
                cursor.close()
                return True, "消息发送成功，感谢您的反馈！"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"发送失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "发送失败"

    @staticmethod
    def get_messages_by_username(username, page=1, per_page=20):
        """获取用户消息列表（含回复记录）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                offset = (page - 1) * per_page
                cursor.execute(
                    """SELECT * FROM contact_messages
                    WHERE username = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                    (username, per_page, offset)
                )
                messages = cursor.fetchall()
                if messages:
                    # 批量加载所有回复
                    msg_ids = [m['id'] for m in messages]
                    placeholders = ','.join(['%s'] * len(msg_ids))
                    cursor.execute(
                        f"""SELECT id, message_id, author_type, content, created_at
                        FROM contact_replies
                        WHERE message_id IN ({placeholders})
                        ORDER BY created_at ASC""",
                        tuple(msg_ids)
                    )
                    all_replies = cursor.fetchall()
                    for r in all_replies:
                        if r.get('created_at'):
                            r['created_at'] = str(r['created_at'])
                    # 按 message_id 分组
                    replies_map = {}
                    for r in all_replies:
                        replies_map.setdefault(r['message_id'], []).append(r)
                    for m in messages:
                        if m.get('created_at'):
                            m['created_at'] = str(m['created_at'])
                        if m.get('replied_at'):
                            m['replied_at'] = str(m['replied_at'])
                        m['replies'] = replies_map.get(m['id'], [])
                cursor.execute(
                    "SELECT COUNT(*) as total FROM contact_messages WHERE username = %s",
                    (username,)
                )
                total = cursor.fetchone()['total']
                cursor.close()
                return True, messages, total
        except Error as e:
            return False, [], 0
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, [], 0

    @staticmethod
    def get_contact_messages(page=1, per_page=20):
        """获取联系消息列表（管理员视图，含回复记录）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                offset = (page - 1) * per_page
                cursor.execute(
                    """SELECT * FROM contact_messages
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                    (per_page, offset)
                )
                messages = cursor.fetchall()
                if messages:
                    msg_ids = [m['id'] for m in messages]
                    placeholders = ','.join(['%s'] * len(msg_ids))
                    cursor.execute(
                        f"""SELECT id, message_id, author_type, content, created_at
                        FROM contact_replies
                        WHERE message_id IN ({placeholders})
                        ORDER BY created_at ASC""",
                        tuple(msg_ids)
                    )
                    all_replies = cursor.fetchall()
                    for r in all_replies:
                        if r.get('created_at'):
                            r['created_at'] = str(r['created_at'])
                    replies_map = {}
                    for r in all_replies:
                        replies_map.setdefault(r['message_id'], []).append(r)
                    for m in messages:
                        if m.get('created_at'):
                            m['created_at'] = str(m['created_at'])
                        if m.get('replied_at'):
                            m['replied_at'] = str(m['replied_at'])
                        m['replies'] = replies_map.get(m['id'], [])
                cursor.execute("SELECT COUNT(*) as total FROM contact_messages")
                total = cursor.fetchone()['total']
                cursor.close()
                return True, messages, total
        except Error as e:
            return False, [], 0
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, [], 0

    @staticmethod
    def get_unread_contact_count():
        """获取未读消息数"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM contact_messages WHERE is_read = FALSE"
                )
                count = cursor.fetchone()[0]
                cursor.close()
                return count
        except Error as e:
            logger.error("获取未读消息数失败: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return 0

    @staticmethod
    def mark_message_read(message_id):
        """标记消息已读"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE contact_messages SET is_read = TRUE WHERE id = %s",
                    (message_id,)
                )
                conn.commit()
                cursor.close()
                return True
        except Error as e:
            if conn:
                conn.rollback()
            logger.error("标记已读失败: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False

    @staticmethod
    def reply_message(message_id, reply_text):
        """回复联系消息"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE contact_messages
                    SET reply = %s, replied_at = NOW(), is_read = TRUE
                    WHERE id = %s""",
                    (reply_text, message_id)
                )
                conn.commit()
                cursor.close()
                return True, "回复成功"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"回复失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "回复失败"

    @staticmethod
    def add_contact_reply(message_id, content, author_type):
        """添加一条回复记录（支持 user 和 admin 双向回复）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO contact_replies (message_id, author_type, content)
                    VALUES (%s, %s, %s)""",
                    (message_id, author_type, content)
                )
                # 同步更新 contact_messages：管理员回复→标记已读，用户回复→重置未读
                cursor.execute(
                    """UPDATE contact_messages
                    SET reply = %s, replied_at = NOW(),
                        is_read = %s
                    WHERE id = %s""",
                    (content, author_type == 'admin', message_id)
                )
                conn.commit()
                cursor.close()
                return True, "回复成功"
        except Error as e:
            if conn:
                conn.rollback()
            return False, f"回复失败: {e}"
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, "回复失败"

    @staticmethod
    def get_contact_replies(message_id):
        """获取某条消息的所有回复记录"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT id, author_type, content, created_at
                    FROM contact_replies
                    WHERE message_id = %s
                    ORDER BY created_at ASC""",
                    (message_id,)
                )
                replies = cursor.fetchall()
                for r in replies:
                    if r.get('created_at'):
                        r['created_at'] = str(r['created_at'])
                cursor.close()
                return True, replies
        except Error as e:
            logger.error("获取回复记录失败: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    @staticmethod
    def get_unread_reply_count(username, since_time=None):
        """获取用户未读回复数（管理员回复了但用户还没看过的）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                if since_time:
                    cursor.execute(
                        """SELECT COUNT(*) FROM contact_replies r
                        JOIN contact_messages m ON r.message_id = m.id
                        WHERE m.username = %s AND r.author_type = 'admin'
                        AND r.created_at > %s""",
                        (username, since_time)
                    )
                else:
                    cursor.execute(
                        """SELECT COUNT(*) FROM contact_replies r
                        JOIN contact_messages m ON r.message_id = m.id
                        WHERE m.username = %s AND r.author_type = 'admin'""",
                        (username,)
                    )
                count = cursor.fetchone()[0]
                cursor.close()
                return count
        except Error as e:
            logger.error("获取未读回复数失败: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return 0

    # ========================
    # 仪表盘统计
    # ========================

    @staticmethod
    def get_user_dashboard_stats(username, mode_filter=None):
        """获取用户仪表盘统计数据"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)

                # 总体统计
                if mode_filter:
                    cursor.execute(
                        """SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                            SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count
                        FROM conversion_logs
                        WHERE username = %s AND mode = %s""",
                        (username, mode_filter)
                    )
                else:
                    cursor.execute(
                        """SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                            SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count
                        FROM conversion_logs
                        WHERE username = %s""",
                        (username,)
                    )
                stats = cursor.fetchone()
                if stats is None:
                    stats = {'total': 0, 'success_count': 0, 'fail_count': 0}

                # 按模式分组统计
                if mode_filter:
                    cursor.execute(
                        """SELECT mode,
                            COUNT(*) as count,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                            SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count
                        FROM conversion_logs
                        WHERE username = %s AND mode = %s
                        GROUP BY mode
                        ORDER BY count DESC""",
                        (username, mode_filter)
                    )
                else:
                    cursor.execute(
                        """SELECT mode,
                            COUNT(*) as count,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                            SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count
                        FROM conversion_logs
                        WHERE username = %s
                        GROUP BY mode
                        ORDER BY count DESC""",
                        (username,)
                    )
                by_mode = cursor.fetchall()

                cursor.close()
                return True, stats, by_mode
        except Error as e:
            logger.error("获取用户仪表盘统计失败: %s", e)
            return False, None, []
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, None, []

    @staticmethod
    def get_conversion_trend(days=7, username=None):
        """获取转换趋势（按天统计）"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                if username:
                    cursor.execute(
                        """SELECT DATE(operation_time) as day,
                                COUNT(*) as total,
                                SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                                SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count
                        FROM conversion_logs
                        WHERE username = %s AND operation_time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                        GROUP BY DATE(operation_time)
                        ORDER BY day ASC""",
                        (username, days)
                    )
                else:
                    cursor.execute(
                        """SELECT DATE(operation_time) as day,
                                COUNT(*) as total,
                                SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                                SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count
                        FROM conversion_logs
                        WHERE operation_time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                        GROUP BY DATE(operation_time)
                        ORDER BY day ASC""",
                        (days,)
                    )
                trend = cursor.fetchall()
                for t in trend:
                    if t.get('day'):
                        t['day'] = str(t['day'])
                cursor.close()
                return True, trend
        except Error as e:
            logger.error("获取转换趋势失败: %s", e)
            return False, []
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, []

    @staticmethod
    def get_all_modes():
        """获取所有出现过的转换模式列表"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT mode FROM conversion_logs ORDER BY mode"
                )
                modes = [row[0] for row in cursor.fetchall()]
                cursor.close()
                return modes
        except Error as e:
            logger.error("获取模式列表失败: %s", e)
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return []

    @staticmethod
    def get_weekly_stats():
        """获取本周（周一到周日）转换统计"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count,
                        SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as fail_count,
                        COUNT(DISTINCT username) as active_users
                    FROM conversion_logs
                    WHERE operation_time >= DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)"""
                )
                weekly = cursor.fetchone()
                cursor.close()
                if weekly is None:
                    weekly = {'total': 0, 'success_count': 0, 'fail_count': 0, 'active_users': 0}
                return True, weekly
        except Error as e:
            logger.error("获取本周统计失败: %s", e)
            return False, None
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, None

    @staticmethod
    def get_storage_stats():
        """获取存储空间占用概览（uploads + outputs 目录）"""
        # 使用 du 命令（Linux）计算目录大小，比遍历更快
        def _get_dir_size_du(path):
            try:
                result = subprocess.run(
                    ['du', '-sb', path], capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return int(result.stdout.split()[0])
            except Exception:
                pass
            return 0

        def _get_dir_size_walk(path):
            """fallback: os.walk 遍历计算"""
            total = 0
            try:
                for dirpath, _dirnames, filenames in os.walk(path):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
            except Exception:
                pass
            return total

        def _count_files(path):
            """统计文件数"""
            count = 0
            try:
                for dirpath, _dirnames, filenames in os.walk(path):
                    count += len(filenames)
            except Exception:
                pass
            return count

        uploads_dir = Config.UPLOAD_FOLDER
        outputs_dir = Config.OUTPUT_FOLDER

        uploads_size = _get_dir_size_du(uploads_dir) or _get_dir_size_walk(uploads_dir)
        outputs_size = _get_dir_size_du(outputs_dir) or _get_dir_size_walk(outputs_dir)
        uploads_count = _count_files(uploads_dir)
        outputs_count = _count_files(outputs_dir)

        return {
            'uploads_size': uploads_size,
            'outputs_size': outputs_size,
            'total_size': uploads_size + outputs_size,
            'uploads_count': uploads_count,
            'outputs_count': outputs_count,
            'total_count': uploads_count + outputs_count
        }

    @staticmethod
    def get_admin_dashboard_stats():
        """获取管理员仪表盘全局统计"""
        conn = None
        try:
            conn = DatabaseManager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)

                # 用户总数
                cursor.execute("SELECT COUNT(*) as total FROM users")
                total_users = cursor.fetchone()['total']

                # 今日活跃用户数
                cursor.execute(
                    """SELECT COUNT(DISTINCT username) as active
                    FROM conversion_logs
                    WHERE DATE(operation_time) = CURDATE()"""
                )
                today_active = cursor.fetchone()['active']

                # 总转换次数
                cursor.execute("SELECT COUNT(*) as total FROM conversion_logs")
                total_conversions = cursor.fetchone()['total']

                # 今日转换次数
                cursor.execute(
                    """SELECT COUNT(*) as today_total,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as today_success,
                            SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as today_fail
                    FROM conversion_logs
                    WHERE DATE(operation_time) = CURDATE()"""
                )
                today_stats = cursor.fetchone()

                # 成功总数
                cursor.execute(
                    "SELECT COUNT(*) as total FROM conversion_logs WHERE success = TRUE"
                )
                total_success = cursor.fetchone()['total']

                # 本周转换统计
                cursor.execute(
                    """SELECT COUNT(*) as weekly_total,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as weekly_success,
                            SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as weekly_fail
                    FROM conversion_logs
                    WHERE operation_time >= DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)"""
                )
                weekly_stats = cursor.fetchone()

                # 按模式统计（Top 10）
                cursor.execute(
                    """SELECT mode, COUNT(*) as count
                    FROM conversion_logs
                    GROUP BY mode
                    ORDER BY count DESC
                    LIMIT 10"""
                )
                by_mode = cursor.fetchall()

                # 按用户统计（Top 10）
                cursor.execute(
                    """SELECT username, COUNT(*) as count
                    FROM conversion_logs
                    GROUP BY username
                    ORDER BY count DESC
                    LIMIT 10"""
                )
                by_user = cursor.fetchall()

                cursor.close()

                today_total = today_stats['today_total'] or 0
                today_success = today_stats['today_success'] or 0
                today_fail = today_stats['today_fail'] or 0
                weekly_total = weekly_stats['weekly_total'] or 0
                weekly_success = weekly_stats['weekly_success'] or 0
                weekly_fail = weekly_stats['weekly_fail'] or 0

                return True, {
                    'total_users': total_users,
                    'today_active': today_active,
                    'total_conversions': total_conversions,
                    'total_success': total_success,
                    'today_total': today_total,
                    'today_success': today_success,
                    'today_fail': today_fail,
                    'weekly_total': weekly_total,
                    'weekly_success': weekly_success,
                    'weekly_fail': weekly_fail,
                    'by_mode': by_mode,
                    'by_user': by_user
                }
        except Error as e:
            logger.error("获取管理员仪表盘统计失败: %s", e)
            return False, None
        finally:
            if conn:
                DatabaseManager.return_connection(conn)
        return False, None



