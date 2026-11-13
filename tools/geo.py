"""좌표 두 개의 직선거리를 구한다. 기준을 넘는지 판정하는 일은 여기 없다(6단계 검증기). (PRD 9번 distance_km, 14번 4단계 중 4-1)"""
import math

import config


def _point(p):
    """(위도, 경도) 로 읽는다. 읽지 못하면 사유 문장을 돌려준다."""
    if isinstance(p, dict):
        p = (p.get("lat"), p.get("lon"))
    if not isinstance(p, (list, tuple)) or len(p) != 2 or p[0] is None or p[1] is None:
        return None, "좌표가 없습니다"
    try:
        lat, lon = float(p[0]), float(p[1])
    except (TypeError, ValueError):
        return None, "좌표가 숫자가 아닙니다"
    if math.isnan(lat) or math.isnan(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, f"좌표가 범위를 벗어났습니다: ({lat}, {lon})"
    return (lat, lon), None


def distance_km(a, b) -> dict:
    """성공: {"ok": True, "km": 12.3} / 실패: {"ok": False, "reason"}. a · b 는 (위도, 경도) 또는 {"lat", "lon"}."""
    # 왜: LLM 이 "가까워요" 라고 말한 거리를 믿지 않고 코드가 계산한다. 어디: 6단계 validate_course 가 연속한 두 장소에 쓴다.
    # 교안: 3일차 Part2 도구 5조건(한 가지 일만 · 실패도 결과로). "숫자와 사실 판정은 코드가".
    (pa, why_a), (pb, why_b) = _point(a), _point(b)
    if why_a or why_b:
        return {"ok": False, "reason": why_a or why_b}

    # 왜: 지구가 둥글어 위도 · 경도 차이를 그냥 빼면 틀린다. 지구를 공으로 보고 두 점 사이의 호 길이를 구한다(하버사인 공식). 어디: 거리 계산.
    # 교안: 직접 대응 없음. 도로가 아니라 직선이라 산 · 바다를 돌아가는 길은 실제보다 짧게 나온다.
    lat1, lon1, lat2, lon2 = map(math.radians, (*pa, *pb))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    km = 2 * config.EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))
    return {"ok": True, "km": round(km, 2)}
