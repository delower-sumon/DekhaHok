from __future__ import annotations
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
    preferred_meeting_point: Optional[str] = None
    payment_method:     str         # "bkash" or "nagad"
    payment_sender_digits: str      # last 2 digits
    referred_by:        Optional[str] = None # referral code
    interests:          Optional[str] = None # Acquisition: interests
    expectations:       Optional[str] = None # Acquisition: expectations
    wants_pickup:       bool = False
    wants_dropoff:      bool = False
    vibe:               Optional[str] = None # Career, Travel, Philosophy
    coupon_code:        Optional[str] = None

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

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v):
        if v.lower() not in ("bkash", "nagad", "upay"):
            raise ValueError("Invalid payment method")
        return v.lower()

    @field_validator("payment_sender_digits")
    @classmethod
    def validate_digits(cls, v):
        if not re.match(r"^\d{2}$", v):
            raise ValueError("Sender digits must be exactly 2 digits")
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
    preferred_meeting_point: Optional[str] = None
    assigned_venue: Optional[str] = None
    meet_date:      Optional[date] = None
    meet_time:      Optional[str] = None
    payment_method:     Optional[str] = None
    payment_sender_digits: Optional[str] = None
    group_members: Optional[list] = [] # list of {name, phone, age, rating}
    rated_member_ids: Optional[list[int]] = [] # list of member ids already rated by this user
    rejection_reason: Optional[str] = None
    assigned_group_id: Optional[int] = None
    referral_code:     Optional[str] = None
    is_verified:       bool = False
    interests:         Optional[str] = None
    expectations:      Optional[str] = None
    wants_pickup:      bool = False
    wants_dropoff:     bool = False
    vibe:              Optional[str] = None
    discount_amount:   float = 0.0


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AdminBookingUpdate(BaseModel):
    payment_status: Optional[str] = None
    booking_status: Optional[str] = None
    admin_notes:    Optional[str] = None
    rejection_reason: Optional[str] = None
    is_verified:    Optional[bool] = None
    wants_pickup:   Optional[bool] = None
    wants_dropoff:  Optional[bool] = None

    @field_validator("payment_status")
    @classmethod
    def validate_payment(cls, v):
        if v is not None and v not in ("unpaid", "paid"):
            raise ValueError("payment_status must be 'unpaid' or 'paid'")
        return v

    @field_validator("booking_status")
    @classmethod
    def validate_booking(cls, v):
        if v is not None and v not in ("processing", "confirmed", "completed", "unsuccessful"):
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


class RatingCreate(BaseModel):
    ratee_id: int
    group_id: int
    score: int
    comment: Optional[str] = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if not (1 <= v <= 5):
            raise ValueError("Score must be between 1 and 5")
        return v


class MessageCreate(BaseModel):
    group_id: int
    message: str


class LocationCreate(BaseModel):
    name: str



class MeetingPointCreate(BaseModel):
    location_id: int
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    point_type: str = "public_place"

class MeetingPointResponse(BaseModel):
    id: int
    location_id: int
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    point_type: str = "public_place"
    is_active: bool
    area_name: Optional[str] = None

class LocationResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    points: list[MeetingPointResponse] = []

class PartnershipCreate(BaseModel):
    restaurant_name: str
    contact_number: str

class PartnershipUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Blogs
# ---------------------------------------------------------------------------

class BlogCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    content: str
    keywords: Optional[str] = None
    seo_description: Optional[str] = None
    image_url: Optional[str] = None
    image_alt: Optional[str] = None
    badge_text: Optional[str] = None
    status: str = "published"
    author: Optional[str] = "Team DekhaHok"
    author_title: Optional[str] = None
    author_image_url: Optional[str] = None
    is_pivoted: bool = False

class BlogResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    keywords: Optional[str] = None
    seo_description: Optional[str] = None
    image_url: Optional[str] = None
    image_alt: Optional[str] = None
    badge_text: Optional[str] = None
    likes: int
    shares: int
    status: str
    author: Optional[str] = "Team DekhaHok"
    author_title: Optional[str] = None
    author_image_url: Optional[str] = None
    is_pivoted: bool = False
    created_at: str

class BlogUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[str] = None
    seo_description: Optional[str] = None
    image_url: Optional[str] = None
    image_alt: Optional[str] = None
    badge_text: Optional[str] = None
    status: Optional[str] = None
    is_pivoted: Optional[bool] = None
    author: Optional[str] = None
    author_title: Optional[str] = None
    author_image_url: Optional[str] = None

# ---------------------------------------------------------------------------
# Public Discovery
# ---------------------------------------------------------------------------

class PublicGroupResponse(BaseModel):
    id: int
    group_code: str
    venue_name: str # Masked in API implementation
    meet_date: date
    meet_time: str
    group_size: int
    member_count: int
    status: str

# ---------------------------------------------------------------------------
# Blog Interaction
# ---------------------------------------------------------------------------

class BlogCommentCreate(BaseModel):
    user_name: str
    comment: str

class BlogCommentResponse(BaseModel):
    id: int
    blog_id: int
    user_name: str
    comment: str
    created_at: str

