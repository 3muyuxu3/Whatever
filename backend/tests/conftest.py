"""pytest 公共夹具与路径配置。"""

import os
import sys

# 将 backend 根目录与 scripts 目录加入 sys.path，便于导入 app 与脚本模块
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for p in (BACKEND_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)
