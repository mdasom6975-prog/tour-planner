"""받은 장소 목록(data/raw/list_*.jsonl)을 세어 표로 보여 준다. API 를 호출하지 않는다. (PRD 14번 1단계 중 1-4a)

실행:  python scripts/list_stats.py
"""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def load() -> pd.DataFrame:
    # 왜: 세 지역 파일을 한 표로 합쳐야 지역 × 유형으로 셀 수 있다. 어디: 모든 집계의 출발점.
    # 교안: 4일차 가계부 PRD — CSV 를 pandas 로 읽어 합계 · 비율을 코드가 계산하던 방식.
    frames = [pd.read_json(p, lines=True, dtype=str) for p in sorted(RAW_DIR.glob("list_*.jsonl"))]
    return pd.concat(frames, ignore_index=True).fillna("")


def main():
    df = load()

    # 왜: 상세 수집 범위를 정할 기본 숫자다. 어디: 1-4c 의 소요 일수 계산에 그대로 들어간다.
    # 교안: 2일차 Part3 "숫자로 판단" / 4일차 "숫자는 코드가" — 건수를 LLM 이나 기억이 아닌 코드로 센다.
    table = pd.crosstab(df["contenttypeid"], df["region"], margins=True, margins_name="합계")
    print("■ 지역 × 콘텐츠 유형 건수")
    print(table.to_string(), "\n")

    # 왜: 유형 번호의 뜻을 기억에 의존하지 않고 실제 장소 이름으로 확인한다. 어디: 표를 읽을 때.
    # 교안: 2일차 Part3 "평가 전에 데이터를 직접 읽어 본다" 는 태도. 직접 대응하는 코드는 없음.
    print("■ 유형별 예시 장소 (각 5곳)")
    for type_id, group in df.groupby("contenttypeid"):
        names = group["title"].sample(min(5, len(group)), random_state=0).tolist()
        print(f"  {type_id}: {' / '.join(names)}")
    print()

    # 왜: 좌표가 없으면 거리 검증을 못 하고, 이미지가 없으면 화면 카드가 빈다. 어디: 수집 우선순위 판단.
    # 교안: 1일차 03 "검증 단계 분리" — 검증에 필요한 값이 데이터에 있는지 먼저 확인.
    df["좌표있음"] = (df["mapx"] != "") & (df["mapy"] != "") & (df["mapx"] != "0")
    df["이미지있음"] = df["firstimage"] != ""
    df["주소있음"] = df["addr1"] != ""
    quality = df.groupby("contenttypeid")[["좌표있음", "이미지있음", "주소있음"]].mean().mul(100).round(1)
    quality.insert(0, "건수", df.groupby("contenttypeid").size())
    print("■ 유형별 품질 (%)")
    print(quality.to_string(), "\n")

    # 왜: 오래 방치된 정보가 얼마나 되는지 봐야 "최신 정보" 를 약속할 수 있다. 어디: 출처 · 수정일 표시.
    # 교안: 팀프로젝트 교안 적용 문서의 "출처 URL · 확인일을 함께 둔다" 와 같은 생각.
    year = df["modifiedtime"].str[:4]
    print("■ 마지막 수정 연도별 건수")
    print(pd.crosstab(year, df["region"], margins=True, margins_name="합계").to_string())


if __name__ == "__main__":
    main()
