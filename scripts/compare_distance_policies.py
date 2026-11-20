"""저장 사례의 하루 거리 기준을 지역·이동 수단별 제안과 비교한다."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.distance_policy import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.suite, args.output)
    print("기존 회귀 결과:", report["baseline"])
    print("기존 보정 코스의 새 하루 기준 판정:", report["counts"]["legacy_corrected"])
    print("실행 중인 거리 정책 변경 없음. 보고서:", args.output / "distance-comparison.md")
    return int(bool(report["baseline"]["FAIL"]))


if __name__ == "__main__":
    raise SystemExit(main())
