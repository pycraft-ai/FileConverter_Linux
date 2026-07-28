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

    # 降低第三方库日志噪音
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

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
