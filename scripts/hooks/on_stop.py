"""Stop 훅: 응답을 끝낼 때 가장 최근 평가 실행 기록을 다시 채점해 코스 규칙 위반 수를 기록한다. 모델을 부르지 않는다. (PRD 12-3, 14번 10단계)

- 코드(.py)가 지난 기록 이후 바뀐 턴에만 돈다. 결과는 logs/hooks/eval.log 에 한 줄씩 쌓인다.
- 규칙 위반이 1건 이상이면 Claude 가 끝내지 못하게 막고 이유를 알린다(합격선 0건).
- 한계: 실제 평가를 새로 돌리지 않는다. "지금 채점기로 본 최근 실행 기록"이므로 코스를 만드는 코드를 고쳤다면 /eval 로 다시 돌려야 한다.
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
LOG_DIR = ROOT / "logs" / "hooks"


def code_state() -> str:
    """HEAD 와 작업 폴더의 파이썬 변경을 합친 지문. 같으면 지난번과 코드가 같다."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout
    return hashlib.sha256((git("rev-parse", "HEAD") + git("diff", "HEAD", "--", "*.py") + git("status", "--porcelain", "--", "*.py")).encode()).hexdigest()[:16]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    # 왜: 이 훅이 막아서 Claude 가 다시 일한 뒤 또 막으면 끝나지 않는다. 한 번 막은 뒤에는 통과시킨다. 어디: 훅 입구.
    # 교안: 직접 대응 없음(Claude Code 훅의 stop_hook_active).
    if data.get("stop_hook_active"):
        return 0
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    state_file, state = LOG_DIR / "last_state", code_state()
    if state_file.exists() and state_file.read_text().strip() == state:
        return 0   # 코드가 그대로면 다시 채점하지 않는다
    try:
        from eval.score import latest_run, score_rows
        run_dir = latest_run()
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        with (ROOT / meta["places"]).open(encoding="utf-8") as f:
            places = {p["id"]: p for p in map(json.loads, f)}
        lines = []
        total = 0
        for path in sorted(p for p in run_dir.glob("*.jsonl") if not p.name.startswith("ground_")):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            s = score_rows(rows, places)
            total += s["rule_total"]
            lines.append(f"{path.stem} 기대 동작 {s['expect_ok']}/{s['count']} · 규칙 위반 {s['rule_total']}건 {s['rule_violations']}")
        record = f"{datetime.now().isoformat(timespec='seconds')} 코드 {state} 실행 {run_dir.name} | " + " | ".join(lines)
    except Exception as e:   # 훅이 죽어도 작업을 막지 않는다. 기록만 남긴다
        with (LOG_DIR / "eval.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} 채점 실패 {type(e).__name__}\n")
        return 0
    with (LOG_DIR / "eval.log").open("a", encoding="utf-8") as f:
        f.write(record + "\n")
    state_file.write_text(state)
    if total > 0:
        print(json.dumps({"decision": "block", "reason": f"코스 규칙 위반 {total}건(합격선 0건). {record}. 원인을 확인하고 고치세요."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
