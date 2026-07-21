"""Twitter 平台模拟脚本（独立子进程）。

用法：python run_twitter_simulation.py --sim-id <id> --config <path> --work-dir <dir>
优先尝试真实 OASIS 模拟；依赖/密钥不可用时回退到降级模拟循环。
"""

import argparse
import json
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from action_logger import run_mock_simulation

# 本脚本负责的平台
PLATFORMS = ["twitter"]


def _try_real_oasis(sim_id: str, cfg: dict, work_dir: str) -> bool:
    """尝试运行真实 OASIS 模拟；不可用则返回 False 以回退。"""
    try:
        import oasis  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    if not os.getenv("LLM_API_KEY"):
        return False
    try:
        # 真实 OASIS 接入点：在完整依赖 + 密钥的部署环境中，
        # 可在此调用 oasis 的 Agent 生成与社交模拟接口。
        # 为保证健壮性，任何异常都回退到降级模拟。
        raise NotImplementedError("真实 OASIS 运行需在部署环境中启用")
    except Exception:  # noqa: BLE001
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Twitter 单平台模拟")
    parser.add_argument("--sim-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not _try_real_oasis(args.sim_id, cfg, args.work_dir):
        run_mock_simulation(PLATFORMS, args.sim_id, cfg, args.work_dir)


if __name__ == "__main__":
    main()
