"""SimulMirror 后端启动入口。"""

from app import create_app
from app.config import config

# 创建 Flask 应用（供 `flask run` 或 gunicorn 等使用）
app = create_app()


if __name__ == "__main__":
    # 直接运行：python run.py
    # threaded=True：保证 SSE 流式接口进行中仍能处理其他并发请求
    app.run(host=config.HOST, port=config.PORT,
            debug=config.DEBUG, threaded=True)
