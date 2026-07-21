"""API 蓝图注册中心。"""

from .graph import graph_bp
from .report import report_bp
from .simulation import simulation_bp


def register_blueprints(app) -> None:
    """将所有蓝图注册到 Flask 应用。"""
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    app.register_blueprint(report_bp, url_prefix="/api/report")
