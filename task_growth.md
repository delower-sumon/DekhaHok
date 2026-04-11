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
- [x] Seed 3 Initial SEO posts.
  
## 6. Admin & Security Enhancements (Complete)
- [x] Security: Introduced "Booking ID" mandatory verification layer for Group Chat entry.
- [x] Security: Implemented session caching for chat verification (sessionStorage).
- [x] Admin: Persistent session logic (localStorage) - no login required on Home/Refresh.
- [x] Admin: Manual "Verified Citizen" badge management in Booking Edit.

- [x] UI/UX: Enhanced Google Maps marker clicks to use descriptive search (Place + Area).
- [x] Bugfix: Restored missing Partnership Admin HTML sections.

## 7. UI/UX Final Polish (Complete)
- [x] UI: Optimized vertical layout by reducing section padding (`py-16` -> `py-10`) and title margins.
- [x] UI: Revamped FAQ section with premium designs and 7 comprehensive items.
- [x] Policy: Implemented 10-day Refund Policy FAQ (3-day payout guarantee).
- [x] Cleanup: Tightened blog card internal spacing and title-to-content rhythms.

- [x] Admin: Extended location categories (Resort, Cinema Hall).[not done yet]
