"""검색 평가의 정답 후보를 모은다. 판정(3-2b) · 채점(3-3)은 여기 없다. (PRD 14번 3단계 중 3-2a)

질문마다 검색기 네 가지의 상위 결과를 합쳐 섞어 eval/pool/candidates.jsonl 로, 누가 몇 위로 골랐는지는 sources.jsonl 로 따로 쓴다.
조건 질문(rule 이 있는 것)은 검색하지 않고 데이터에서 정답을 계산해 rule_answers.jsonl 로 쓴다.
실행:  python -m eval.build_pool
"""
import json
import random
from pathlib import Path

import config
from eval.searchers import make_searchers
from rag.filters import is_visible

ROOT = Path(__file__).resolve().parent.parent
SET_PATH = ROOT / "eval" / "retrieval_set.jsonl"
POOL_DIR = ROOT / "eval" / "pool"
NEGATIVE = ("없음", "불가", "없습니다", "어려움", "어렵")


def _read(path: Path) -> list:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def rule_answers(question: dict, places: list) -> list:
    """조건 질문의 정답을 데이터에서 계산한다. [{"place_id", "title", "value", "check"}]"""
    # 왜: "수유실 있는 전북 문화시설" 은 판단이 아니라 사실이다. 검색 결과에서 고르면 검색기가 놓친 곳이 정답에서 빠진다. 어디: 조건 질문 6건.
    # 교안: "숫자와 사실 판정은 코드가". RAG 실습1 Q2 의 qrels 를 사람 대신 규칙으로 만드는 경우다.
    rule, out = question["rule"], []
    for p in places:
        if not is_visible(p, region=question["region"], types=rule.get("types"), today=question["today"]):
            continue
        if rule.get("pet"):
            value = p["pet"].get("범위", "") if p.get("pet") else ""
        else:
            group, field = rule["access"]
            value = p.get("access", {}).get(group, {}).get(field, "")
        if not value:
            continue
        # 값이 있어도 "수유실 없음" 일 수 있다. 부정 낱말이 든 값은 코드가 판정하지 않고 사람이 보도록 표시만 한다.
        out.append({"place_id": p["id"], "title": p["title"], "value": value, "check": any(w in value for w in NEGATIVE)})
    return out


def build_pool(depth: int | None = None, encoder=None, scorer=None) -> dict:
    """성공: {"ok": True, "pooled", "pool_sizes", "rule", "no_answer", "failed", "path"} / 실패: {"ok": False, "reason"}"""
    places_path = ROOT / config.EVAL_PLACES
    if not SET_PATH.exists() or not places_path.exists():
        return {"ok": False, "reason": f"파일이 없습니다: {SET_PATH.name} 또는 {config.EVAL_PLACES}"}
    depth = config.EVAL_POOL_DEPTH if depth is None else depth
    questions, places = _read(SET_PATH), _read(places_path)
    by_id = {p["id"]: p for p in places}

    searchers, dense = make_searchers(places, encoder=encoder, scorer=scorer)   # 조립은 eval/searchers.py — 채점과 같은 검색기를 쓴다

    candidates, sources, rules, failed, sizes, no_answer = [], [], [], [], {}, 0
    for q in questions:
        if q.get("rule"):
            for a in rule_answers(q, places):
                rules.append({"qid": q["id"], "query": q["query"], **a})
            continue
        if q["answers"] == []:   # 정답 없음으로 확정된 질문은 후보를 모으지 않는다
            no_answer += 1
            continue

        # 왜: 한 검색기의 결과만 보고 정답을 정하면 그 검색기에 유리한 정답이 된다. 네 가지의 결과를 합쳐 후보로 삼는다(풀링). 어디: 질문마다.
        # 교안: 직접 대응 없음. 한계 — 네 검색기가 모두 놓친 정답은 후보에 없어 Recall 이 실제보다 높게 나올 수 있다.
        ranks = {}
        for name, search in searchers.items():
            r = search(q["query"], depth, region=q["region"], today=q["today"])
            if not r["ok"]:
                failed.append({"qid": q["id"], "searcher": name, "reason": r["reason"]})
                continue
            for n, item in enumerate(r["results"], start=1):
                ranks.setdefault(item["id"], {})[name] = n

        # 왜: 순위가 보이면 "1위니까 맞겠지" 로 기운다. 질문마다 고정된 씨앗으로 섞고, 순위는 다른 파일에 둔다. 어디: 저장 전.
        # 교안: 2일차 Part3 — 채점 기준을 결과를 보기 전에 정한다는 원칙을 판정 화면에 적용한 것.
        ids = sorted(ranks)
        random.Random(f"{config.EVAL_SEED}-{q['id']}").shuffle(ids)
        sizes[q["id"]] = len(ids)
        for pid in ids:
            p = by_id[pid]
            candidates.append({"qid": q["id"], "query": q["query"], "place_id": pid, "title": p["title"], "type": p["type"],
                               "region": p["region"], "addr": p["addr"], "text": p["search_text"]})
            sources.append({"qid": q["id"], "place_id": pid, "ranks": ranks[pid]})

    POOL_DIR.mkdir(parents=True, exist_ok=True)
    _write(POOL_DIR / "candidates.jsonl", candidates)
    _write(POOL_DIR / "sources.jsonl", sources)
    _write(POOL_DIR / "rule_answers.jsonl", rules)

    rule_counts = {}
    for r in rules:
        c = rule_counts.setdefault(r["qid"], {"answers": 0, "check": 0})
        c["answers"] += 1
        c["check"] += r["check"]
    return {"ok": True, "pooled": len(sizes), "candidates": len(candidates), "pool_sizes": sizes, "rule": rule_counts,
            "no_answer": no_answer, "failed": failed, "dense": dense.stats, "path": str(POOL_DIR)}


if __name__ == "__main__":
    print(json.dumps(build_pool(), ensure_ascii=False, indent=1))
