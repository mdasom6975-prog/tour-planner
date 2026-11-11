"""TourAPI 를 한 번 호출하는 함수 call() 하나만 있는 파일. (PRD 14번 1단계 중 1-1)

목록 수집 · 페이지 넘기기 · 저장은 여기 없다. 뒤 조각에서 이 함수를 불러 쓴다.
"""
import json
import os
from datetime import date
from pathlib import Path

import requests

import config

# 왜: 오늘 몇 번 불렀는지 프로그램을 껐다 켜도 기억하려고 파일에 적는다. 어디: 한도 검사.
# 교안: 3일차 04 일정비서가 data/calendar.json 에 상태를 저장하던 방식(_load_cal/_save_cal).
USAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "_usage.json"


def _load_usage(today: str) -> dict:
    # 왜: 날짜가 바뀌면 한도가 초기화되므로 오늘 기록만 쓴다. 어디: call() 시작과 끝.
    # 교안: 3일차 day3_tools._load_cal — 파일이 없으면 빈 값으로 시작하는 패턴.
    if USAGE_PATH.exists():
        usage = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        if usage.get("date") == today:
            return usage
    return {"date": today, "counts": {}}


def _save_usage(usage: dict) -> None:
    # 왜: 호출할 때마다 바로 적어야 중간에 멈춰도 횟수가 맞는다. 어디: 요청을 보낸 직후.
    # 교안: 3일차 day3_tools._save_cal — ensure_ascii=False 로 한글을 그대로 저장.
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USAGE_PATH.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")


def call(operation: str, params: dict | None = None, today: str | None = None) -> dict:
    """TourAPI 오퍼레이션을 한 번 호출한다.

    성공: {"ok": True, "items": [...], "total": 전체 건수}
    실패: {"ok": False, "reason": "사유"}   ← 예외를 던지지 않는다
    """
    # 왜: 날짜를 인자로 받으면 테스트에서 "내일"을 흉내 낼 수 있다. 어디: 한도 초기화 검증.
    # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 외부 의존을 인자로 받는 원칙.
    today = today or date.today().isoformat()

    # 왜: 키가 없으면 호출해 봐야 실패하므로 한도를 쓰기 전에 걸러 낸다. 어디: 함수 맨 앞.
    # 교안: 2일차 Part4 "비밀은 .env 에만" — 키는 코드 · 지시문 · 로그에 쓰지 않는다.
    key = os.getenv("TOURAPI_KEY")
    if not key:
        return {"ok": False, "reason": ".env 에 TOURAPI_KEY 가 없습니다"}

    # 왜: 한도를 넘기면 그날 수집이 전부 막히므로 보내기 전에 코드가 막는다. 어디: 요청 직전.
    # 교안: 3일차 Part4 "안전장치는 프롬프트가 아니라 코드에" / day3_tools.run_agent 의 max_rounds.
    # 한도는 오퍼레이션마다 따로 센다 (2026-11-11 활용신청 화면에서 사용자가 확인).
    usage = _load_usage(today)
    used = usage["counts"].get(operation, 0)
    budget = config.TOURAPI_DAILY_LIMIT - config.TOURAPI_SAFETY_MARGIN
    if used >= budget:
        # "limit": True 는 부르는 쪽이 "실패" 와 "오늘 분량 끝" 을 글자가 아닌 값으로 구분하게 해 준다.
        return {"ok": False, "limit": True, "reason": f"오늘 {operation} 호출 한도 도달 ({used}/{budget}). 내일 이어서 받습니다"}

    # 왜: 매번 똑같이 붙는 값은 함수가 붙여야 호출하는 쪽이 조건만 신경 쓴다. 어디: 모든 오퍼레이션.
    # 교안: 3일차 day3_tools.get_weather — requests.get(url, params={...}) 로 조건을 넘기던 형태.
    query = {
        "serviceKey": key,
        "MobileOS": "ETC",
        "MobileApp": "tour-planner",
        "_type": "json",
        **(params or {}),
    }

    # 왜: 서버는 실패한 요청도 한 건으로 셀 수 있어 결과와 상관없이 먼저 센다. 어디: 요청 직전.
    # 교안: 2일차 Part3 "속도 · 비용은 넘으면 안 되는 선" — 쓴 양을 기록해야 선을 지킬 수 있다.
    usage["counts"][operation] = usage["counts"].get(operation, 0) + 1
    _save_usage(usage)

    # 왜: 네트워크 오류로 수집 전체가 죽지 않게 오류를 결과로 바꾼다. 어디: 실제 HTTP 호출.
    # 교안: 3일차 Part2 도구 설계 5조건 "에러도 결과로" / get_weather 의 except → {'error': ...}.
    try:
        r = requests.get(f"{config.TOURAPI_BASE}/{operation}", params=query, timeout=15)
    except requests.RequestException as e:
        return {"ok": False, "reason": f"연결 실패: {type(e).__name__}"}

    # 왜: TourAPI 는 키 · 한도 · 주소 오류일 때 JSON 대신 XML 이나 일반 글자로 답한다. 어디: 응답 해석 전.
    # 교안: 2일차 Part4 다층 방어의 "출력 검증"과 같은 생각 — 받은 것을 쓰기 전에 코드로 형식 확인.
    text = r.text.strip()
    if not text.startswith("{"):
        return {"ok": False, "reason": f"HTTP {r.status_code}, JSON 이 아닌 응답: {text[:150]}"}

    # 왜: HTTP 200 이어도 본문의 resultCode 가 실패일 수 있다. 어디: 본문 머리말 검사.
    # 교안: 3일차 get_exchange_rate — 응답은 왔지만 값이 없을 때 {'error': ...} 를 돌려주던 처리.
    data = r.json()
    if "response" not in data:
        return {"ok": False, "reason": f"HTTP {r.status_code}, 예상과 다른 응답: {text[:150]}"}
    response = data["response"]
    header = response.get("header", {})
    if header.get("resultCode") != "0000":
        return {"ok": False, "reason": f"resultCode={header.get('resultCode')} {header.get('resultMsg')}"}

    # 왜: 결과가 0건이면 items 가 빈 문자열, 1건이면 dict 로 오기도 해서 항상 list 로 맞춘다. 어디: 반환 직전.
    # 교안: 직접 대응하는 부분 없음 (TourAPI 응답의 특성). 3일차 도구들이 항상 dict 를 돌려주던 것과 같은 취지.
    body = response.get("body", {})
    items = (body.get("items") or {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return {"ok": True, "items": items, "total": body.get("totalCount", len(items))}
