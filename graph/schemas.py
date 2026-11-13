"""LLM 이 채우는 조건 스키마. 이 칸에 없는 값은 State 로 들어오지 못한다. (PRD F1)"""
from typing import Literal

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


class Slot(BaseModel):
    slot: Literal["오전", "점심", "오후", "저녁"] = Field(description="하루 칸. 오전·오후는 가볼 곳, 점심·저녁은 음식점")
    content_id: str = Field(description="후보 장소의 id 를 그대로")
    reason: str = Field(description="이 장소를 이 자리에 넣은 이유 한 문장")


class DayPlan(BaseModel):
    date: str = Field(description="여행일 YYYY-MM-DD (주어진 날짜 그대로)")
    slots: list[Slot] = Field(default_factory=list)


class Backup(BaseModel):
    content_id: str = Field(description="부가 코스 후보의 id 를 그대로")
    reason: str = Field(description="비나 눈이 올 때 가볼 만한 이유 한 문장")


class CafePick(BaseModel):
    content_id: str = Field(description="카페 후보의 id 를 그대로")
    reason: str = Field(description="코스 근처에서 들르기 좋은 이유 한 문장")


class Course(BaseModel):
    days: list[DayPlan] = Field(default_factory=list)
    rain_reason: str = Field("", description="비·눈 오는 날을 실내 위주로 짠 이유 한 줄. 그런 날이 없으면 빈 문자열")
    backup: list[Backup] = Field(default_factory=list, description="비나 눈이 올 때 갈 만한 실내 장소 2~3곳")
    cafes: list[CafePick] = Field(default_factory=list, description="코스 근처에서 들를 만한 카페 2곳. 코스 칸에는 넣지 않는다")


class Route(BaseModel):
    mode: Literal["new", "edit"] = Field(description="지금 문장이 이미 나온 코스를 고치는 말이면 edit, 새 여행 요청이면 new")


class EditedCourse(Course):
    note: str = Field("", description="요청 중 후보에 없어서 반영하지 못한 부분을 한 문장으로. 모두 반영했으면 빈 문자열")
