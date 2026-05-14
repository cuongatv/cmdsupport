"""Pydantic DTOs for personal habit planning and calendar views."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database.models import HabitOccurrenceStatus, TaskPriority


class HabitCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    priority: TaskPriority = TaskPriority.NONE
    preferred_time: time
    duration_minutes: int = Field(..., ge=1)
    active_days: list[int]
    is_active: bool = True

    @field_validator("active_days")
    @classmethod
    def active_days_valid(cls, v: list[int]) -> list[int]:
        invalid_days = [day for day in v if day < 0 or day > 6]
        if invalid_days:
            raise ValueError("active_days must contain values from 0 to 6")
        return v


class HabitRead(HabitCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_employee_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class HabitUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    priority: Optional[TaskPriority] = None
    preferred_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=1)
    active_days: Optional[list[int]] = None
    is_active: Optional[bool] = None

    @field_validator("active_days")
    @classmethod
    def active_days_valid(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return v
        invalid_days = [day for day in v if day < 0 or day > 6]
        if invalid_days:
            raise ValueError("active_days must contain values from 0 to 6")
        return v


class HabitOccurrenceStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    habit_id: uuid.UUID
    occurrence_date: date
    state: HabitOccurrenceStatus
    actual_start: Optional[time]
    shift_reason: Optional[str]
    created_at: datetime


class CalendarEventType(str, Enum):
    TASK = "task"
    HABIT = "habit"


class CalendarTaskEvent(BaseModel):
    event_type: Literal[CalendarEventType.TASK]
    task_id: uuid.UUID
    title: str
    priority: TaskPriority
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    schedule_locked: bool


class CalendarHabitEvent(BaseModel):
    event_type: Literal[CalendarEventType.HABIT]
    habit_id: uuid.UUID
    title: str
    priority: TaskPriority
    start: datetime
    end: datetime
    original_start: Optional[datetime] = None
    shift_reason: Optional[str] = None
    state: Optional[HabitOccurrenceStatus] = None


class CalendarWeekResponse(BaseModel):
    scope: Literal["personal", "department"]
    week_start: date
    week_end: date
    events: list[CalendarTaskEvent | CalendarHabitEvent]


class DashboardBuckets(BaseModel):
    total: int
    not_due_yet: int
    due_soon: int
    overdue: int


class UnitDashboardAggregate(BaseModel):
    unit_id: uuid.UUID
    unit_name: str
    unit_type: str
    buckets: DashboardBuckets


class DashboardOverviewResponse(BaseModel):
    personal: DashboardBuckets
    units: list[UnitDashboardAggregate]
    due_soon_days: int = 7
