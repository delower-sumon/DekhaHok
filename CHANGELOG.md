# Changelog - DekhaHok Beta

All notable changes to the DekhaHok main branch will be documented in this file.

## [2026-04-03] - UI & Backend Beta Fixes

### Added
- **Analytics Module**: Integrated a website page view tracking system. Hits to the root URL are now logged (IP-hashed) in a new `page_views` table.
- **Admin Analytics Tab**: A new section in the admin dashboard to view stats by Day, Week, Month, and All-Time.
- **Admin Sidebar Badges**: Dynamic counting badges for "Groups" (unfilled) and "Areas/Locations" (active) to mirror the "Bookings" badge.
- **Booking Sorting**: Status column in the admin bookings table is now sortable (A-Z toggling).
- **Time Preferences**: User's `preferred_time` is now displayed alongside the date in the admin bookings table.

### Changed
- **Capacity Enforcement**: Backend now strictly blocks group assignments that exceed capacity or involve mismatched ticket sizes.
- **Toast Notifications**: Drastically reduced display duration to 500ms and added `clearTimeout` logic to prevent UI overlapping/locking during multiple rapid updates.
- **Frontend Tracker Layout**: Relocated "Hub Buttons" (Group Chat/Emergency) to the bottom of the tracking status UI for better accessibility.
- **Mobile UI Refinement**: Added a responsive line break for the "-শুভকামনা" text in the hero section to prevent layout clipping on small screens.
- **Date Formatting**: Implemented human-readable long-form date formatting for the tracker UI (e.g., "4 April 2026").

### Fixed
- **Notification Persistence**: Fixed a bug where toast notifications would stay on screen indefinitely if multiple updates were triggered quickly.
- **Hero Text Clipping**: Resolved overlapping text issues on mobile views for the hero status strip.
