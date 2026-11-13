"""그래프 결과를 화면 · 내려받기 문서에 쓸 모양으로 바꾼다. Streamlit 을 모른다. (14번 7-1 ~ 7-3)

사실(이름 · 주소 · 거리 · 날짜 · 휴무)은 respond 가 만든 값을 그대로 옮기고 여기서 새로 판정하지 않는다.
관광공사 소개글은 고치지 않고 앞부분만 발췌한다(저작권 정책, PRD 11번).
"""
import math
from urllib.parse import quote

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


def weather_line(w: dict | None) -> str:
    if not w or not w.get("available"):
        return "날씨 정보를 가져오지 못했습니다"
    kind = "비 예보" if w.get("rainy") else "눈 예보" if w.get("snowy") else "비·눈 예보 없음"
    return f"최저 {w['temp_min']:g}~최고 {w['temp_max']:g}℃ · 강수확률 {w['rain_prob']:g}% · {kind}"


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


def export_markdown(state: dict, places: dict, as_of: str) -> str:
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
            lines.append(f"- [지도에서 보기]({map_link(place or s)})" + (f" · 정보 기준일 {place['modified']}" if place.get("modified") else ""))
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
