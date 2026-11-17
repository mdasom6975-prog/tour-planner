"""PostToolUse 훅: 파이썬 파일을 고친 뒤 pytest 를 돌린다. 실패하면 Claude 에게 결과를 돌려준다. (PRD 12-3, 14번 10단계)

표준 입력으로 훅 JSON 을 받는다. 파이썬 파일이 아니면 아무것도 하지 않는다.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # 저장소 뿌리


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    path = (data.get("tool_input") or {}).get("file_path") or (data.get("tool_response") or {}).get("filePath") or ""
    # 왜: 문서 · 설정을 고칠 때마다 테스트를 돌리면 느리기만 하다. 이 저장소의 파이썬 파일일 때만 돌린다. 어디: 훅 입구.
    # 교안: 2일차 하네스 "코드 편집 뒤 자동 검사". 직접 대응 없음(훅 형식은 Claude Code 문서).
    if not path.endswith(".py") or ROOT not in Path(path).resolve().parents:
        return 0
    run = subprocess.run([str(ROOT / ".venv" / "bin" / "python"), "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120)
    if run.returncode == 0:
        return 0
    # 종료 코드 2 + 표준 오류 = Claude 에게 되돌려 보내는 내용. 마지막 줄들만 보낸다(키 값이 출력에 섞일 일은 없지만 길이를 줄인다)
    print("pytest 실패 (편집한 파일: %s)\n%s" % (Path(path).name, "\n".join(run.stdout.splitlines()[-25:])), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
