"""실행: .venv/bin/python scripts/replay_regressions.py --suite <녹화 폴더> [--strict-known]."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.regression import run_suite


def main():
    parser = argparse.ArgumentParser(description="모델·네트워크 없이 저장된 검증 사례 전체 재생")
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict-known", action="store_true", help="기존 미해결 문제도 종료 코드 1로 처리")
    args = parser.parse_args()
    try:
        report = run_suite(args.suite, args.output or args.suite.parent / "reports")
    except Exception as exc:
        print(f"회귀 검증 실행 실패: {type(exc).__name__}", file=sys.stderr)
        return 2
    print("합계:", report["counts"])
    return int(bool(report["counts"]["FAIL"] or (args.strict_known and report["counts"]["KNOWN_ISSUE"])))


if __name__ == "__main__":
    raise SystemExit(main())
