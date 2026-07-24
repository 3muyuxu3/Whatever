"""SimulMirror 后端启动入口。"""

import os
import sys

# 解决 Windows 控制台中文乱码：必须在导入 app（会初始化日志、触发输出）之前，
# 将标准输出/错误流重设为 UTF-8，否则中文日志在 GBK 控制台会变成乱码。
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app import create_app  # noqa: E402
from app.config import config  # noqa: E402

# 创建 Flask 应用（供 `flask run` 或 gunicorn 等使用）
app = create_app()


if __name__ == "__main__":
    # 启动前校验关键配置：缺失 LLM/Zep 时打印警告（不阻断，支持降级运行）
    for _warning in config.validate():
        print(f"[配置警告] {_warning}")
    # 直接运行：python run.py
    # threaded=True：保证 SSE 流式接口进行中仍能处理其他并发请求
    app.run(host=config.HOST, port=config.PORT,
            debug=config.DEBUG, threaded=True)
