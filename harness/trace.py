"""실행 기록. 질문 한 건을 처리하는 동안 끝난 단계를 순서대로 남긴다. (PRD 12-1, 14번 2-a)

화면의 개발자 모드(실행 추적)와 평가 하네스가 이 기록을 읽는다. 화면에 그리기 · 집계는 여기 없다.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

# 왜: 뒤에서 도구 · LLM 호출을 기록할 때 키가 실수로 섞이는 것을 형식 단계에서 막는다. 어디: summarize.
# 교안: 2일차 Part4 "비밀은 .env 에만" — 키는 코드 · 지시문 · 로그에 남기지 않는다.
# 이름이 이 낱말로 "끝나는" 항목만 가린다. 처음에는 "들어 있으면" 가렸는데, 검색어를 나눈 낱말(query_tokens)과
# LLM 토큰 수(input_tokens)까지 가려져서 고쳤다. "tokens" 는 가리지 않고 "token" 은 가린다.
SENSITIVE_ENDINGS = ("key", "token", "secret", "password", "authorization")
MAX_CHARS = 200
MAX_ITEMS = 5


def _is_secret(name) -> bool:
    return str(name).lower().endswith(SENSITIVE_ENDINGS)


def summarize(value):
    # 왜: 지시문 전문이나 긴 소개글이 통째로 기록되면 파일이 커지고 화면에 그대로 드러난다. 기록할 때 줄인다. 어디: 입력 · 출력 전부.
    # 교안: PRD F4 "입력 · 출력은 요약한다". 화면에서 가리는 것만으로는 파일에 남으므로 기록 단계에서 한다.
    if isinstance(value, str):
        return value if len(value) <= MAX_CHARS else f"{value[:MAX_CHARS]}…(전체 {len(value)}자)"
    if isinstance(value, dict):
        return {
            k: "***" if _is_secret(k) else summarize(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        head = [summarize(v) for v in value[:MAX_ITEMS]]
        return head if len(value) <= MAX_ITEMS else head + [f"…(외 {len(value) - MAX_ITEMS}건)"]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return summarize(str(value))


class Trace:
    def __init__(self, run_id: str | None = None, base_dir: Path = RUNS_DIR, clock=None, save: bool = True):
        # 왜: 시각과 실행 번호를 바꿔 끼울 수 있어야 평가에서 같은 입력에 같은 기록이 나온다. 어디: 생성자.
        # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 외부 의존(여기서는 현재 시각)을 인자로 받는다.
        self.clock = clock or datetime.now
        now = self.clock()
        self.run_id = run_id or f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        self.steps = []
        self.path = Path(base_dir) / f"{now:%Y-%m-%d}" / f"{self.run_id}.jsonl" if save else None

    def record(self, step: str, kind: str, input=None, output=None, ok: bool = True, took_ms: float | None = None) -> dict:
        """끝난 단계 하나를 남긴다. kind 는 tool(도구) · node(그래프 단계) · llm(모델 호출) 중 하나."""
        # 왜: 모든 단계가 같은 모양으로 남아야 화면이 한 가지 방식으로 그리고 평가가 한 가지 방식으로 집계한다. 어디: 기록 한 줄.
        # 교안: 3일차 day3_tools.run_agent 의 verbose 출력(도구 이름 · 인자 · 결과)을 눈으로 보는 대신 값으로 남긴 것.
        entry = {
            "run_id": self.run_id,
            "seq": len(self.steps) + 1,
            "step": step,
            "kind": kind,
            "input": summarize(input),
            "output": summarize(output),
            "ok": bool(ok),
            "took_ms": took_ms,
            "at": f"{self.clock():%H:%M:%S}",
        }
        self.steps.append(entry)

        # 왜: 메모리의 기록은 화면이 바로 그리고, 파일의 기록은 나중에 평가 하네스가 읽는다. 중간에 꺼져도 남게 줄마다 쓴다. 어디: 저장.
        # 교안: PRD 12-1 "요청마다 runs/날짜/run_id.jsonl". 1-5b 상세 수집에서 받는 즉시 한 줄씩 덧붙이던 것과 같다.
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
