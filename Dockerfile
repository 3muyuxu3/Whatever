# ============ SimulMirror 一体化镜像（前端 + 后端） ============
# 前端使用 Vite 构建并通过 preview 提供，后端为 Flask，打包在同一镜像中。
# 加速镜像（可选）：如需国内加速，可将下方 base 镜像替换为
#   ghcr.nju.edu.cn/library/python:3.12-slim 等镜像地址。

FROM python:3.12-slim

# 安装 Node.js 22 与基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 pnpm 与 uv
RUN npm install -g pnpm@10 && pip install --no-cache-dir uv

WORKDIR /app

# ---- 前端：安装依赖并构建 ----
COPY frontend ./frontend
RUN cd frontend && pnpm install --frozen-lockfile && pnpm run build

# ---- 后端：安装完整依赖 ----
COPY backend ./backend
RUN cd backend && uv sync --frozen --no-dev

# 入口脚本
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# 前端 3001，后端 API 5001
EXPOSE 3001 5001
# preview 代理指向同容器内的后端
ENV BACKEND_URL=http://localhost:5001

CMD ["/app/docker-entrypoint.sh"]
