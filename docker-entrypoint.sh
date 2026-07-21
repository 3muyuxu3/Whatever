#!/bin/sh
# SimulMirror 容器入口：同时启动后端与前端预览。
set -e

# 后端 Flask（后台运行，端口 5001）
cd /app/backend && uv run python run.py &

# 前端 Vite 预览（前台运行，端口 3001，绑定 0.0.0.0）
cd /app/frontend && pnpm run preview
