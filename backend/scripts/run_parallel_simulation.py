"""双平台并行模拟脚本（核心亮点，独立子进程）。

同时模拟 Twitter 与 Reddit 两个平台的 Agent 交互与社会演化。
用法：python run_parallel_simulation.py --sim-id <id> --config <path> --work-dir <dir>
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

# 双平台并行
PLATFORMS = ["twitter", "reddit"]


def _try_real_oasis(sim_id: str, cfg: dict, work_dir: str) -> bool:
    """尝试运行真实的双平台并行 OASIS 模拟；不可用则返回 False 以回退。"""
    try:
        import oasis  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    if not os.getenv("LLM_API_KEY"):
        return False
    try:
        from oasis_runner import run_real_simulation

        run_real_simulation(PLATFORMS, sim_id, cfg, work_dir)
        return True
    except Exception as e:  # noqa: BLE001
        # 清空可能产生的部分输出，确保回退到降级循环时从干净状态开始
        try:
            open(os.path.join(work_dir, "actions.jsonl"),
                 "w", encoding="utf-8").close()
        except Exception:  # noqa: BLE001
            pass
        print(f"[oasis] 真实双平台模拟失败，回退到降级循环：{e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Twitter + Reddit 双平台并行模拟")
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
