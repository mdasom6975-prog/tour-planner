"""임베딩 가중치와 재정렬 후보 수를 바꿔 가며 같은 질문으로 잰다. config 의 값은 바꾸지 않는다. (PRD 14번 3단계 중 3-5a)

실행:  python -m eval.compare_settings     (고름용 20건만. 확인용은 설정을 정한 뒤 retrieval_eval 로 한 번)
결과는 runs/retrieval/settings_고름.json 에 저장한다(git 밖).
"""
import json
import time
from pathlib import Path

import config
from eval.metrics import ndcg_at_k, recall_at_k, unjudged_at_k
from eval.retrieval_eval import OUT_DIR, SET_PATH, _judged_ids, _mean, _read
from eval.searchers import make_searchers

ROOT = Path(__file__).resolve().parent.parent
EPS = 1e-9


def _settings() -> list:
    """[(이름, 검색기, 넘길 인자)]. 합침은 가중치만, 재정렬은 가중치 × 후보 수."""
    out = [(f"hybrid w{w}", "hybrid", {"w_dense": w}) for w in config.EVAL_W_DENSE_GRID if w < 1.0]   # 1.0 의 합침은 임베딩 단독과 같다
    out += [(f"rerank w{w} c{c}", "rerank", {"w_dense": w, "candidates": c})
            for w in config.EVAL_W_DENSE_GRID for c in config.EVAL_RERANK_CAND_GRID]
    return out


def run(k: int | None = None, encoder=None, scorer=None) -> dict:
    """성공: {"ok": True, "current", "table", "unjudged_places", "questions", ...} / 실패: {"ok": False, "reason"}"""
    places_path = ROOT / config.EVAL_PLACES
    if not SET_PATH.exists() or not places_path.exists():
        return {"ok": False, "reason": f"파일이 없습니다: {SET_PATH.name} 또는 {config.EVAL_PLACES}"}
    k = config.EVAL_K if k is None else k
    questions = [q for q in _read(SET_PATH) if q["split"] == "고름"]
    searchers, _ = make_searchers(_read(places_path), encoder=encoder, scorer=scorer)
    judged = _judged_ids()
    settings = _settings()
    current = f"rerank w{config.HYBRID_W_DENSE} c{config.RERANK_CANDIDATES}"
    searchers["rerank"]("준비", k)   # 모델을 불러오는 시간이 첫 질문에 섞이지 않게

    rows, failed, missing = [], [], {}
    for q in questions:
        row = {"id": q["id"], "query": q["query"], "kind": q["kind"], "by": {}}
        for name, base, kwargs in settings:
            started = time.perf_counter()
            r = searchers[base](q["query"], k, region=q["region"], today=q["today"], **kwargs)
            ms = round((time.perf_counter() - started) * 1000, 1)
            if not r["ok"]:
                failed.append({"qid": q["id"], "setting": name, "reason": r["reason"]})
                row["by"][name] = {"ok": False, "ms": ms}
                continue
            ids = [item["id"] for item in r["results"]]
            # 왜: 정답은 지금 설정의 검색기가 고른 곳만 보고 매겼다. 새 설정이 올린 낯선 곳은 0점이 되어 불리하므로, 누구인지 모아 추가 판정한다. 어디: 미판정 세기.
            # 교안: 직접 대응 없음. 3-2a 풀링의 한계를 설정 비교에서 메우는 절차다.
            unjudged = 0
            if not q.get("rule") and q["answers"]:
                done = judged.get(q["id"], set())
                unjudged = unjudged_at_k(ids, done, k)
                for item in r["results"]:
                    if item["id"] not in done:
                        missing[(q["id"], item["id"])] = item["title"]
            row["by"][name] = {"ok": True, "recall": recall_at_k(ids, q["answers"], k), "ndcg": ndcg_at_k(ids, q["answers"], k),
                               "unjudged": unjudged, "ms": ms, "top": ids}
        rows.append(row)

    # 왜: 평균만 보면 한 질문이 크게 오른 것과 여러 질문이 조금씩 오른 것을 구별하지 못한다. 현재 설정보다 좋아진 · 나빠진 질문 수를 함께 센다. 어디: 표.
    # 교안: 2일차 Part3 — 바꿀지 말지의 기준(평균 0.02 이상 + 좋아진 질문이 더 많음)을 결과를 보기 전에 정해 두었다.
    table = {}
    for name, _, _ in settings:
        cells = [(row["by"][name], row["by"][current]) for row in rows if row["by"][name]["ok"] and row["by"][name]["ndcg"] is not None]
        table[name] = {"n": len(cells), "recall": _mean([c["recall"] for c, _ in cells]), "ndcg": _mean([c["ndcg"] for c, _ in cells]),
                       "ms": _mean([row["by"][name]["ms"] for row in rows]),
                       "better": sum(c["ndcg"] > base["ndcg"] + EPS for c, base in cells),
                       "worse": sum(c["ndcg"] < base["ndcg"] - EPS for c, base in cells),
                       "unjudged": sum(c["unjudged"] for c, _ in cells)}
    result = {"ok": True, "k": k, "current": current, "table": table, "failed": failed,
              "unjudged_places": [{"qid": qid, "place_id": pid, "title": title} for (qid, pid), title in sorted(missing.items())],
              "questions": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "settings_고름.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    result["path"] = str(out_path)
    return result


if __name__ == "__main__":
    res = run()
    if not res["ok"]:
        print(res["reason"])
        raise SystemExit(1)
    print(f"현재 설정: {res['current']} · 실패 {len(res['failed'])}건 · 판정하지 않은 곳 {len(res['unjudged_places'])}곳")
    for name, s in res["table"].items():
        mark = " ← 현재" if name == res["current"] else ""
        print(f"{name:18s} n={s['n']:2d}  Recall {s['recall']:.3f}  nDCG {s['ndcg']:.3f}  {s['ms']:7.1f}ms  좋아짐 {s['better']:2d} 나빠짐 {s['worse']:2d}  미판정 {s['unjudged']}{mark}")
    print("저장:", res["path"])
