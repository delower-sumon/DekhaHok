# Changelog - DekhaHok Beta

All notable changes to the DekhaHok main branch will be documented in this file.

## [2026-06-26] - Feature Branch: Host Marketplace (Initial Commit)

> **Branch:** `feature/host-marketplace`
> This is the initial snapshot of the DekhaHok Beta codebase branched off `main` to begin host marketplace development. All files are committed as the foundation for upcoming host-facing features.

### Branch Scope
- **Initial codebase snapshot** of all backend, frontend templates, static assets, admin panel, and configuration files as of 2026-06-26.
- **Foundation established** for host marketplace feature development including host onboarding, event management, booking flows, notification systems, SEO architecture, blog editor, and admin pipeline.

---

## [2026-06-26] - SEO Architecture, Blog Editor & Favicon Update

### Added
- **User Notification System:** Expanded the notification system to all authenticated users. When an admin updates a booking status, the user instantly receives a notification linking to their tracking dashboard.
- **Smart Notification Suggestions:** When a user checks their notification bell and has zero unread alerts, the dropdown intelligently fetches and displays 3 random live experiences as "Suggested For You" with direct booking links.
- **Host Notification System:** Added a fully-fledged notification architecture. Admins approving events and users booking tickets now instantly trigger database notifications.
- **Global Notification Bell:** Injected a dynamic notification bell into the navbar for all authenticated users, showing a pulsing red badge and dropdown for unread alerts.
- **Area Filtering:** Built a sleek dropdown selector on the Homepage to let users filter experiences by specific Dhaka areas, working in tandem with category and time filters.
- **Global SEO Tags:** Injected default Open Graph and Twitter Card tags into `base.html` so all inherited pages have a rich social media footprint by default.
- **Dynamic Event Tags:** Event details are now fetched server-side in `main.py` and injected dynamically into the `<head>` of `booking.html`, allowing Facebook/Twitter to crawl event links natively instead of hitting a Javascript wall.
- **Event Sitemap Indexing:** Updated `/sitemap.xml` in `main.py` to automatically include all published events alongside blogs for native Google Search indexing.
- **Dedicated Blog Editor:** Implemented `admin/blog_edit.html` for a dedicated on-page editing experience, migrating away from the legacy modal system.
- **Custom Favicon:** Added a custom, cropped `favicon.png` across all entry templates (`base.html`, `index.html`, `404.html`, `DekhaHok.html`, and `admin/index.html`).

### Changed
- **Platform FAQ Extraction:** Extracted the legacy FAQ accordion from the old `DekhaHok.html` page and transplanted it to the bottom of the new Homepage. The content was completely rewritten in Bengali to reflect the new marketplace operations (NID Verification, Tracking IDs, Refund Policy), and legacy Lucide icons were replaced with FontAwesome.
- **Hero SVG Animation Fix:** Fixed a UI bug in the Homepage's SVG connection animation where the central "Top Experience" circle was displaying a generic map-pin instead of an event image. The animation now properly cycles through a curated set of event snapshot images as the dots connect.
- **Host Event UI Messaging:** Updated the "Publish Event" button and wording in the Host Event Creation page to "Submit for Review" to properly convey the admin-approval workflow.
- **Dashboard Timestamp Polish:** Scrubbed raw PostgreSQL ISO timestamps from the Host Dashboard, replacing them with formatted 12-hour AM/PM dates and smartly deduped location strings.
- **Auth Modal Consolidation:** Moved the auth modal from the standalone page into `base.html` to be globally accessible. It is now triggered instantly from Homepage Experience cards and booking buttons in a condensed, sleeker UI.
- **Crawler-Friendly Booking Route:** Unauthenticated users hitting `/booking/{event_id}` are no longer hard-redirected to `/login`. Instead, they view the event metadata and an inline "Login to Book" UI, preserving SEO crawler visibility while retaining the forced-login business logic.
- **Blog Meta Bug Fix:** Repaired Open Graph tags in `blog_detail.html` that were mistakenly reading `blog.description` instead of `blog.seo_description` and `image_url`.

## [2026-06-25] - Authentication, Host Dashboard, & Avatar Upgrades

### Added
- **Dynamic Avatars:** Replaced legacy Dicebear images with `ui-avatars.com` to dynamically generate initial-based profile pictures for new manual and Google OAuth registrations.
- **Host Profession Capture:** Added `profession` column to `hosts` table. The host application form now captures this, and the host dashboard dynamically displays it.
- **Host Application Expansion:** Added more detailed categories (Sports & Wellness, Entertainment, Education) to the host application form and made the community experience field optional.
- **Existing Booking Detection:** Logged-in users clicking an event they've already booked are now shown their Tracking ID directly instead of the checkout form.

### Changed
- **Forced Booking Login:** Unauthenticated users attempting to book an event are now strictly redirected to the login/signup page.
- **Google OAuth Redirects (`?next=`):** Overhauled `auth.html` and the Google OAuth callback in `main.py`. The system now successfully parses the `?next=` URL parameter, dynamically injecting it into the Google Login button ID, allowing seamless post-login redirection back to the event checkout.
- **Host Dashboard UI Polish:** Swapped out the old random emoji icons (🎨, 🌱, 💼) in the "Your Scheduled Activities" list for a unified brand leaf icon (`fa-leaf`).
- **Host Ratings Reset:** Removed the placeholder "4.98 ★" rating on the dashboard, resetting it to "0.0 ★" until hosts accumulate actual reviews.

### Removed
- **Discount Equality:** Stripped all legacy 20% female discount logic, calculations, and UI dropdown labels from the booking checkout process.

## [2026-06-24] - Host Payout Management & UI Enhancements

### Added
- **Host Payout Database Support:** Added `host_payment_status` column to the `events` table via database migrations.
- **Admin Payout API:** Created `GET /api/admin/payouts` and `PATCH /api/admin/payouts/{event_id}` endpoints.
- **Admin Payouts UI:** Added a new "Payouts" tab in the Admin Panel to track event revenues and toggle host payment statuses.

### Changed
- **Booking Counts Visibility:** Displayed dynamic `booked_count/capacity` ratios on Curated Experience cards (Homepage) and the Booking Page event info section.
- **Admin Navigation Simplification:** Merged the "Partnerships" tab into the "Areas & Locations" tab, which has been renamed to **"Operations & Data"**. Partnership requests and Area management now share a vertically stacked view.

### Fixed
- **Tracking Icon Bug:** Swapped the failing `map-pin` Lucide icon for a reliable FontAwesome `location-dot` in the homepage tracking section.
- **Payout API Error:** Fixed a 500 Internal Server Error by joining the `users` table to fetch host names and correcting the authentication function call to `require_admin`.

### Future Development (Next Testing Session)
- **[DONE] Blog Management Refactor:** Clean up old blogs and enhance the admin blog management UI.
- **[DONE] Blog Image Hosting:** Migrate blog images away from direct GitHub repo rendering inside the app directory.
- *[AGENT NOTE: When you read this changelog in a future session, check if these future development items have been completed. If yes, mark them done. If not, remind the user through the chat interface.]*

## [2026-06-24] - Day 3: Blog Improvements & UI Polish

### Added
- **Blog View Tracking:** Implemented a silent `views` column in the database and an API tracker in the `serve_blog_detail` endpoint to increment views dynamically.
- **Other Blogs Showcase:** Added a related blogs grid to the bottom of each blog article.
- **Blog Page CTA:** Injected a beautiful "Book Experience" conversion card to direct readers to the `/#catalog-section`.
- **Blog Admin Upload:** Built a direct file uploader in the admin panel that securely converts images into `Base64` storage inside the database.

### Changed
- **Homepage Hero Glow:** Applied an emerald UI background glow behind the primary Bengali text block.
- **Capacity Badge Redesign:** Transformed the top-aligned tracking numbers into an elegant right-aligned pill layout matching the host profile in the experience cards.
- **Booking Counter UI:** Made the checkout tracker visible with a neat `0/5 Booked` pill on the sticky event summary side panel.
- **Total Revenue Display:** Simplified the financial logic to keep "Total Revenue" displaying at `৳0` dynamically until the event fully completes.

### Fixed
- **Host Avatar Sync:** Adjusted the SQL join logic to properly sync and show real host profile pictures on event cards instead of random dicebear icons.
- **Missing Migration:** Fixed the auto-reloader server crash by properly injecting the `views` column migration query directly into the end of the `database.py` schema init.

## [2026-06-22] - Redesign & Operations Refactoring

### Redesign & Visual Polish
- **Auth Page Header:** Centered Bengali SVG logo (`dekhahok_bn.svg`) and removed speech bubble / sprout logo icons from the login page (`auth.html`).
- **Category Extension:** Renamed the `Tours` category filter to `Travel` and added `Cafe Explorer` (☕), `Arts & Crafts` (🖼️), and `Tech & Startups` (🚀) filters on the homepage (`index.html`) and mockup (`index-ui.html`).
- **Snappy Dropdown & Avatar Upload:** Eliminated the snappy profile dropdown collapse by wrapping it in an absolute div, bridging the hover boundary gap. Added a "Change Photo" button and an image upload modal utilizing Base64 encoding.
- **Admin Panel Layout Redesign:** Replaced the vertical sidebar in `admin/index.html` with the mockup's top operations header, always-visible metrics grid (GPV, Active Hosts, Experiences Published, Tickets Issued), and a scrollable horizontal tabs bar supporting all 9 dashboard views.

### Bug Fixes
- **Booking Flow Date Errors:** Resolved a 500 error in `/api/bookings` when booking events with missing dates by falling back safely to the current date and default time.
- **Coupon Code Sanitization:** Fixed checkout failures when coupon codes were passed as empty strings. Sanitized inputs to automatically skip empty coupon validation.
- **API updates:** Added user avatar upload endpoint `/api/users/avatar` and updated `/api/admin/dashboard` to return NID-verified host counts, published experiences, and tickets issued.

## [2026-06-22] - Host-Driven Marketplace Transition (Taas)

### Changed
- **Homepage UI Routing Transition:** Switched the root routing in `main.py` to serve the new modernized `index.html` instead of the legacy `DekhaHok.html` template.

### Added
- **Host Onboarding Application (`/host/apply`):** A multi-step application flow for users to apply as community hosts by submitting NID, operating area, bio, and category.
- **Host Dashboard (`/host/dashboard`):** Sidebar dashboard for verified hosts displaying earnings statistics, events counts, attendee reaches, scheduled activities feeds, attendee registry modals, and waitlist promotion API actions.
- **Admin Marketplace Pipeline:** Integrated host audits (verification status updates & NID auditing), discover catalog event moderation (draft-to-published toggles), and booking event-to-event transfer capabilities into the admin dashboard (`admin/index.html`).
- **Jinja2 User Session Context Processor:** Automated user session checking (`user` data payload injection) into all page templates from signed browser cookies.
- **Marketplace DB Schema Migrations (`database.py`):** Structured database initialization schemas for `users`, `hosts`, and `events`, modified `bookings` relations, and implemented startup migrations mapping legacy booking IDs to a seeded default event.

### Fixed
- **Event Date Parsing:** Corrected timestamp string conversion for NULL event dates in `/api/events` and `/api/events/{event_id}` to prevent `Invalid Date` on UI catalog cards, mapping them to `null` which safely displays as `"TBA"`.
- **User Avatar Image Fallbacks:** Resolved `/None` and `/host/None` console requests by adding a profile avatar fallback using Dicebear SVG avatars in `templates/base.html` and the authentication payloads.

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
