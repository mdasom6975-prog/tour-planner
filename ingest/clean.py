"""목록 · 소개글 · 휴무일 · 무장애 · 반려동물 파일을 장소 한 곳당 한 줄로 합친다. API 를 호출하지 않는다. (PRD 14번 1단계 중 1-6a, A-4)

검색기가 읽을 글(search_text)도 여기서 만든다 (1-6b). 무장애 · 반려동물을 그 글에 넣는 일(A-5)은 여기 없다.
실행:  python -m ingest.clean
"""
import html
import json
import re
from pathlib import Path

import config
from ingest.rest_days import parse_rest

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "places.jsonl"

# 왜: 같은 뜻의 항목이 유형마다 이름이 달라, 뒤 단계가 유형을 몰라도 되게 한 이름으로 맞춘다. 어디: 합칠 때.
# 교안: 4일차 PRD "도시 → 통화 표(코드)" — 규칙을 if 문이 아니라 표로 두면 유형 추가가 한 줄이다.
# 항목 이름은 2026-11-11 받은 948곳의 실제 응답에서 확인했다.
FIELD_MAP = {
    "12": {"rest": "restdate", "hours": "usetime", "contact": "infocenter", "parking": "parking",
           "extra": {"experience": "expguide", "stroller": "chkbabycarriage", "pet": "chkpet"}},
    "14": {"rest": "restdateculture", "hours": "usetimeculture", "contact": "infocenterculture", "parking": "parkingculture",
           "extra": {"fee": "usefee", "parking_fee": "parkingfee", "visit_time": "spendtime"}},
    "15": {"rest": None, "hours": "playtime", "contact": "sponsor1tel", "parking": None,
           "extra": {"event_start": "eventstartdate", "event_end": "eventenddate", "event_place": "eventplace",
                     "program": "program", "fee": "usetimefestival", "host": "sponsor1"}},
    "39": {"rest": "restdatefood", "hours": "opentimefood", "contact": "infocenterfood", "parking": "parkingfood",
           "extra": {"menu_main": "firstmenu", "menu": "treatmenu", "takeout": "packing"}},
}

# 왜: 원본 이름(handicapetc, brailepromotion)은 화면과 LLM이 읽기 어려워 대상별 묶음과 우리말 이름으로 바꾼다. 값은 원문 그대로 둔다. 어디: access 칸.
# 교안: 4일차 PRD "도시 → 통화 표(코드)". 항목 이름은 2026-11-12 받은 1,857곳의 실제 응답에서 확인했다.
ACCESS_MAP = {
    "이동": {"parking": "주차", "route": "접근로", "publictransport": "대중교통", "ticketoffice": "매표소", "promotion": "홍보물",
            "wheelchair": "휠체어", "exit": "출입통로", "elevator": "엘리베이터", "restroom": "화장실", "auditorium": "관람석",
            "room": "객실", "handicapetc": "기타"},
    "시각": {"braileblock": "점자블록", "helpdog": "보조견 동반", "guidehuman": "안내요원", "audioguide": "오디오가이드",
            "bigprint": "큰 활자", "brailepromotion": "점자 홍보물", "guidesystem": "유도 안내", "blindhandicapetc": "기타"},
    "청각": {"signguide": "수어 안내", "videoguide": "자막 영상", "hearingroom": "객실", "hearinghandicapetc": "기타"},
    "영유아": {"stroller": "유아차", "lactationroom": "수유실", "babysparechair": "유아용 의자", "infantsfamilyetc": "기타"},
}
# risk(사고 예방)는 뺀다. 2026-11-12 정제된 곳 중 값이 있는 99곳 모두 allowed(견종)와 같은 문장이었다(원본이 그렇게 온다).
PET_MAP = {"scope": "범위", "allowed": "견종", "required": "필수", "notes": "유의",
           "facilities": "시설", "provided": "비치", "rental": "대여", "for_sale": "판매"}


def _text(value) -> str:
    # 왜: 원문에 섞인 줄바꿈 태그 · 특수문자 표기만 정리하고 내용은 고치지 않는다. 어디: 모든 글 항목.
    # 교안: 2일차 Part4 — 외부 문서는 그대로 믿지 않고 형식을 정리한 뒤 태그로 감싸 넘긴다.
    s = html.unescape(str(value or ""))
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\s*\n\s*", "\n", s).strip()


def _homepage(value) -> str:
    # 왜: 홈페이지 항목은 <a href="..."> 태그째로 와서 주소만 뽑는다. 어디: 화면의 링크.
    # 교안: 2일차 Part1 "형식은 코드로 강제" — 정규식으로 필요한 부분만 꺼내는 규칙 검사와 같은 도구.
    m = re.search(r'href="([^"]+)"', str(value or ""))
    if m:
        return html.unescape(m.group(1))
    plain = _text(value)
    return plain if plain.startswith("http") else ""


def _coord(item: dict):
    # 왜: 좌표는 거리 검증에 쓰이므로 글자가 아닌 숫자여야 하고, 엉뚱한 값은 걸러 표시한다. 어디: lat/lon.
    # 교안: "숫자는 코드가" — 거리 계산에 들어갈 숫자를 코드가 미리 확인한다.
    try:
        lat, lon = float(item.get("mapy")), float(item.get("mapx"))
    except (TypeError, ValueError):
        return None, None
    if not (33 <= lat <= 39 and 124 <= lon <= 132):
        return None, None
    return lat, lon


def _area(addr: str) -> str:
    # 왜: "해운대", "애월" 같은 동네 이름으로 찾을 수 있게 하되 번지 · 도로명 숫자는 잡음이라 뺀다. 어디: 본문 첫 줄.
    # 교안: RAG 실습1 Q3 — BM25 는 글자 일치로 찾으므로 본문에 어떤 낱말을 넣을지가 검색 결과를 정한다.
    tokens = addr.split()
    parts = tokens[:2] + [t for t in tokens[2:4] if re.fullmatch(r"[가-힣]+(읍|면|동|리|가)", t)]
    in_paren = re.search(r"\(([^)]+)\)", addr)
    if in_paren and in_paren.group(1) not in parts:
        parts.append(in_paren.group(1))
    return " ".join(parts)


def build_search_text(place: dict) -> str:
    """검색기(BM25 · 임베딩)가 읽을 글 한 덩어리를 만든다. 장소 한 곳이 문서 한 건이다."""
    # 왜: 소개글이 최대 914자(중앙 340자)라 나눌 만큼 길지 않다. 나누지 않으면 검색 결과 한 건이 곧 장소 한 곳이다.
    # 교안: 3일차 03 가이드북은 긴 문서를 나눴다(청킹). 여기서는 길이를 재 보고 나누지 않기로 했다.
    extra = place["extra"]
    lines = [f"[{place['type']}] {place['title']} ({_area(place['addr'])})"]

    # 왜: "칼국수", "무료", "체험" 같은 조건에 반응하려면 유형별 단서가 본문에 있어야 한다. 어디: 둘째 줄.
    # 교안: RAG 실습1 Q8 실패 사례 분석 — 찾지 못한 이유가 "본문에 그 낱말이 없어서" 인 경우를 줄인다.
    labels = {
        "음식점": [("대표 메뉴", "menu_main"), ("메뉴", "menu")],
        "축제·행사": [("행사 장소", "event_place"), ("프로그램", "program")],
        "문화시설": [("이용요금", "fee")],
        "관광지": [("체험", "experience")],
    }
    hints = [f"{label}: {extra[key]}" for label, key in labels.get(place["type"], []) if extra.get(key)]
    if hints:
        lines.append(". ".join(h.replace("\n", " ") for h in hints))

    # 왜: "휠체어", "수유실", "강아지" 로 찾으려면 그 낱말이 본문에 있어야 한다. 값은 원문 그대로 넣고, 정보가 없으면 줄을 넣지 않는다("정보 없음" 이 검색에 걸리지 않게). 어디: 소개글 앞 (A-5).
    # 교안: RAG 실습1 Q3 · Q8. "화장실 없음" 같은 부정 문장도 들어가므로 그 영향은 3단계 평가에서 잰다.
    flat = lambda s: s.replace("\n", " ")
    if place.get("access"):
        groups = [f"{g}: " + " / ".join(f"{k} {flat(v)}" for k, v in items.items()) for g, items in place["access"].items()]
        lines.append("무장애 — " + " · ".join(groups))
    if place.get("pet"):
        lines.append("반려동물 — " + " / ".join(f"{k} {flat(v)}" for k, v in place["pet"].items()))

    # 왜: 휴무일 · 이용시간 · 행사 기간 · 전화 · 홈페이지는 일부러 넣지 않는다. 날짜와 휴무는 검색이 아니라 코드가 거른다.
    # 교안: "숫자와 사실 판정은 코드가" — 본문에 넣으면 "화요일" 검색에 화요일 휴무인 곳이 걸린다.
    if place["overview"]:
        lines.append(place["overview"].replace("\n", " "))
    return "\n".join(lines)


def _access(row: dict | None) -> dict:
    # 왜: 값이 있는 항목만 남긴다. 빈 사전은 "시설 없음" 이 아니라 "정보 없음" 이다(아직 안 받았거나 관광공사에 내용이 없음). 어디: access 칸.
    # 교안: 2일차 Part1 구조화 출력 — 정해진 이름과 모양. "있음/없음" 판정은 하지 않는다(원문에 좋은 점과 나쁜 점이 섞여 있다).
    data = (row or {}).get("data") or {}
    groups = {g: {label: _text(data.get(src)) for src, label in fields.items() if _text(data.get(src))}
              for g, fields in ACCESS_MAP.items()}
    return {g: v for g, v in groups.items() if v}


def _pet(row: dict | None) -> dict:
    return {label: _text((row or {}).get(src)) for src, label in PET_MAP.items() if _text((row or {}).get(src))}


def _load(name: str) -> dict:
    # 없는 파일은 빈 것으로 본다. 꼭 있어야 하는 파일은 build_places 가 먼저 검사한다.
    if not (RAW_DIR / name).exists():
        return {}
    with (RAW_DIR / name).open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["contentid"]: r for r in rows}


def build_places() -> dict:
    """성공: {"ok": True, "count", "by_type", "bad_coords", "hidden", "showflag_unknown", "access", "pet", "path"} / 실패: {"ok": False, "reason"}"""
    # 왜: 세 파일 중 하나라도 없으면 합칠 수 없다. 어디: 함수 맨 앞의 입력 검사.
    # 교안: 3일차 Part2 "에러도 결과로".
    needed = [f"list_{r}.jsonl" for r in config.REGIONS] + ["detail_common.jsonl", "detail_intro.jsonl"]
    missing = [n for n in needed if not (RAW_DIR / n).exists()]
    if missing:
        return {"ok": False, "reason": f"원본 파일이 없습니다: {missing}"}

    common, intro = _load("detail_common.jsonl"), _load("detail_intro.jsonl")
    # 왜: 무장애 · 반려동물은 없어도 코스를 짤 수 있는 덧붙는 정보라, 파일이 없으면 멈추지 않고 빈 칸으로 둔다. 어디: 입력.
    # 교안: RAG 실습1 Q1 — 문서에 메타데이터를 붙여 두고 뒤에서 거르거나 보여 주는 데 쓴다.
    access, pet = _load("access.jsonl"), _load("pet.jsonl")
    places, by_type, bad_coords = [], {}, 0
    counts = {"access_fetched": 0, "access": 0, "pet": 0}
    flags = {"0": 0, "1": 0, "": 0}

    # 왜: 목록 순서대로 돌면 원본이 같을 때 결과 순서도 항상 같다. 어디: 합치기의 바깥 반복.
    # 교안: RAG 실습1 Q1 — corpus 를 만들 때 순서를 고정해 재현되게 하던 것.
    for region in config.REGIONS:
        # 왜: 표출 여부는 평소 목록에 없고 동기화 목록(1-7a)에만 있다. 파일이 없거나 그 장소가 없으면 빈 값("모름")으로 두고 숨기지 않는다. 어디: 지역마다 한 번.
        # 교안: 3일차 Part2 "에러도 결과로" — 동기화를 못 받은 날에도 정제가 멈추거나 검색이 통째로 비지 않게 한다.
        sync_name = f"sync_{region}.jsonl"
        sync = _load(sync_name) if (RAW_DIR / sync_name).exists() else {}
        for cid, item in _load(f"list_{region}.jsonl").items():
            # 소개글과 휴무일이 둘 다 있는 곳만 넣는다. 수집이 진행되면 다시 실행해 늘린다.
            if cid not in common or cid not in intro:
                continue
            type_id = item["contenttypeid"]
            fmap = FIELD_MAP.get(type_id)
            if fmap is None:
                continue
            c, i = common[cid]["data"] or {}, intro[cid]["data"] or {}
            lat, lon = _coord(item)
            bad_coords += lat is None
            modified = item.get("modifiedtime", "")

            # 왜: 뒤 단계(검색 · 도구 · 검증 · 화면)가 유형과 상관없이 같은 이름으로 읽게 한다. 어디: 저장하는 한 줄.
            # 교안: 2일차 Part1 구조화 출력 — 정해진 이름과 모양으로 받으면 다음 코드가 단순해진다.
            places.append({
                "id": cid,
                "region": region,
                "type": config.DETAIL_TYPES[type_id],
                "title": _text(item.get("title")),
                "addr": _text(f"{item.get('addr1', '')} {item.get('addr2', '')}"),
                "lat": lat,
                "lon": lon,
                "image": item.get("firstimage", ""),
                "modified": f"{modified[:4]}-{modified[4:6]}-{modified[6:8]}" if len(modified) >= 8 else "",
                "overview": _text(c.get("overview")),
                "homepage": _homepage(c.get("homepage")),
                "rest_text": _text(i.get(fmap["rest"])) if fmap["rest"] else "",
                "hours_text": _text(i.get(fmap["hours"])) if fmap["hours"] else "",
                "contact": _text(i.get(fmap["contact"])) if fmap["contact"] else "",
                "parking": _text(i.get(fmap["parking"])) if fmap["parking"] else "",
                "extra": {k: _text(i.get(src)) for k, src in fmap["extra"].items() if _text(i.get(src))},
                "showflag": sync.get(cid, {}).get("showflag") or "",   # "1" 표출 · "0" 비표출 · "" 모름
                "access": _access(access.get(cid)),   # {"이동": {"주차": "…"}, "시각": {…}, …} · 빈 사전은 정보 없음
                "pet": _pet(pet.get(cid)),            # {"범위": "…", "견종": "…", …} · 빈 사전은 정보 없음
            })
            counts["access_fetched"] += cid in access
            counts["access"] += bool(places[-1]["access"])
            counts["pet"] += bool(places[-1]["pet"])
            flags[places[-1]["showflag"]] = flags.get(places[-1]["showflag"], 0) + 1
            places[-1]["search_text"] = build_search_text(places[-1])
            # 왜: 검증기가 "이 요일에 가도 되는가" 를 코드로 판정하려면 문장이 아닌 값이 필요하다. 어디: 6단계 검증기의 입력.
            # 교안: "숫자와 사실 판정은 코드가". 축제는 휴무일 대신 행사 기간으로 검증하므로 해당 없음으로 둔다.
            if fmap["rest"]:
                places[-1].update(parse_rest(places[-1]["rest_text"]))
            else:
                places[-1].update({"rest_status": "not_applicable", "rest_weekdays": [], "rest_note": False})
            by_type[config.DETAIL_TYPES[type_id]] = by_type.get(config.DETAIL_TYPES[type_id], 0) + 1

    # 왜: 원본에서 계산해 통째로 다시 쓰면 몇 번 실행해도 결과가 같다. 어디: 저장.
    # 교안: RAG 실습1 Q1 — 한 줄에 한 건인 jsonl.
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for p in places:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    return {"ok": True, "count": len(places), "by_type": by_type, "bad_coords": bad_coords,
            "hidden": flags["0"], "showflag_unknown": flags[""], **counts, "path": str(OUT_PATH)}


if __name__ == "__main__":
    print(build_places())
