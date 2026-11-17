"""그래프 결과를 화면 · 내려받기 문서에 쓸 모양으로 바꾼다. Streamlit 을 모른다. (14번 7-1 ~ 7-3)

사실(이름 · 주소 · 거리 · 날짜 · 휴무)은 respond 가 만든 값을 그대로 옮기고 여기서 새로 판정하지 않는다.
관광공사 소개글은 고치지 않고 앞부분만 발췌한다(저작권 정책, PRD 11번).
"""
import html
import math
import json
from pathlib import Path
from urllib.parse import quote

import config

import config

POLICY_URL = "https://api.visitkorea.or.kr/#/useServiceGuide/2"
CREDIT = "출처 : ⓒ한국관광공사"
DAY_COLORS = ["#d9480f", "#1971c2", "#2f9e44"]   # 여행일 순서대로 선 · 핀 색 (config.MAX_TRIP_DAYS = 3)


def excerpt(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def map_link(place: dict) -> str:
    # 왜: 이름으로 검색하면 같은 이름이 여러 곳 나오고 축제는 아예 안 나온다. 가진 좌표로 한 곳을 바로 찍는다. 어디: 지도 링크.
    # 교안: 직접 대응 없음. 설계 원칙 "사실은 코드가" — 위치를 지도 검색에 맡기지 않고 받은 좌표를 그대로 쓴다.
    name = quote(str(place.get("title", "")).replace(",", " "))   # 쉼표는 이름 · 위도 · 경도를 나누는 글자라 이름에서 뺀다
    return f"https://map.kakao.com/link/map/{name},{place.get('lat')},{place.get('lon')}"


def shop_link(place: dict):
    # 좌표 핀에는 영업시간 · 후기가 안 뜬다. 음식점만 "주소 + 이름" 검색 링크를 하나 더 둔다(주소 뒤 괄호는 검색을 흐려서 뗀다).
    if place.get("type") != "음식점":
        return None
    road = str(place.get("addr", "")).split("(")[0].strip()
    query = road if place.get("title", "") in road else f"{road} {place.get('title', '')}"
    return "https://map.kakao.com/link/search/" + quote(query)


def load_kakao_ids(path: Path) -> dict:
    # 왜: 3단계에서 찾아 둔 카카오 장소 ID 를 {contentid: place_id} 로 읽는다. 어디: 링크 결정 입력.
    # 교안: 3일차 04 일정비서가 data/calendar.json 을 읽던 방식 — 파일이 없으면 빈 값(옛 링크로 돌아간다).
    if not Path(path).exists():
        return {}
    with Path(path).open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["contentid"]: r["place_id"] for r in rows if r.get("place_id")}


def place_links(place: dict, kakao_ids: dict | None = None) -> list:
    """[(글자, 주소)]. 장소 ID 가 있으면 카카오 장소 페이지 하나(정보+위치), 없으면 기존 지도 · 가게 정보 링크."""
    # 왜: 장소 페이지는 가게 정보와 정확한 위치를 함께 보여 준다. ID 가 없으면 지금 링크를 그대로 둔다. 어디: 카드 · 내려받기 문서.
    # 교안: 직접 대응 없음. 설계 원칙 "사실은 코드가" — ID 는 좌표 · 이름 일치로 코드가 정한 값만 쓴다.
    pid = (kakao_ids or {}).get(place.get("id"))
    if pid:
        return [("카카오맵에서 보기", config.KAKAO_PLACE_PAGE_URL + str(pid))]
    links = [("지도에서 보기", map_link(place))]
    if shop_link(place):
        links.append(("가게 정보", shop_link(place)))
    return links


def weather_line(w: dict | None) -> str:
    if not w or not w.get("available"):
        return "날씨 정보를 가져오지 못했습니다"
    kind = "비 예보" if w.get("rainy") else "눈 예보" if w.get("snowy") else "비·눈 예보 없음"
    return f"최저 {w['temp_min']:g}~최고 {w['temp_max']:g}℃ · 강수확률 {w['rain_prob']:g}% · {kind}"


def rain_note(w: dict | None, rain_reason: str) -> str:
    """비 · 눈 오는 날이고 모델이 이유를 적었으면 그 날 아래에 보일 문장을 돌려준다. 아니면 빈 문자열."""
    # 왜: "비 오는 날은 실내 위주"라는 분기가 화면에서는 날씨 줄의 '비 예보' 한 단어로만 보여, 왜 이 장소들인지 알기 어려웠다(2026-11-17 화면 확인). 어디: 날짜별 날씨 줄 아래.
    # 교안: PRD F3 날씨 분기. 문장은 모델이 쓰고(rain_reason), 비 · 눈 판정은 코드가 한다.
    return f"비·눈 예보로 실내 위주로 짰습니다. {rain_reason}" if w and w.get("indoor") and rain_reason else ""


def weather_by_date(state: dict) -> dict:
    return {d["date"]: d for d in (state.get("weather") or {}).get("days", [])}


def summary_line(state: dict) -> str:
    """결과 맨 위 요약 한 줄: 지역 · 기간 · 동행 · 취향."""
    req, ans = state.get("request") or {}, state.get("answer") or {}
    dates = [d["date"] for d in ans.get("days", [])]
    where = " ".join(x for x in (req.get("region"), req.get("place") if req.get("place") != req.get("region") else None) if x)
    when = f"{dates[0]} ~ {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else "")
    parts = [where, when, req.get("companions") or "", ", ".join(req.get("preferences") or [])]
    return " · ".join(p for p in parts if p)


def route_by_day(answer: dict) -> list:
    """[(날짜, [{n, slot, title, lat, lon}])]. 좌표가 없는 장소는 지도에서 뺀다."""
    out = []
    for d in answer.get("days", []):
        pts = [{"n": i, "slot": s["slot"], "title": s["title"], "lat": s["lat"], "lon": s["lon"]}
               for i, s in enumerate(d["slots"], 1) if s.get("lat") is not None and s.get("lon") is not None]
        out.append((d["date"], pts))
    return out


def map_view(routes: list) -> tuple | None:
    """모든 핀이 한 화면에 들어오는 (중심 위도, 중심 경도, 확대 단계). 핀이 없으면 None."""
    # 왜: folium 의 fit_bounds 는 지도 칸 크기를 알기 전에 계산돼 엉뚱한 곳(산 속)으로 확대됐다(2026-11-13 화면 확인). 코드가 중심과 확대를 직접 정한다. 어디: 지도 시작 위치.
    # 교안: 직접 대응 없음. 지도 폭 약 500px 에 핀 범위가 들어오도록 한 계산: 확대 단계 = log2(560 / 위경도 범위).
    pts = [(p["lat"], p["lon"]) for _, day in routes for p in day]
    if not pts:
        return None
    lats, lons = [a for a, _ in pts], [b for _, b in pts]
    lat = (min(lats) + max(lats)) / 2
    span = max(max(lats) - min(lats), (max(lons) - min(lons)) * math.cos(math.radians(lat)), 0.005)
    return lat, (min(lons) + max(lons)) / 2, max(7, min(15, int(math.log2(560 / span))))


def export_markdown(state: dict, places: dict, as_of: str, kakao_ids: dict | None = None) -> str:
    """코스를 마크다운 문서로. 출처 문구와 저작권 정책 링크를 붙인다(PRD F4)."""
    ans, weather = state.get("answer") or {}, weather_by_date(state)
    lines = ["# 어디갈래 여행 코스", "", summary_line(state), ""]
    for d in ans.get("days", []):
        lines += [f"## {d['date']}", "", f"날씨: {weather_line(weather.get(d['date']))}", ""]
        for s in d["slots"]:
            place = places.get(s["id"], {})
            lines.append(f"### {s['slot']} — {s['title']} ({s['type']})")
            lines.append(f"- 고른 이유: {s['reason']}")
            lines.append(f"- 주소: {s['addr']}" + (f" · 직전 장소에서 직선 약 {s['leg_km']}km" if s.get("leg_km") is not None else ""))
            if s.get("facts"):
                lines.append("- " + " · ".join(s["facts"]))
            for name, items in s.get("access", []):
                lines.append(f"  - 무장애 — {name}: " + " / ".join(items))
            if place.get("overview"):
                lines.append(f"- 소개(관광공사 원문 발췌): {excerpt(place['overview'])}")
            first = place_links(place, kakao_ids)[0] if place.get("id") in (kakao_ids or {}) else ("지도에서 보기", map_link(place or s))
            lines.append(f"- [{first[0]}]({first[1]})" + (f" · 정보 기준일 {place['modified']}" if place.get("modified") else ""))
            lines.append("")
    if ans.get("cafes"):
        lines += ["## 근처 카페 추천", ""]
        for b in ans["cafes"]:
            lines += [f"- {b['title']} — {b['reason']} · 주소: {b['addr']}" + (f" · {' · '.join(b['facts'])}" if b.get("facts") else "")]
        lines.append("")
    lines += ["## 비나 눈이 오면 (부가 코스)", ""]
    for b in ans.get("backup", []) or []:
        lines += [f"- {b['title']} ({b['type']}) — {b['reason']} · 주소: {b['addr']}"]
    if not ans.get("backup"):
        lines.append("- 이 조건에서 실내 후보를 찾지 못했습니다.")
    if ans.get("notices"):
        lines += ["", "## 알림", ""] + [f"- {n}" for n in ans["notices"]]
    src = (state.get("weather") or {}).get("source")
    lines += ["", "---", f"{CREDIT} · [저작권 정책 안내]({POLICY_URL})" + (f" · 날씨: {src}" if src else "") + f" · 데이터 기준일 {as_of}"]
    return "\n".join(lines) + "\n"


# --- 축제 · 장기 행사 갤러리 -------------------------------------------------
def _ymd(text: str) -> str:
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(str(text)) == 8 else str(text or "")


def festival_cards(festivals: dict, places: dict) -> list:
    """State 의 festivals → 갤러리 카드 목록. 기간 안 축제를 먼저, 상설 · 장기 행사를 뒤에 둔다. 사진 · 소개 · 홈페이지는 저장된 장소에서 가져온다."""
    # 왜: 갤러리는 "보여 주기만" 한다. 날짜 판정은 search_festivals 가 한 값을 옮기고, 사진 · 원문은 저장분 그대로 쓴다. 어디: 화면 직전.
    # 교안: PRD 8번 "LLM 은 받은 장소 정보를 옮겨 적기만" — 여기에는 LLM 이 쓰는 문장이 없다.
    cards = []
    for group, label in (("items", "축제"), ("long_running", "상설 · 장기 행사")):
        for f in (festivals or {}).get(group, []):
            p = places.get(f["id"], {})
            extra = p.get("extra") or {}
            home = str(p.get("homepage") or "")
            cards.append({
                "id": f["id"], "title": f.get("title", ""), "label": label, "image": p.get("image") or "",
                "period": f"{f.get('event_start', '')} ~ {f.get('event_end', '')}", "days_in_trip": f.get("days_in_trip", []),
                "place": f.get("event_place") or "", "addr": f.get("addr") or "", "fee": extra.get("fee", ""), "host": extra.get("host", ""),
                "overview": excerpt(p.get("overview") or f.get("snippet", ""), 220), "program": excerpt(extra.get("program", ""), 160),
                "homepage": home if home.startswith(("http://", "https://")) else "",
                "map": map_link(f), "modified": p.get("modified") or f.get("modified") or "",
            })
    return cards[:config.GALLERY_MAX]


GALLERY_CSS = """
body{margin:0;font-family:-apple-system,'Noto Sans KR',sans-serif;color:#222;background:transparent}
.row{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 12px;scroll-snap-type:x proximity}
.card{flex:0 0 190px;scroll-snap-align:start;border:2px solid #8885;border-radius:10px;background:#8881;padding:0;cursor:pointer;text-align:left;color:inherit;font:inherit}
.card.on{border-color:#d9480f}
.card .img{height:130px;display:flex;align-items:center;justify-content:center;background:#8882;border-radius:8px 8px 0 0}
.card img{max-width:100%;max-height:100%;object-fit:contain}
.card .t{padding:8px 10px;font-size:13px;line-height:1.35}
.card .t b{display:block;margin-bottom:2px}
.tag{font-size:11px;color:#d9480f}
#panel{border:1px solid #8885;border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.55;display:none}
#panel h4{margin:0 0 6px;font-size:15px}
#panel a{color:#1971c2}
.hint{font-size:12px;color:#888;margin:2px 0 6px}
@media (prefers-color-scheme: dark){body{color:#eee}#panel a{color:#74c0fc}}
"""

GALLERY_JS = """
var cards=document.querySelectorAll('.card'),panel=document.getElementById('panel');
function fit(){try{var h=(document.documentElement.scrollHeight+6)+'px',f=window.frameElement;f.style.height=h;f.parentElement.style.height=h}catch(e){}}
fit();window.addEventListener('load',fit);
cards.forEach(function(c){c.addEventListener('click',function(){
  var open=c.classList.contains('on');
  cards.forEach(function(x){x.classList.remove('on')});
  if(open){panel.style.display='none';fit();return}
  c.classList.add('on');
  panel.innerHTML=document.getElementById('d-'+c.dataset.k).innerHTML;
  panel.style.display='block';fit();
})});
"""


def gallery_html(cards: list) -> str:
    """가로로 넘기는 카드 한 줄 + 누르면 아래에 정보가 펼쳐지는 HTML 한 덩어리. 모든 글자는 이스케이프한다(소개글이 태그를 품어도 실행되지 않는다)."""
    # 왜: 사진은 자르지 않고 전체를 보인다(변경 금지 유형이 71%, PRD 11번). 줄 수가 많아도 한 줄로 넘기게 하고 정보는 누를 때만 보인다. 어디: 축제 갤러리.
    # 교안: 직접 대응 없음(2026-11-13 요청). 외부 문장을 HTML 에 넣으므로 html.escape 가 기본 방어선이다.
    e = html.escape
    row, details = [], []
    for k, c in enumerate(cards):
        img = f'<img src="{e(c["image"], quote=True)}" alt="{e(c["title"])}">' if c["image"] else '<span class="hint">사진 없음</span>'
        row.append(f'<button type="button" class="card" data-k="{k}"><div class="img">{img}</div>'
                   f'<div class="t"><span class="tag">{e(c["label"])}</span><b>{e(c["title"])}</b>{e(c["period"])}</div></button>')
        lines = [f'<h4>{e(c["title"])} <span class="tag">{e(c["label"])}</span></h4>', f'기간: {e(c["period"])}']
        if c["days_in_trip"]:
            lines.append("여행 중 겹치는 날: " + e(", ".join(c["days_in_trip"])))
        for name, key in (("장소", "place"), ("주소", "addr"), ("요금", "fee"), ("주최", "host")):
            if c[key]:
                lines.append(f"{name}: {e(c[key])}")
        if c["program"]:
            lines.append(f"프로그램: {e(c['program'])}")
        if c["overview"]:
            lines.append(f"소개(관광공사 원문 발췌): {e(c['overview'])}")
        links = [f'<a href="{e(c["map"], quote=True)}" target="_blank" rel="noopener">지도에서 보기</a>']
        if c["homepage"]:
            links.append(f'<a href="{e(c["homepage"], quote=True)}" target="_blank" rel="noopener">홈페이지</a>')
        lines.append(" · ".join(links) + (f" · 정보 기준일 {e(c['modified'])}" if c["modified"] else "") + f" · {e(CREDIT)}")
        details.append(f'<div id="d-{k}" hidden>' + "<br>".join(lines) + "</div>")
    return (f"<style>{GALLERY_CSS}</style><div class='hint'>사진을 누르면 정보가 열립니다. 옆으로 넘겨 보세요.</div>"
            f"<div class='row'>{''.join(row)}</div><div id='panel'></div>{''.join(details)}<script>{GALLERY_JS}</script>")


def known_region(final: dict) -> str | None:
    """코스가 나왔거나, 지역은 이미 알고 다른 것(날짜 · 일수)만 되묻는 중이면 그 지역을 돌려준다. 아니면 None."""
    # 왜: "언제 출발하시나요?"라고 날짜만 되묻는데 지역 칩이 다시 떠서, 눌린 지역이 답에 덧붙어 지역이 바뀔 수 있었다(7-5 화면 확인에서 발견). 어디: 지역 칩을 그릴지 정할 때.
    # 교안: 직접 대응 없음. 화면 판단을 순수 함수로 빼 테스트한다.
    answer, region = (final or {}).get("answer") or {}, ((final or {}).get("request") or {}).get("region")
    return region if region and answer.get("kind") in ("course", "ask_back") else None


def compose_question(question: str, region: str | None, themes: list, has_course: bool) -> str:
    """입력창 문장 + 칩 선택 → 그래프에 넣을 문장. 칩은 조건 이해(parse_request)와 route 가 읽는 문장으로만 덧붙인다."""
    # 왜: 칩 선택값을 State 에 몰래 넣지 않고 문장으로 덧붙이면 같은 경로(조건 이해 · route)를 타서 규칙 · 기록이 하나로 남는다. 어디: 질문 보내기 직전.
    # 교안: 직접 대응 없음(2026-11-13 요청).
    text = question.strip()
    if has_course:   # 코스가 나온 뒤에는 새 여행이 아니라 "취향 추가"다
        return f"{text} 취향 추가: {', '.join(themes)}".strip() if themes else text
    extra = ([f"지역: {region}"] if region else []) + ([f"취향: {', '.join(themes)}"] if themes else [])
    return f"{text} ({', '.join(extra)})" if extra else text
