# backend/app/utils/logger.py
import sys

from loguru import logger

_configured = False


def setup_logger(name: str):
    """配置并返回 logger（loguru，控制台 + 文件）"""
    global _configured
    if not _configured:
        logger.remove()
        logger.add(sys.stdout, level='INFO',
                   format='<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {name} - {message}')
        logger.add('logs/app_{time:YYYY-MM-DD}.log', level='INFO', rotation='1 day',
                   retention='7 days', encoding='utf-8', enqueue=True)
        _configured = True
    return logger
