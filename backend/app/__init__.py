"""Flask 应用工厂。

负责创建应用、加载配置、启用 CORS、注册蓝图、注册全局错误处理与退出清理钩子。
"""

import atexit

from flask import Flask, jsonify
from flask_cors import CORS

from .api import register_blueprints
from .config import config
from .utils.logger import get_logger

logger = get_logger("app")

# 确保退出清理钩子只注册一次（create_app 可能被多次调用，如测试场景）
_cleanup_registered = False


def create_app() -> Flask:
    """应用工厂。"""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["DEBUG"] = config.DEBUG

    # 确保上传/数据目录存在
    config.ensure_dirs()

    # 允许前端跨域访问 /api/*
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # 注册业务蓝图
    register_blueprints(app)

    # 健康检查（同时暴露关键能力是否可用）
    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "simulmirror-backend",
                "slogan": "模拟镜像，推演未来",
                "features": {
                    "llm": config.has_llm(),
                    "boost_llm": config.has_boost_llm(),
                    "zep": config.has_zep(),
                },
            }
        )

    # ---- 统一错误处理 ----
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "not_found"}), 404

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": "file_too_large"}), 413

    @app.errorhandler(500)
    def server_error(e):
        logger.error("内部错误：%s", e)
        return jsonify({"error": "internal_error", "detail": str(e)}), 500

    # 退出时清理运行中的模拟子进程（仅注册一次）
    global _cleanup_registered
    if not _cleanup_registered:
        from .services.simulation_manager import simulation_manager

        atexit.register(simulation_manager.cleanup_all)
        _cleanup_registered = True

    logger.info("SimulMirror 后端已初始化（debug=%s）", config.DEBUG)
    return app
