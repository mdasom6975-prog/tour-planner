"""TourAPI 를 한 번 호출하는 함수 call() 하나만 있는 파일. (PRD 14번 1단계 중 1-1)

목록 수집 · 페이지 넘기기 · 저장은 여기 없다. 뒤 조각에서 이 함수를 불러 쓴다.
"""
import json
import os
from datetime import date
from pathlib import Path

import requests

import config
from harness.logs import get_logger

log = get_logger("ingest.tourapi")

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


def _fail(usage_key: str, reason: str, level: str = "warning", **more) -> dict:
    # 왜: 실패를 결과로 돌려주면서 같은 내용을 로그에도 남긴다. 언제 어떤 오퍼레이션이 왜 실패했는지 나중에 볼 수 있다. 어디: call 의 모든 실패 경로.
    # 교안: 직접 대응 없음 (L-2). 요청 주소는 적지 않는다 — 키가 주소에 붙어 있다. 로그 장치도 키 모양을 한 번 더 가린다.
    getattr(log, level)("%s 실패: %s", usage_key, reason)
    return {"ok": False, **more, "reason": reason}


def call(operation: str, params: dict | None = None, today: str | None = None, service: str | None = None, margin: int | None = None) -> dict:
    """TourAPI 오퍼레이션을 한 번 호출한다.

    성공: {"ok": True, "items": [...], "total": 전체 건수}
    실패: {"ok": False, "reason": "사유"}   ← 예외를 던지지 않는다
    """
    # 왜: 날짜를 인자로 받으면 테스트에서 "내일"을 흉내 낼 수 있다. 어디: 한도 초기화 검증.
    # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 외부 의존을 인자로 받는 원칙.
    today = today or date.today().isoformat()

    # 왜: 무장애 여행 정보는 별도 서비스(KorWithService2)다. 같은 이름의 오퍼레이션이 있고 한도도 따로라 기록을 나눈다. 어디: 주소와 기록의 이름.
    # 교안: 3일차 Part2 "도구는 한 가지 일만" 을 지키면서 인자로 대상을 바꾼다. 기본값은 기존 서비스라 기존 호출은 그대로다.
    root, default_service = config.TOURAPI_BASE.rsplit("/", 1)
    service = service or default_service
    # 서비스마다 주소가 따로 정해져 있으면 그것을 쓰고, 없으면 기본 주소의 윗 경로에 서비스 이름을 붙인다(config.TOURAPI_SERVICE_BASES).
    base = config.TOURAPI_BASE if service == default_service else config.TOURAPI_SERVICE_BASES.get(service) or f"{root}/{service}"
    usage_key = operation if service == default_service else f"{service}/{operation}"

    # 왜: 키가 없으면 호출해 봐야 실패하므로 한도를 쓰기 전에 걸러 낸다. 어디: 함수 맨 앞.
    # 교안: 2일차 Part4 "비밀은 .env 에만" — 키는 코드 · 지시문 · 로그에 쓰지 않는다.
    key = os.getenv("TOURAPI_KEY")
    if not key:
        return _fail(usage_key, ".env 에 TOURAPI_KEY 가 없습니다", "error")

    # 왜: 한도를 넘기면 그날 수집이 전부 막히므로 보내기 전에 코드가 막는다. 어디: 요청 직전.
    # 교안: 3일차 Part4 "안전장치는 프롬프트가 아니라 코드에" / day3_tools.run_agent 의 max_rounds.
    # 한도는 오퍼레이션마다 따로 1,000건이다. 서버가 응답 머리말(X-RateLimit-Remaining)로 남은 수를 알려 준다
    # (2026-11-11 세 오퍼레이션에서 서버 값과 우리 기록이 일치하는 것을 확인).
    # margin: 한도 직전에 남겨 둘 수. 수집은 기본값(50)을 남기고, 실시간 재확인(get_place_detail)은 그 여유분 안에서 더 작은 값으로 부른다.
    margin = config.TOURAPI_SAFETY_MARGIN if margin is None else margin
    usage = _load_usage(today)
    used = usage["counts"].get(usage_key, 0)
    server_remaining = usage.get("server_remaining", {}).get(usage_key)

    # 왜: 우리 기록은 이 함수를 거친 호출만 센다. 서버가 알려 준 값이 있으면 그것이 정답이다. 어디: 멈출지 판단.
    # 교안: 1일차 03 "환각" 과 같은 교훈 — 기억(우리 기록)보다 근거(서버 값)를 우선한다.
    if server_remaining is not None:
        blocked = server_remaining <= margin
        detail = f"서버가 알려 준 남은 수 {server_remaining}, 여유분 {margin}"
    else:
        # 그날 첫 호출 전이라 서버 값이 아직 없을 때만 우리 기록으로 판단한다.
        budget = config.TOURAPI_DAILY_LIMIT - margin
        blocked = used >= budget
        detail = f"우리 기록 {used}/{budget}"
    if blocked:
        # "limit": True 는 부르는 쪽이 "실패" 와 "오늘 분량 끝" 을 글자가 아닌 값으로 구분하게 해 준다.
        return _fail(usage_key, f"오늘 {usage_key} 호출 한도 도달 ({detail}). 내일 이어서 받습니다", "info", limit=True)

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
    usage["counts"][usage_key] = usage["counts"].get(usage_key, 0) + 1
    _save_usage(usage)

    # 왜: 네트워크 오류로 수집 전체가 죽지 않게 오류를 결과로 바꾼다. 어디: 실제 HTTP 호출.
    # 교안: 3일차 Part2 도구 설계 5조건 "에러도 결과로" / get_weather 의 except → {'error': ...}.
    try:
        r = requests.get(f"{base}/{operation}", params=query, timeout=15)
    except requests.RequestException as e:
        return _fail(usage_key, f"연결 실패: {type(e).__name__}")

    # 왜: 서버가 센 남은 수를 받아 적어 두면 다음 호출의 판단 근거가 되고, 파일만 열어도 남은 한도를 알 수 있다. 어디: 응답 직후.
    # 교안: 12-1 실행 기록 — 추측하지 않고 실제로 관측한 값을 남긴다. 머리말이 없으면 우리 기록 방식으로 남는다.
    limit_h, remain_h = r.headers.get("X-RateLimit-Limit"), r.headers.get("X-RateLimit-Remaining")
    if remain_h is not None and remain_h.isdigit():
        usage.setdefault("server_remaining", {})[usage_key] = int(remain_h)
        # 서버가 센 사용량과 우리 기록이 다르면 다른 경로의 호출이 있었다는 뜻이다. 차이를 적어 둔다.
        if limit_h is not None and limit_h.isdigit():
            drift = (int(limit_h) - int(remain_h)) - usage["counts"][usage_key]
            usage.setdefault("drift", {})[usage_key] = drift
        _save_usage(usage)

    # 왜: TourAPI 는 키 · 한도 · 주소 오류일 때 JSON 대신 XML 이나 일반 글자로 답한다. 어디: 응답 해석 전.
    # 교안: 2일차 Part4 다층 방어의 "출력 검증"과 같은 생각 — 받은 것을 쓰기 전에 코드로 형식 확인.
    text = r.text.strip()
    if not text.startswith("{"):
        return _fail(usage_key, f"HTTP {r.status_code}, JSON 이 아닌 응답: {text[:150]}")

    # 왜: HTTP 200 이어도 본문의 resultCode 가 실패일 수 있다. 어디: 본문 머리말 검사.
    # 교안: 3일차 get_exchange_rate — 응답은 왔지만 값이 없을 때 {'error': ...} 를 돌려주던 처리.
    data = r.json()
    if "response" not in data:
        return _fail(usage_key, f"HTTP {r.status_code}, 예상과 다른 응답: {text[:150]}")
    response = data["response"]
    header = response.get("header", {})
    if header.get("resultCode") != "0000":
        return _fail(usage_key, f"resultCode={header.get('resultCode')} {header.get('resultMsg')}")

    # 왜: 결과가 0건이면 items 가 빈 문자열, 1건이면 dict 로 오기도 해서 항상 list 로 맞춘다. 어디: 반환 직전.
    # 교안: 직접 대응하는 부분 없음 (TourAPI 응답의 특성). 3일차 도구들이 항상 dict 를 돌려주던 것과 같은 취지.
    body = response.get("body", {})
    items = (body.get("items") or {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return {"ok": True, "items": items, "total": body.get("totalCount", len(items))}
