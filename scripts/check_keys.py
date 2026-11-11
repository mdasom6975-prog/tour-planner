"""키 3개가 동작하는지 확인한다. 키 값은 어디에도 출력하지 않는다.

실행:  python scripts/check_keys.py
- TourAPI : 지역코드 목록 1회 조회 (하루 한도에서 1건 사용)
- Claude  : 모델 정보 조회 (토큰 비용 없음)
- OpenAI  : 모델 정보 조회 (토큰 비용 없음)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config


def check_tourapi():
    key = os.getenv("TOURAPI_KEY")
    if not key:
        return False, ".env 에 TOURAPI_KEY 가 없습니다"
    try:
        r = requests.get(
            f"{config.TOURAPI_BASE}/areaCode2",
            params={
                "serviceKey": key,
                "MobileOS": "ETC",
                "MobileApp": "tour-planner",
                "_type": "json",
                "numOfRows": 20,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"연결 실패: {type(e).__name__}"
    text = r.text.strip()
    # 키 오류일 때는 _type=json 이어도 XML 로 답한다.
    if not text.startswith("{"):
        for code in ("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"):
            if code in text:
                return False, f"{code} (방금 승인됐다면 최대 1시간 뒤 다시 시도)"
        return False, f"HTTP {r.status_code}, JSON 이 아닌 응답: {text[:120]}"
    body = r.json().get("response", {})
    header = body.get("header", {})
    if header.get("resultCode") != "0000":
        return False, f"resultCode={header.get('resultCode')} {header.get('resultMsg')}"
    items = body.get("body", {}).get("items") or {}
    names = [i.get("name") for i in items.get("item", [])]
    return True, f"지역코드 {len(names)}건 ({', '.join(names[:5])} …)"


def check_claude():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False, ".env 에 ANTHROPIC_API_KEY 가 없습니다"
    import anthropic

    model = config.MODELS["claude"].split(":", 1)[1]
    try:
        info = anthropic.Anthropic().models.retrieve(model)
    except anthropic.AuthenticationError:
        return False, "키가 올바르지 않습니다"
    except anthropic.NotFoundError:
        return False, f"모델 {model} 을 찾을 수 없습니다"
    except anthropic.APIStatusError as e:
        return False, f"HTTP {e.status_code}"
    except anthropic.APIConnectionError:
        return False, "연결 실패"
    return True, f"{info.id} 사용 가능"


def check_openai():
    if not os.getenv("OPENAI_API_KEY"):
        return False, ".env 에 OPENAI_API_KEY 가 없습니다"
    import openai

    model = config.MODELS["openai"].split(":", 1)[1]
    try:
        info = openai.OpenAI().models.retrieve(model)
    except openai.AuthenticationError:
        return False, "키가 올바르지 않습니다"
    except openai.NotFoundError:
        return False, f"모델 {model} 을 찾을 수 없습니다"
    except openai.APIStatusError as e:
        return False, f"HTTP {e.status_code}"
    except openai.APIConnectionError:
        return False, "연결 실패"
    return True, f"{info.id} 사용 가능"


def main():
    checks = [("TourAPI", check_tourapi), ("Claude", check_claude), ("OpenAI", check_openai)]
    failed = 0
    for name, fn in checks:
        ok, msg = fn()
        failed += not ok
        print(f"[{'통과' if ok else '실패'}] {name:8s} {msg}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
