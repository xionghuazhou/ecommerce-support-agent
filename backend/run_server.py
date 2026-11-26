# backend/run_server.py
"""启动入口：打印访问地址并启动 uvicorn（由项目根目录的 打开智能助手.bat 调用）

中文提示放在 Python 里而不是 bat 里，规避 cmd 批处理的编码解析问题。
"""
import logging
import logging.handlers
import socket
from pathlib import Path

import uvicorn

# uvicorn 的错误/访问日志落文件（隐藏窗口运行时 stderr 不可见，异常堆栈必须落盘才能排查）
_LOG_DIR = Path(__file__).resolve().parent.parent / 'logs'
_LOG_DIR.mkdir(exist_ok=True)
_fh = logging.handlers.RotatingFileHandler(_LOG_DIR / 'server.log',
                                           maxBytes=5_000_000, backupCount=2, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
logging.getLogger('uvicorn').addHandler(_fh)
logging.getLogger('uvicorn.error').addHandler(_fh)
logging.getLogger('uvicorn.access').addHandler(_fh)
# 根 logger 也落一份，保证所有日志可见（控制台 + 文件双写）
logging.basicConfig(level=logging.INFO,
                    handlers=[logging.StreamHandler(__import__('sys').stdout), _fh],
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')


def get_lan_ip() -> str:
    """取本机局域网 IP（UDP 探测，不实际发包）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def main():
    ip = get_lan_ip()
    print('=' * 60)
    print('  电商智能客服系统 启动中...')
    print()
    print('  本机访问:  http://127.0.0.1:8000')
    print()
    print('  手机/其他电脑访问（需连同一个 Wi-Fi）:')
    print(f'  http://{ip}:8000')
    print()
    print('  停止服务: 按 Ctrl+C 或直接关闭本窗口')
    print('=' * 60)

    try:
        # log_config=None：保留上面的文件日志配置，否则 uvicorn 会覆盖并丢失异常堆栈
        uvicorn.run('app.main:app', host='0.0.0.0', port=8000, log_level='info', log_config=None)
    except KeyboardInterrupt:
        print('\n服务已停止')


if __name__ == '__main__':
    main()
