"""코스 평가셋(eval/course_set.jsonl)의 형식만 검사한다. 모델을 부르지 않는다. (14번 8-1)"""
import json
from collections import Counter
from datetime import date
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent.parent
ROWS = [json.loads(line) for line in (ROOT / "eval" / "course_set.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
KINDS = {"course", "ask_back", "abstain"}
EXPECT_KEYS = {"kind", "region", "place", "days", "start_date", "missing", "exclusions", "museum_max", "notice_has", "text_has",
               "text_not", "title_has", "title_not", "mode", "changed"}
MISSING_CODES = {"region", "days", "start_date", "days_too_long", "unsupported_region", "parse_failed"}


def test_40건이고_유형과_분할이_PRD와_같다():
    # 왜: PRD 12-2 "4유형 40건, dev 28 / holdout 12". 유형마다 양쪽에 고르게 들어가야 holdout 이 한 유형으로 쏠리지 않는다.
    assert len(ROWS) == 40 and len({r["id"] for r in ROWS}) == 40
    assert Counter(r["split"] for r in ROWS) == {"dev": 28, "holdout": 12}
    assert Counter(r["case"] for r in ROWS) == {"정상": 16, "경계": 8, "엣지": 8, "공격": 8}
    assert all(Counter(r["case"] for r in ROWS if r["split"] == "holdout")[c] >= 2 for c in ("정상", "경계", "엣지", "공격"))


def test_문항마다_필요한_칸이_있고_값이_표_안에_있다():
    for r in ROWS:
        exp = r["expect"]
        assert set(r) == {"id", "case", "split", "today", "turns", "expect", "note"}, r["id"]
        assert r["turns"] and all(isinstance(t, str) and t.strip() for t in r["turns"]), r["id"]
        assert exp["kind"] in KINDS and set(exp) <= EXPECT_KEYS, r["id"]
        assert exp.get("region") in (None, *config.REGIONS), r["id"]
        assert set(exp.get("missing", [])) <= MISSING_CODES, r["id"]
        if exp.get("days") is not None:
            assert 1 <= exp["days"] <= config.MAX_TRIP_DAYS, r["id"]
        if exp.get("start_date"):   # 기대 날짜는 기준일 이후여야 한다(지난 날짜는 되묻기 문항이다)
            assert date.fromisoformat(exp["start_date"]) >= date.fromisoformat(r["today"]), r["id"]
        if exp["kind"] == "course":
            assert exp.get("region") and exp.get("days") and exp.get("start_date"), r["id"]


def test_평가_문장은_지시문과_시연_버튼에_들어_있지_않다():
    # 왜: 평가 문장이 퓨샷 예시나 지시문에 있으면 점수가 부풀려진다(CLAUDE.md 평가 규칙). 어디: graph/ 의 지시문과 app.py 의 시연 문장.
    sources = "".join(p.read_text(encoding="utf-8") for p in [*(ROOT / "graph").glob("*.py"), ROOT / "app.py"])
    assert not [t for r in ROWS for t in r["turns"] if t in sources]
