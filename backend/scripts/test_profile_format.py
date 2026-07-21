"""Profile 格式验证脚本。

校验生成的 Agent 人设（Reddit JSON）是否包含必需字段，可用于调试与测试。
用法：python test_profile_format.py <profiles.json>
"""

import json
import sys

# 人设必需字段
REQUIRED_FIELDS = ["name", "bio", "persona", "mbti", "occupation", "interests"]


def validate_profile(profile: dict) -> list[str]:
    """校验单个人设，返回缺失字段列表（空列表表示通过）。"""
    missing = [f for f in REQUIRED_FIELDS if f not in profile]
    # interests 需为列表
    if "interests" in profile and not isinstance(profile["interests"], list):
        missing.append("interests(must be list)")
    return missing


def validate_profiles(profiles: list[dict]) -> bool:
    """校验人设列表，打印结果并返回是否全部通过。"""
    ok = True
    for i, p in enumerate(profiles):
        missing = validate_profile(p)
        if missing:
            ok = False
            print(f"[FAIL] profile #{i} 缺失字段：{missing}")
        else:
            print(f"[OK] profile #{i}: {p.get('name')}")
    return ok


def main() -> None:
    if len(sys.argv) < 2:
        print("用法：python test_profile_format.py <profiles.json>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        profiles = json.load(f)
    if not isinstance(profiles, list):
        print("错误：profiles 应为 JSON 数组")
        sys.exit(1)
    sys.exit(0 if validate_profiles(profiles) else 2)


if __name__ == "__main__":
    main()
