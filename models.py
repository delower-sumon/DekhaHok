from datetime import date, time
from typing import Optional
from pydantic import BaseModel, field_validator
import re


# ---------------------------------------------------------------------------
# Booking — public form submission
# ---------------------------------------------------------------------------

class BookingCreate(BaseModel):
    name:               str
    phone:              str
    email:              Optional[str] = None
    age:                Optional[int] = None
    group_size:         int
    preferred_date:     date
    preferred_time:     str         # "17:00" or "19:00"
    venue_type:         str
    conversation_style: Optional[str] = None
    preferred_people:   Optional[str] = None
    current_location:   Optional[str] = None
    preferred_location: Optional[str] = None

    @field_validator("group_size")
    @classmethod
    def validate_group_size(cls, v):
        if v not in (2, 5):
            raise ValueError("group_size must be 2 or 5")
        return v

    @field_validator("preferred_time")
    @classmethod
    def validate_preferred_time(cls, v):
        if v not in ("17:00", "19:00"):
            raise ValueError("preferred_time must be '17:00' or '19:00'")
        return v

    @field_validator("venue_type")
    @classmethod
    def validate_venue_type(cls, v):
        if v not in ("restaurant", "public_place"):
            raise ValueError("venue_type must be 'restaurant' or 'public_place'")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not re.match(r"^(\+?880)?01[3-9]\d{8}$", cleaned):
            raise ValueError("Enter a valid Bangladeshi phone number (01XXXXXXXXX)")
        return cleaned

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if v is not None and not (18 <= v <= 80):
            raise ValueError("Age must be between 18 and 80")
        return v


class BookingResponse(BaseModel):
    tracking_id: str
    message:     str


class TrackingResponse(BaseModel):
    tracking_id:    str
    name:           str
    group_size:     int
    preferred_date:  date
    preferred_time:  Optional[str] = None
    venue_type:      str
    booking_status:  str
    payment_status: str
    fee_amount:     float
    current_location:   Optional[str] = None
    preferred_location: Optional[str] = None
    assigned_venue: Optional[str] = None
    meet_date:      Optional[date] = None
    meet_time:      Optional[str] = None


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AdminBookingUpdate(BaseModel):
    payment_status: Optional[str] = None
    booking_status: Optional[str] = None
    admin_notes:    Optional[str] = None

    @field_validator("payment_status")
    @classmethod
    def validate_payment(cls, v):
        if v is not None and v not in ("unpaid", "paid"):
            raise ValueError("payment_status must be 'unpaid' or 'paid'")
        return v

    @field_validator("booking_status")
    @classmethod
    def validate_booking(cls, v):
        if v is not None and v not in ("processing", "confirmed", "completed"):
            raise ValueError("Invalid booking_status")
        return v


class GroupCreate(BaseModel):
    venue_name: str
    meet_date:  date
    meet_time:  str
    group_size: int


class GroupAssign(BaseModel):
    booking_ids: list[int]


class GroupUpdate(BaseModel):
    venue_name: Optional[str] = None
    meet_date:  Optional[date] = None
    meet_time:  Optional[str] = None
    group_size: Optional[int] = None
    status:     Optional[str] = None


class LocationCreate(BaseModel):
    name: str


class LocationResponse(BaseModel):
    id: int
    name: str
    is_active: bool
