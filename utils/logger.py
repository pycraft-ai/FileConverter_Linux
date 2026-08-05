"""
统一日志配置模块。
同时输出到终端（便于开发调试）和文件（持久化留存，自动按天轮转）。
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler


def setup_logger(name: str = 'fileconverter',
                 log_dir: str = None,
                 level: int = logging.INFO) -> logging.Logger:
    """
    初始化应用级日志系统，只调用一次即可。

    Args:
        name: 日志记录器名称
        log_dir: 日志文件目录，默认为项目根目录下的 logs/
        level: 日志级别，默认 INFO

    Returns:
        配置好的 root logger
    """
    if log_dir is None:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'logs'
        )

    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler（模块重新加载等情况）
    if logger.handlers:
        return logger

    # 关键：禁止日志向上传播到 root logger。
    # gunicorn 会给 root logger 附加默认 handler，若不关闭 propagate，
    # 同一行日志会被打印两次（自定义格式 + root 的 [INFO] 格式）。
    logger.propagate = False

    # --- 终端输出格式：带颜色级别 + 模块名 ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_fmt = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-7s | %(name)s.%(funcName)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # --- 文件输出格式：完整时间 + 完整路径 ---
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # 文件记录更详细级别
    file_fmt = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-7s | %(name)s.%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # 降低第三方库日志噪音（只保留 WARNING 及以上）
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('mysql.connector').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)

    # root logger 兜底：确保未被 fileconverter 显式管理的日志不会以 INFO 级别刷屏。
    # 第三方库（如 mysql-connector 的插件探测日志）会传播到 root，这里把 root 提到 WARNING，
    # 避免其 INFO 级别的 [INFO] 噪音混入。
    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取子模块日志记录器，命名格式为 fileconverter.<模块名>。

    Usage:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info('xxx')
    """
    return logging.getLogger(f'fileconverter.{name}')
