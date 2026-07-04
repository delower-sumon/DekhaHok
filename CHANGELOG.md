# Changelog - DekhaHok Beta

All notable changes to the DekhaHok main branch will be documented in this file.

## [2026-07-05] - SEO, Core Web Vitals & Accessibility Optimizations

### Added
- **Schema.org Structured Data**: Injected `Organization` schema directly into `base.html` for native Google Knowledge Graph rendering (including founding date, correct phone number, and synchronized social links). Added dynamic `Event` schema logic into `booking.html` for rich search results.
- **Explicit Image Dimensions**: Added `width="140"` and `height="34"` to the main navbar branding logo in `base.html` to eliminate Cumulative Layout Shift (CLS).

### Changed
- **SEO Metadata**: Standardized the HTML `lang="bn"` attribute across all templates. Reformatted `<h1>` structures for optimal search engine crawling while retaining UI consistency.
- **Resource Deferral & Script Loading**: Improved Time to First Byte (TTFB) by deferring non-critical scripts (`lucide.js`, `canvas-confetti.js`). Confined heavyweight `leaflet` mapping libraries exclusively to `index.html`.
- **Accessibility (Touch Targets)**: Expanded all interactive icon-only button touch targets (Navbar Notifications, Profile, Mobile Menu, Footer Socials) to a minimum of `44x44px` to meet WCAG 2.1 mobile tap target standards. Enforced descriptive `aria-label` tags for screen readers across the application.
- **Image Formats & Lazy Loading**: Converted heavy static assets (like `dekhahok_ui.png`) to lightweight `.webp` equivalents. Systematically applied `loading="lazy"` to all below-the-fold images across all templates.

### Removed
- **Unused Assets**: Permanently deleted unreferenced and oversized images (`blind_adda.jpeg`, `thelocal.jpg`, `sumon.png`, `dekhahok_ui.png`) from `static/assets/`.
- **Demo Avatars**: Stripped static mockup user avatars (`rita`, `rubel`, `lisa`) and wired the affected components (`DekhaHok.html`, `blog_detail.html`) to live backend user profile API endpoints (`/api/users/X/avatar`).
- **Homepage Map Section**: Removed the deprecated map visualization elements and initialization scripts from `index.html` per product requirements.

## [2026-07-04] - Safety Enhancements, Form Fixes & Footer Social Integration

### Added
- **Event Creation Safety Terms**: Introduced a mandatory Bengali guidelines & safety checkbox to Step 3 of the Event Creation form (`host_event_create.html`). Hosts must acknowledge the terms to submit an event for review.
- **Social Media Links in Footer**: Integrated a social links row with Facebook, Instagram, LinkedIn, YouTube, and X (Twitter) into the "Company" column of all standard platform footers (`base.html` and other standalone files).
- **X (Twitter) Logo SVG**: Injected a clean inline SVG for the X logo to bypass FontAwesome version limitations on older loaded CDNs, ensuring full cross-platform icon rendering.

### Changed
- **Footer Social Link Update**: Updated X (Twitter) social redirect link to `https://x.com/dekhahok` with `target="_blank"` across all platform footers.
- **Footer Tagline Recolor**: Changed the CSS text color of the `"Beyond the digital bubble."` tagline from `text-zinc-500` to `text-sky-400` in the footer of all standard pages to match the diamond blue heart icon's color.
- **Founding 100 Badge Position**: Realigned the "Founding 100" tag to sit on the top-left corner (`left-1.5`) of the host's profession badge, matching the vertical text baseline and preventing left-border avatar overlap.
- **Cover Image Hidden Input Validation Fix**: Removed the HTML5 `required` attribute from the hidden file upload element (`#ev-image`) in `host_event_create.html`. This allows JavaScript to capture form validation errors gracefully, showing the user-facing warning text rather than throwing browser focus exceptions.
- **Updated Bengali Safety Copy**: Refined the Bengali terminology in participant booking (`booking.html`) and host onboarding application (`host_apply.html`) terms.
- **Payment Anti-Flake Bengali Notice**: Translated the anti-flake banner copy inside the booking checkout modal to Bengali, keeping the English text as `sr-only` for SEO and screen-reader accessibility.
- **Official Handle Correction**: Fixed the official Instagram redirect URLs to `https://www.instagram.com/dekha_hok` across all templates.


## [2026-07-03] - Community Safety, Founding 100 & Admin Badge System

### Added
- **Community Safety Acknowledgements**: Injected mandatory Bengali safety checkboxes (with `sr-only` English for SEO) into the participant booking flow (`booking.html`) and the host application flow (`host_apply.html`). Users and hosts cannot proceed without explicitly agreeing to community guidelines.
- **Founding 100 Badge System**: Introduced a dynamic "Founding 100" badge on host profession tags featuring an emerald outer glow (`shadow-[0_0_8px_rgba(16,185,129,0.5)]`) and a gradient overlay label. The badge renders on both homepage event cards (`index.html`) and booking detail views (`booking.html`).
- **Admin-Controlled Badge Assignment**: Added `is_founding BOOLEAN DEFAULT FALSE` column to the `hosts` table with automatic migration on startup. The admin can now toggle the Founding 100 badge per host from the Host Verification Pipeline in `admin/index.html`, using the existing PATCH `/api/admin/hosts/{host_id}` endpoint.
- **Backfill Migration**: One-time automatic backfill sets `is_founding = TRUE` for all hosts with `id <= 100` on first server startup after migration.

### Changed
- **Mobile Booking Layout Fix**: Refactored the booking event card layout from a rigid horizontal `flex` to a responsive `flex-col sm:flex-row` stack. The Ticket Price section now displays on mobile (previously `hidden sm:block`), separated by a subtle border line.
- **Backend Event APIs**: Updated `/api/events` and `/api/events/{id}` SQL queries to join and return `host_is_founding` from the hosts table. Updated `/api/admin/hosts` to return `is_founding` per host.


## [2026-07-03] - Professional Services & Sports Expansion

### Added
- **Homepage Containers**: Added two premium-styled product containers for **Professional Services** (`প্রফেশনাল সার্ভিসেস`) and **Sports** (`স্পোর্টস`) directly above the Travel section in `index.html`. 
- **Smart Hiding Logic**: Implemented dynamic Javascript hiding logic in `renderCatalogGrid()` so that if the server returns 0 active events for Travel, Sports, or Professional Services, their entire HTML section wrappers cleanly hide from the DOM, maintaining a polished UI.

### Changed
- **Host Forms Category Injection**: Added `Professional Services` to the category dropdowns in `host_event_create.html` and `host_event_edit.html`.
- **Dateless Forms UI**: Injected a JS listener into both host forms that dynamically hides the "Date & Time" input and strips its required validation whenever "Professional Services" is selected.
- **Dateless Booking UI**: Upgraded `index.html` event cards and the `booking.html` details view to explicitly hide the calendar/date badges for the `professional` category, avoiding confusing "TBA" strings for one-off service purchases.
- **Backend Schema Patch**: Decoupled `event_date` as a required string in `models.py` (`EventCreate` schema is now `Optional[str]`), and updated `main.py` event processing to safely store `NULL` in the Postgres database if the frontend omits a date, overriding the old +7 day fallback logic.

## [2026-07-03] - Global Footer Update & Brand Polish

### Changed
- **Global Footer Links**: Refactored the footer across the entire platform. Removed the outdated "Language / ভাষা" column and hidden Google Translate widget. Replaced it with a new **"Company"** column featuring the "About DekhaHok" and "Contact Support" links.
- **Standalone Pages Synchronization**: Synchronized the new footer structure directly into the 7 standalone pages (`about.html`, `contact.html`, `host_guidelines.html`, `partnership.html`, `privacy_policy.html`, `safety.html`, `terms.html`) that don't natively inherit the `base.html` layout.
- **Brand Positioning Copy**: Updated browser tab titles (`<title>`) in `DekhaHok.html` and `index.html` to reflect the new platform positioning: **"DekhaHok • Social Community & Services"**.
- **Hero Text Upgrade**: Replaced the previous hero headline gradient text in `index.html` from "সোশাল মিডিয়া..." to **"সোশাল কমিউনিটি ও প্রফেশনাল সার্ভিসেস।"**.
- **Partnership Copy Shift**: Updated the partnership form description in `partnership.html` to target a broader audience ("বাস্তব অভিজ্ঞতা ও প্রফেশনাল সার্ভিসেসের ভেন্যু পার্টনার হতে...") instead of limiting it just to restaurants and cafes.
- **Support CTA Module**: Retouched the support section in the homepage `index.html` with updated Bengali badges, headings, and a refined tagline.

## [2026-07-01] - Animated Brand Logo, Trust Vibe Sync, Google OAuth & Onboarding Redesign

### Added
- **Animated Brand Logo SVG**: Built a self-contained inline SVG using SMIL animations that translates the hero's connection paths, glowing nodes, and outward pulse wave natively. Colors are set to brand green (#10B981), purple (#A855F7), and trust deep blue (#3B82F6).
- **Navbar & Menu Placement**: Integrated the animated logo next to (to the right of) the static Bangla brand text logo (`dekhahok_bn.svg`) on both the desktop header navbar and the mobile menu drawer.
- **Vertically Stacked Logo Lockup**: Designed a vertically stacked brand lockup displaying the animated SVG logo on top and the Bangla logo text centered directly below it. Applied this unified branding at the top of the Global Auth Modal and the Host Onboarding Sign-In panel.
- **Inline Host Apply Authentication**: Replaced the default forced login barrier on the host application page (`templates/host_apply.html`) with an interactive, tabbed inline Login/Signup form panel featuring custom Bengali copy and hidden English SEO crawler synonyms.
- **Standalone Sub-Page Sync**: Injected the blue-themed animated brand logo SVG into the navigation headers and changed the bottom row copy-pasted footer heart SVG classes from rose red to diamond blue (`text-sky-400`) on `terms.html`, `safety.html`, `privacy_policy.html`, `partnership.html`, `host_guidelines.html`, `about.html`, and `contact.html`. Removed references to the legacy bubble icon (`dekhahok_logo.svg`) in their headers.

### Changed
- **Home Page Hero Subtitle**: Updated the sub-navigation hero badge text in `templates/index.html` from "Now live in Dhaka City" to **"Beyond the digital bubble."** to align with the overarching platform mission.
- **Hero Canvas Dots Color Sync**: Recolor the moving node dots on the home page hero animation canvas to emerald green, purple, and blue-500, aligning with the new navigation brand color system.
- **Official Google Brand G Logo**: Upgraded the fragmented Google login SVGs to the official, color-accurate Google G logo in `base.html` (modal), `auth.html` (login page), and `host_apply.html` (onboarding).
- **Passport Section Mobile Layout**: Centered the "Get Passport" box in the DekhaHok Passport membership section on mobile screens by applying `text-center md:text-right` to its parent wrapper.

## [2026-06-28] - After-Merge Fixes, Subpage Translation Sync & Database Startup Fix

### Added
- **New Guidelines Pages**: Created `templates/safety.html` (Safety Guidelines) and `templates/host_guidelines.html` (Host Agreement) with tailored green styling, custom SEO metadata tags, and floating WhatsApp buttons. Registered their corresponding FastAPI routes `/safety` and `/host-guidelines` in `main.py`.
- **Event Brief Description on Booking Details**: Appended a brief description container into the selection card of `templates/booking.html`, populated dynamically on load.

### Changed
- **Subpage Footer Synchronization**: Replaced outdated footers on all custom sub-pages (`privacy_policy.html`, `terms.html`, `about.html`, `contact.html`, `partnership.html`, `safety.html`, `host_guidelines.html`) with the homepage's unified footer layout, complete with translation capability (En / Bn language toggle button via Google Translate widget).
- **Newline-Separated Included Items**: Modified form parsing logic and input guidelines in both `host_event_create.html` and `host_event_edit.html` to allow hosts to input experience perks line-by-line (using newlines instead of commas). Enhanced the FastAPI edit route to populate the textarea dynamically using newline joining.
- **Brief Description Restrained**: Set `maxlength="150"` constraint on the Brief Description textarea across the host create and edit event pages to keep descriptions concise.
- **Dynamic sitemap.xml Expansion**: Updated `/sitemap.xml` dynamic generation route to include the two new static pages `/safety` and `/host-guidelines`.

### Fixed
- **Favicon 404 Route**: Resolved favicon fetch failures on custom sub-pages by registering a direct `/favicon.ico` route in the backend returning the static favicon asset.
- **Default Event Startup Restoration Loop**: Solved a bug in the startup routine `init_db()` in `database.py` where the default "DekhaHok Circle Adda" event (previously deleted from the admin dashboard) was continuously re-created due to bookings with `event_id IS NULL` triggering the legacy migration block. Integrated a persistent site setting flag `'legacy_bookings_migrated'` to bypass the check after initial completion.

## [2026-06-27] - Admin Event Deletion, Payment Method Expansion & Contact Update

### Added
- **Admin Event Deletion:** Added a DELETE endpoint (`/api/admin/events/{event_id}`) in the backend to allow administrators to permanently delete draft/unpublished events. Published events are restricted from deletion.
- **Admin Delete Event UI:** Integrated a Trash icon delete button into the admin dashboard events table. It prompts for confirmation via `customConfirm` and handles soft-blocking deletion of published events.
- **DBBL & Upay Payment Options:** Expanded the checkout page's payment method options by adding DBBL and Upay. Included support for validating `dbbl` in `models.py`.

### Changed
- **Support WhatsApp & Phone Number Update:** Updated the platform's support contact number from `+880 1884-477720` to `+880 1325-900906` across the `base.html` float button, SEO metadata, contact page, and `README.md`.
- **Checkout Payment Selection UI:** Redesigned the payment selection buttons on the booking page into a grid layout to cleanly support bKash, Nagad, DBBL, and Upay options.
- **Admin Event Date Display:** Polish event date presentation in the admin dashboard events list by formatting it using `.toLocaleString()` instead of plain string slice.

## [2026-06-27] - Bug Fixes: Host Edit Data Recall & API Memory Fix

### Fixed
- **Host Event Edit Recall:** Fixed an issue where the host dashboard edit page (`/host/events/{id}/edit`) failed to recall the previously saved `included` perks and `category` from the database due to a PostgreSQL `JSONB` array conversion error and strict casing in javascript.
- **API Events Memory Crash (500 Error):** Fixed a critical `500 Internal Server Error` (MemoryError) in the `/api/events` endpoint that occurred after publishing an event with a large Base64 image payload. Replaced raw image fetching with a boolean check to drastically reduce memory usage.
- **Template Rendering Crash (500 Error):** Fixed an issue in `user_context_processor` where `created_at` timestamps were converted to strings prematurely, causing `local_time_filter` to crash the entire application when a user with unread notifications logged in.

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
