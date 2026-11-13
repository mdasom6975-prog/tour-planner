"""LLM 이 채우는 조건 스키마. 이 칸에 없는 값은 State 로 들어오지 못한다. (PRD F1)"""
from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    region: str | None = Field(None, description="지원 지역 이름 하나. 도시를 말하면 그 도시가 속한 지역. 없으면 null")
    place: str | None = Field(None, description="시·군 이름(예: 전주). 말하지 않았으면 null")
    start_date: str | None = Field(None, description="여행 시작일 YYYY-MM-DD. 알 수 없으면 null")
    days: int | None = Field(None, description="여행 일수(1박 2일이면 2). 말하지 않았으면 null")
    companions: str | None = Field(None, description="동행(예: 부모님, 아이). 없으면 null")
    preferences: list[str] = Field(default_factory=list, description="취향·바라는 것")
    exclusions: list[str] = Field(default_factory=list, description="빼 달라고 한 것")


class Grade(BaseModel):
    relevant_ids: list[str] = Field(default_factory=list, description="조건에 맞는 후보의 id")
    reason: str = Field("", description="부족한 점 한 문장")


class NewQuery(BaseModel):
    query: str = Field(description="고쳐 쓴 검색 질의 한 문장")
