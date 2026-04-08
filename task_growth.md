# Task: Growth Optimizations (DekhaHok)

## 1. Database Phase (Complete)
- [x] Add `blogs` table to `database.py`.
- [x] Extend `bookings` table with `referral_code`, `referred_by`, and `is_verified`.
- [x] Seed initial SEO blog posts in `init_db`.

## 2. Models Phase (Complete)
- [x] Create `Blog` and `PublicGroup` Pydantic models in `models.py`.
- [x] Update `BookingCreate` and `TrackingResponse` in `models.py`.

## 3. Backend (API) Phase (Complete)
- [x] Helper: `generate_referral_code` in `main.py`.
- [x] API: `GET /api/public/groups` (Anonymized discover).
- [x] API: `GET /api/blogs` (Public posts).
- [x] API: `POST /api/admin/blogs` (Admin CRUD).
- [x] Logic: Generate referral code and save referrer on booking.
- [x] Logic: "Verified Citizen" badge trigger on completed booking + referral.

## 4. Frontend Phase (Complete)
- [x] UI: "Discover Meetups" section (Guest Browsing) with area filter.
- [x] UI: Blog section for SEO stories.
- [x] UI: Referral Code input in booking form.
- [x] UI: Referral dashboard in tracker (Personal code + Verified status).

## 5. Content & SEO (Complete)
- [x] Seed 3 Initial SEO posts:
  - "Best places to meet in Dhaka"
  - "Safe meeting spots Dhanmondi"
  - "Networking events Dhaka"
