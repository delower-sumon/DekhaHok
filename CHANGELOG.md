# Changelog - DekhaHok Beta

All notable changes to the DekhaHok main branch will be documented in this file.

## [2026-04-24] - UI Refinements & Codebase Cleanup

### Changed
- **Vibe Buttons Redesign:** Redesigned the Vibe (Mood) selection buttons into clean, pill-shaped utility buttons. Relocated them immediately beneath the "Preferences Note" input field, organized them into a single horizontally-scrollable row, and removed the previous confetti click animation.
- **Promo Code Box:** Reduced the overall padding, border-radius, and max-width of the "Coupon Code" section to make it more compact and visually proportional to surrounding elements.
- **Blog Image SEO:** Modified the blog detail template to display the `image_alt` text as a visible, italicized caption below the cover image.
- **Footer Links:** Added the missing LinkedIn social icon to the footers of the homepage and the blog detail page.

### Removed
- **Legacy Analytics Tracking:** Completely removed the `page_views` database table tracking, the root `/` route IP-logging, the `/api/admin/analytics` endpoint from `main.py`, and the corresponding "Analytics" tab from the Admin dashboard in favor of Cloudflare and Google Search Console.
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

## [2026-04-03] - UI/UX Refinements (Session 2)

### Changed
- **Card Redesign**: Applied requested "Button 33" glassmorphic effect to Member Cards and Venue/Place Cards in the status tracker for a more tactile, premium feel.
- **Hub Buttons**: Reverted Group Chat and Emergency Support buttons to their original `action-hub-btn` branding.
- **Rating Stars**: Fixed a critical mobile layout bug where rating stars appeared vertically. Implemented strict inline flex styles to force horizontal alignment and tap-friendliness on mobile.

### Added
- **Admin Persistence**: Implemented `sessionStorage` for admin authentication, allowing dashboard refreshes without forced logouts while maintaining tab-level security.
