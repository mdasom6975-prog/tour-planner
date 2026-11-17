"""시연 준비용: 지역별로 앞으로 며칠 동안 "비 · 눈 오는 날"로 판정되는 날짜를 보여 준다. (PRD 14번 11단계)

"비 오는 날" 시나리오는 예보에 비가 있어야 실내 위주 분기를 보여 줄 수 있다. 시연 전에 돌려 날짜를 고른다.
실행:  python scripts/find_rainy_days.py          (오늘부터 10일, 기상청 예보 범위)
       python scripts/find_rainy_days.py 14       (14일: 11일째부터는 Open-Meteo 가 응답해야 나온다)
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from tools.weather import get_weather

# 지역을 대표하는 한 점(위도, 경도). 코스에서는 후보 장소들의 가운데 점을 쓰므로 실제 값과 조금 다를 수 있다
POINTS = {"부산": (35.16, 129.16), "강릉": (37.75, 128.88), "제주": (33.38, 126.55), "서울": (37.57, 126.98), "전북(전주)": (35.82, 127.15), "전남광주(여수)": (34.76, 127.66)}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    today = date.today()
    days = [(today + timedelta(days=i)).isoformat() for i in range(n)]
    print(f"오늘 {today.isoformat()} · 비 판정 기준: 강수확률 {config.RAIN_PROB_THRESHOLD}% 이상 또는 눈")
    for name, (lat, lon) in POINTS.items():
        got = get_weather(lat, lon, days, today=today.isoformat())
        rows = got.get("days") or []
        if not rows:
            print(f"{name}: 날씨를 가져오지 못했습니다 ({got.get('reason') or got.get('notice') or '사유 없음'})")
            continue
        # 왜: 판정 기준은 그래프(graph/context.py)와 같은 config 값을 쓴다. 여기서 다른 기준을 쓰면 시연 때 화면과 어긋난다. 어디: 비 · 눈 판정.
        # 교안: 직접 대응 없음(시연 준비 도구).
        wet = [f"{d['date'][5:]}({d['rain_prob']:.0f}%)" for d in rows
               if d.get("available") and ((d.get("rain_prob") or 0) >= config.RAIN_PROB_THRESHOLD or (d.get("snow_cm") or 0) > 0 or d.get("snow"))]
        missing = [d["date"][5:] for d in rows if not d.get("available")]
        print(f"{name}: 비 · 눈 오는 날 {', '.join(wet) or '없음'}" + (f" · 예보 없음 {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
