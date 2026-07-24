"""统一模拟脚本（独立子进程）。

支持 Twitter 单平台、Reddit 单平台与双平台并行三种模式，由 --platform 指定，
替代原先近乎重复的 run_twitter/reddit/parallel_simulation.py 三个脚本（DRY）。
优先尝试真实 OASIS 模拟；依赖/密钥不可用时回退到降级模拟循环。

用法：python run_simulation.py --sim-id <id> --config <path> --work-dir <dir> --platform parallel
"""

import argparse
import json
import logging
import os
import signal

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from action_logger import run_mock_simulation

# 平台模式 -> 平台列表
PLATFORM_SETS = {
    "twitter": ["twitter"],
    "reddit": ["reddit"],
    "parallel": ["twitter", "reddit"],
}

# OASIS 库各模块在 import 时即于 ./log 下按时间生成运行期日志（oasis-* / social.* /
# table-*），长期运行会不断堆积。这些前缀用于「跑完即删」清理，
# 不含后端自身的 simulmirror.log（由主进程持有，另行管理）。
_RUN_LOG_PREFIXES = (
    "oasis-", "oasis.env-", "social.agent-", "social.twitter-",
    "social.reddit-", "table-",
)


def _cleanup_run_logs() -> None:
    """模拟子进程退出前，关闭并删除本次运行生成的 OASIS 日志文件。

    先关闭指向运行期日志文件的 FileHandler 释放句柄（Windows 上打开的
    文件无法删除），再删除文件；并兜底清理日志目录下的同类残留。
    """
    targets: set[str] = set()
    # 1) 遍历所有 logger，关闭指向运行期日志文件的 FileHandler
    try:
        manager = logging.Logger.manager
        loggers = [logging.getLogger()]
        loggers += [lg for lg in manager.loggerDict.values()
                    if isinstance(lg, logging.Logger)]
        for lg in loggers:
            for h in list(getattr(lg, "handlers", []) or []):
                fn = getattr(h, "baseFilename", None)
                if fn and os.path.basename(fn).startswith(_RUN_LOG_PREFIXES):
                    targets.add(fn)
                    try:
                        h.close()
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        lg.removeHandler(h)
                    except Exception:  # noqa: BLE001
                        pass
    except Exception:  # noqa: BLE001
        pass
    # 2) 兜底：收集日志目录（cwd/./log 与 backend/log）下的同类文件
    log_dirs = {os.path.abspath("./log"), os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "log")}
    for d in log_dirs:
        try:
            if os.path.isdir(d):
                for name in os.listdir(d):
                    if name.startswith(_RUN_LOG_PREFIXES):
                        targets.add(os.path.join(d, name))
        except OSError:
            pass
    # 3) 删除已关闭的日志文件
    for fn in targets:
        try:
            os.remove(fn)
        except OSError:
            pass


def _install_signal_cleanup() -> None:
    """将终止信号转为 SystemExit，以保证被停止时仍能走 finally 清理日志。"""
    def _handler(signum, frame):  # noqa: ANN001
        raise SystemExit(0)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        s = getattr(signal, name, None)
        if s is not None:
            try:
                signal.signal(s, _handler)
            except (ValueError, OSError):
                pass


def _try_real_oasis(platforms: list, sim_id: str, cfg: dict, work_dir: str) -> bool:
    """尝试运行真实 OASIS 模拟；不可用则返回 False 以回退。"""
    try:
        import oasis  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    if not os.getenv("LLM_API_KEY"):
        return False
    try:
        from oasis_runner import run_real_simulation

        run_real_simulation(platforms, sim_id, cfg, work_dir)
        return True
    except Exception as e:  # noqa: BLE001
        # 任何异常都回退到降级模拟；清空可能的部分输出以保证干净状态
        try:
            with open(os.path.join(work_dir, "actions.jsonl"), "w", encoding="utf-8"):
                pass
        except Exception:  # noqa: BLE001
            pass
        print(f"[oasis] 真实模拟失败（{','.join(platforms)}），回退到降级循环：{e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OASIS 模拟（Twitter / Reddit / 双平台并行）")
    parser.add_argument("--sim-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--platform", default="parallel",
                        choices=list(PLATFORM_SETS.keys()))
    args = parser.parse_args()

    platforms = PLATFORM_SETS.get(args.platform, PLATFORM_SETS["parallel"])

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 终止信号也走清理流程；无论正常跑完还是被停止，退出前都删除运行期 OASIS 日志
    _install_signal_cleanup()
    try:
        if not _try_real_oasis(platforms, args.sim_id, cfg, args.work_dir):
            run_mock_simulation(platforms, args.sim_id, cfg, args.work_dir)
    finally:
        _cleanup_run_logs()


if __name__ == "__main__":
    main()
