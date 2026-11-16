"""코스 평가셋을 그래프로 돌려 문항별 실행 기록을 남긴다. 채점은 여기 없다. (PRD 12-2, 14번 8-2)

실행:  python -m eval.run                       (dev 28건, 기본 모델)
       python -m eval.run --ids c01,b02         (고른 문항만)
       python -m eval.run --provider claude,openai
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

import config
from graph.llm import make_llm
from graph.runtime import make_graph
from harness.trace import Trace

ROOT = Path(__file__).resolve().parent.parent


def load_set(split: str = "dev", ids: list | None = None) -> list:
    """평가셋을 읽는다. ids 를 주면 분할과 상관없이 그 문항만 고른다."""
    with (ROOT / config.EVAL_COURSE_SET).open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if ids:
        return [r for r in rows if r["id"] in ids]
    return rows if split == "all" else [r for r in rows if r["split"] == split]


def fixed_weather(lat, lon, start: str, end: str) -> dict:
    # 왜: 실제 예보는 날마다 바뀌어 어제와 오늘 점수를 비교할 수 없다. 날짜별로 정해 둔 값을 Open-Meteo 응답 모양으로 돌려준다(2026-11-16 결정). 어디: get_weather 의 fetch.
    # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 같은 입력이면 같은 결과.
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    days = [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]
    values = [config.EVAL_WEATHER.get(d, config.EVAL_WEATHER_DEFAULT) for d in days]
    return {"daily": {"time": days, "temperature_2m_max": [v["temp_max"] for v in values],
                      "temperature_2m_min": [v["temp_min"] for v in values],
                      "precipitation_probability_max": [v["rain_prob"] for v in values],
                      "snowfall_sum": [v["snow_cm"] for v in values]}}


def stored_only(operation: str, params: dict) -> dict:
    # 왜: 평가는 관광공사 실시간 조회를 하지 않는다(하루 한도 · 재현). "한도 도달"과 같은 모양으로 답하면 도구가 호출 0건으로 저장분을 쓴다. 어디: get_place_detail 의 fetch.
    # 교안: PRD 9번 "실시간이 안 되면 저장분".
    return {"ok": False, "limit": True, "reason": "평가에서는 실시간 조회를 하지 않습니다"}


def _course_view(answer: dict) -> list:
    """코스에서 채점에 쓸 값만 남긴다. 소개글 같은 관광공사 문장은 기록에 넣지 않는다."""
    return [{"date": d["date"], "slots": [{"slot": s["slot"], "id": s["id"], "title": s["title"]} for s in d.get("slots", [])]}
            for d in answer.get("days", [])]


def run_item(item: dict, retriever, llm=None, provider: str | None = None) -> dict:
    """문항 하나를 새 대화로 돌린다. turns 를 차례로 보내고 턴마다 결과를 남긴다."""
    usage = []
    trace = Trace(save=False)
    # 왜: 문항마다 그래프 · 대화 저장소를 새로 만들어야 앞 문항의 코스가 다음 문항에 끌려가지 않는다. 어디: 문항 실행.
    # 교안: 3일차 05 checkpointer — thread 가 다르면 State 도 다르다. 여기서는 저장소까지 새로 만든다.
    graph = make_graph(retriever, trace, llm=llm or make_llm(provider, on_usage=usage.append), checkpointer=MemorySaver(),
                       today=item["today"], weather_fetch=fixed_weather, detail_fetch=stored_only)
    cfg = {"configurable": {"thread_id": item["id"]}}
    turns, error = [], ""
    started = time.perf_counter()
    for text in item["turns"]:
        t0, seen, tokens_before = time.perf_counter(), len(trace.steps), len(usage)
        try:
            out = graph.invoke({"message": text}, cfg)
        except Exception as e:   # 한 문항이 죽어도 나머지는 돌린다. 예외 문구에는 주소 · 키가 섞일 수 있어 종류만 남긴다
            error = type(e).__name__
            break
        answer = out.get("answer") or {}
        steps = trace.steps[seen:]
        turns.append({
            "message": text, "kind": answer.get("kind"), "mode": out.get("mode"),
            "request": {k: (out.get("request") or {}).get(k) for k in ("region", "place", "start_date", "days", "companions", "preferences", "exclusions", "missing", "notes")},
            "missing": answer.get("missing", []), "text": answer.get("text", ""), "notices": answer.get("notices", []),
            "course": _course_view(answer),
            "backup": [{"id": b.get("id"), "title": b.get("title")} for b in answer.get("backup", [])],
            "cafes": [{"id": c.get("id"), "title": c.get("title")} for c in answer.get("cafes", [])],
            "festivals": [{"id": f["id"], "title": f["title"], "event_start": f["event_start"], "event_end": f["event_end"]}
                          for f in (out.get("festivals") or {}).get("items", [])],
            "violations": [{"rule": v.get("rule"), "date": v.get("date"), "slot": v.get("slot")} for v in out.get("violations", [])],
            "removed": len(out.get("removed", [])), "retries": out.get("retries", {}), "grade": out.get("grade", {}),
            "steps": [{"step": s["step"], "kind": s["kind"], "ok": s["ok"], "took_ms": s["took_ms"]} for s in steps],
            "llm_calls": len(usage) - tokens_before,
            "input_tokens": sum(u["input_tokens"] for u in usage[tokens_before:]),
            "output_tokens": sum(u["output_tokens"] for u in usage[tokens_before:]),
            "took_sec": round(time.perf_counter() - t0, 2),
        })
    return {"id": item["id"], "case": item["case"], "split": item["split"], "expect": item["expect"], "turns": turns,
            "error": error, "took_sec": round(time.perf_counter() - started, 2)}


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def run_all(items: list, retriever, providers: list, out_dir: Path, llm=None, say=print) -> dict:
    """모델마다 문항을 차례로 돌려 out_dir/모델.jsonl 에 한 줄씩 쓴다. 설정은 meta.json 에 남긴다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # 왜: 나중에 "어떤 코드 · 어떤 데이터 · 어떤 설정으로 돌린 결과인가"를 되짚을 수 있어야 비교표를 믿을 수 있다. 어디: 실행 기록 머리말.
    # 교안: 2일차 Part3 "회귀 비교표" — 실행 조건을 결과와 함께 남긴다.
    meta = {"started": datetime.now().isoformat(timespec="seconds"), "git": _git_sha(), "places": config.EVAL_COURSE_PLACES,
            "place_count": len(retriever.places), "items": [i["id"] for i in items],
            "models": {p: config.MODELS[p] for p in providers}, "weather": "fixed", "detail": "stored",
            "config": {k: getattr(config, k) for k in ("SEARCH_K", "OVERFETCH", "MAX_LEG_KM_BY_REGION", "MUSEUM_MAX", "MAX_TRIP_DAYS")}}
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {}
    for provider in providers:
        rows = []
        with (out_dir / f"{provider}.jsonl").open("w", encoding="utf-8") as f:
            for item in items:
                row = run_item(item, retriever, llm=llm, provider=provider)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                rows.append(row)
                last = row["turns"][-1] if row["turns"] else {}
                say(f"  {provider} {row['id']} {row['case']} → {last.get('kind') or row['error']} (기대 {item['expect']['kind']}) "
                    f"{row['took_sec']}초 · 토큰 {sum(t['input_tokens'] + t['output_tokens'] for t in row['turns'])}")
        summary[provider] = {"items": len(rows), "errors": sum(1 for r in rows if r["error"]),
                             "kind_match": sum(1 for r in rows if r["turns"] and r["turns"][-1]["kind"] == r["expect"]["kind"]),
                             "took_sec": round(sum(r["took_sec"] for r in rows), 1),
                             "input_tokens": sum(t["input_tokens"] for r in rows for t in r["turns"]),
                             "output_tokens": sum(t["output_tokens"] for r in rows for t in r["turns"])}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["dev", "holdout", "all"])
    parser.add_argument("--ids", default="")
    parser.add_argument("--provider", default=config.LLM_PROVIDER)
    args = parser.parse_args()
    providers = [p.strip() for p in args.provider.split(",") if p.strip()]
    unknown = [p for p in providers if p not in config.MODELS]
    if unknown:
        sys.exit(f"모르는 모델 이름: {unknown}. 가능한 값: {list(config.MODELS)}")
    items = load_set(args.split, [i.strip() for i in args.ids.split(",") if i.strip()])
    if not items:
        sys.exit("돌릴 문항이 없습니다")
    places = ROOT / config.EVAL_COURSE_PLACES
    if not places.exists():
        sys.exit(f"평가용 데이터 사본이 없습니다: {config.EVAL_COURSE_PLACES}")

    from rag.retriever import Retriever
    retriever = Retriever.from_file(places, index_dir=ROOT / config.EVAL_COURSE_INDEX_DIR)
    out_dir = ROOT / config.EVAL_RUNS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"문항 {len(items)}건 · 모델 {providers} · 장소 {len(retriever.places)}곳 → {out_dir.relative_to(ROOT)}")
    summary = run_all(items, retriever, providers, out_dir)
    for provider, s in summary.items():
        print(f"{provider}: 답 종류 일치 {s['kind_match']}/{s['items']} · 오류 {s['errors']} · {s['took_sec']}초 · "
              f"토큰 입력 {s['input_tokens']:,} 출력 {s['output_tokens']:,}")


if __name__ == "__main__":
    main()
