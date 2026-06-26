# Combined Implementation Plans (Claude & GPT)

This document combines the implementation plans and development specifications from both AI models:
- **Source 1:** [Plan from claude.txt](file:///c:/Users/Sumon/Desktop/Concept/Plan%20from%20claude.txt)
- **Source 2:** [plan from gpt.txt](file:///c:/Users/Sumon/Desktop/Concept/plan%20from%20gpt.txt)

---

# PART 1: Plan from Claude

# DekhaHok — Implementation Plan
## Upgrading `index.html` SPA → FastAPI + Jinja Marketplace

**Branch:** `feature/host-marketplace`  
**Current state:** Single-page app, all data hardcoded in JS (`allEvents[]`, `hostEvents[]`, `bookings[]` arrays inside the HTML file). No backend integration yet.  
**Target state:** Same UI, same design — but every array replaced with live DB queries, every form wired to FastAPI routes, every view split into a proper Jinja template.

---

## Guiding principle
> **Do not redesign. Wire up.**  
> The uploaded `index.html` is already the target UI. The job is to pull its hardcoded JS data out and replace it with real FastAPI endpoints + Neon DB queries — without changing how anything looks or feels.

---

## What exists in the current `index.html`

| View | ID | What it does |
|---|---|---|
| Home | `home-view` | Hero, event catalog, packages, passport, host CTA |
| Host onboarding | `host-onboarding-view` | 4-step form: profile → approval → event create → publish |
| Booking flow | `booking-view` | 4-step: personal info → tickets + bKash → confirm → success |
| Host dashboard | `dashboard-view` | Stats, upcoming events, attendee management, create event modal |
| Admin panel | `admin-view` | Hosts table, events table, bookings table, approve/reject |

**All data currently lives in these JS variables** (lines 1992–2158):
```
allEvents[]     → 8 hardcoded events
hostEvents[]    → 2 hardcoded host events with attendees
bookings[]      → inside admin panel
hosts[]         → inside admin panel
```

**Key JS functions to keep as-is** (just swap their data source):
```
renderEvents(events)          → keep, feed from API
openBooking(eventId)          → keep, fetch event from API
simulateBookingPayment()      → replace with real bKash call
renderAdminDashboard()        → keep, feed from API
approveHost(id)               → wire to POST /admin/hosts/{id}/approve
renderHostEvents()            → keep, feed from API
submitCreatedDashboardEvent() → wire to POST /host/events/create
```

---

## Step 0 — Git setup

```bash
git checkout main
git pull origin main
git checkout -b feature/host-marketplace
```

Do all work in this branch. Never touch `main` until tested end-to-end.

---

## Step 1 — Database migrations
**Run once on Neon** (add to a `migrations/002_marketplace.sql` file)

```sql
-- HOSTS
CREATE TABLE IF NOT EXISTS hosts (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    email         VARCHAR(200) UNIQUE NOT NULL,
    phone         VARCHAR(20),
    category      VARCHAR(20) NOT NULL CHECK (category IN ('creative','professional','lifestyle')),
    bio           TEXT,
    avatar_url    TEXT,
    social_links  JSONB DEFAULT '{}',
    past_experience TEXT,
    why_host      TEXT,
    status        VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','suspended')),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- EVENTS
CREATE TABLE IF NOT EXISTS events (
    id              SERIAL PRIMARY KEY,
    host_id         INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    slug            VARCHAR(250) UNIQUE NOT NULL,
    title           VARCHAR(300) NOT NULL,
    description     TEXT,
    category        VARCHAR(20) NOT NULL CHECK (category IN ('creative','professional','lifestyle','tour')),
    package_tier    VARCHAR(20) NOT NULL CHECK (package_tier IN ('circle','experience','premium')),
    price_per_person INTEGER NOT NULL,
    capacity        INTEGER NOT NULL DEFAULT 10,
    booked_count    INTEGER DEFAULT 0,
    location_name   VARCHAR(300),
    location_area   VARCHAR(100),
    event_date      TIMESTAMPTZ,
    image_url       TEXT,
    included        JSONB DEFAULT '[]',
    status          VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft','published','completed','cancelled')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Add marketplace columns to existing documents/bookings table
-- (keep existing columns — only ADD new ones)
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS event_id      INTEGER REFERENCES events(id),
    ADD COLUMN IF NOT EXISTS host_id       INTEGER REFERENCES hosts(id),
    ADD COLUMN IF NOT EXISTS package_tier  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS price_paid    INTEGER,
    ADD COLUMN IF NOT EXISTS attendee_count INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS vibe_tags     TEXT[],
    ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'bkash',
    ADD COLUMN IF NOT EXISTS payment_status VARCHAR(20) DEFAULT 'pending';

-- REVIEWS
CREATE TABLE IF NOT EXISTS reviews (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER REFERENCES events(id),
    host_id         INTEGER REFERENCES hosts(id),
    tracking_id     VARCHAR(50),
    rating          INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_events_status   ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_host     ON events(host_id);
CREATE INDEX IF NOT EXISTS idx_hosts_status    ON hosts(status);
CREATE INDEX IF NOT EXISTS idx_reviews_event   ON reviews(event_id);
```

---

## Step 2 — Split `index.html` into Jinja templates

The current file is one giant HTML file. Split it into proper templates that FastAPI can render.

```
templates/
  base.html              ← nav + footer shell
  index.html             ← home view (hero + catalog + packages)
  host_apply.html        ← host onboarding 4-step form
  host_dashboard.html    ← host dashboard + sidebar
  booking.html           ← booking 4-step flow
  admin.html             ← admin panel (password-protected)
  track.html             ← existing tracking page (keep as-is)
```

**`base.html` gets:** nav, footer, all `<link>` and `<script>` tags, Tailwind config.

**Each view template** `{% extends "base.html" %}` and fills `{% block content %}`.

**Critical:** keep all existing CSS class names exactly. Do not refactor Tailwind classes. The design is done.

---

## Step 3 — FastAPI routes to add

Add these to your existing `main.py`. **Do not remove existing routes.**

```python
# ─── DEPENDENCIES ─────────────────────────────
import json, re, datetime
from fastapi import Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

# ─── HOME ─────────────────────────────────────
@app.get("/")
async def home(request: Request):
    async with pool.acquire() as conn:
        events = await conn.fetch("""
            SELECT e.*, h.name as host_name, h.avatar_url as host_avatar,
                   h.category as host_category,
                   (e.capacity - e.booked_count) as spots_left
            FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            WHERE e.status = 'published'
            ORDER BY e.event_date ASC
            LIMIT 12
        """)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "events": events
    })

# ─── EVENTS API (for JS fetch calls) ──────────
@app.get("/api/events")
async def api_events(category: str = None):
    async with pool.acquire() as conn:
        query = """
            SELECT e.*, h.name as host_name, h.avatar_url,
                   (e.capacity - e.booked_count) as spots_left
            FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            WHERE e.status = 'published'
        """
        params = []
        if category:
            query += f" AND e.category = $1"
            params.append(category)
        query += " ORDER BY e.event_date ASC"
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]

@app.get("/api/events/{event_id}")
async def api_event_detail(event_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT e.*, h.name as host_name, h.avatar_url, h.bio as host_bio,
                   (e.capacity - e.booked_count) as spots_left
            FROM events e LEFT JOIN hosts h ON e.host_id = h.id
            WHERE e.id = $1 AND e.status = 'published'
        """, event_id)
    if not row:
        raise HTTPException(404)
    return dict(row)

# ─── BOOKING ─────────────────────────────────
@app.post("/api/book")
async def api_book(
    event_id:       int   = Form(...),
    name:           str   = Form(...),
    email:          str   = Form(...),
    phone:          str   = Form(...),
    preferences:    str   = Form(default=""),
    vibe_tags:      str   = Form(default=""),
    attendee_count: int   = Form(default=1),
    payment_method: str   = Form(default="bkash"),
):
    # Generate tracking ID (keep existing format DH-XXXXXXXX)
    import random, string
    tracking_id = "DH-" + ''.join(random.choices(string.digits, k=8))
    
    async with pool.acquire() as conn:
        event = await conn.fetchrow(
            "SELECT * FROM events WHERE id=$1 AND status='published'", event_id
        )
        if not event:
            raise HTTPException(400, "Event not found")
        if event['booked_count'] + attendee_count > event['capacity']:
            raise HTTPException(400, "Not enough spots")
        
        price_paid = event['price_per_person'] * attendee_count
        tags = [t.strip() for t in vibe_tags.split(',') if t.strip()]
        
        await conn.execute("""
            INSERT INTO documents
            (name, email, phone, message, status, tracking_id,
             event_id, host_id, package_tier, price_paid,
             attendee_count, vibe_tags, payment_method, payment_status)
            VALUES ($1,$2,$3,$4,'pending',$5,$6,$7,$8,$9,$10,$11,$12,'pending')
        """, name, email, phone, preferences, tracking_id,
             event_id, event['host_id'], event['package_tier'],
             price_paid, attendee_count, tags, payment_method)
        
        # Increment booked_count
        await conn.execute(
            "UPDATE events SET booked_count = booked_count + $1 WHERE id = $2",
            attendee_count, event_id
        )
    
    return JSONResponse({"tracking_id": tracking_id, "price_paid": price_paid})

# ─── HOST APPLY ───────────────────────────────
@app.get("/host")
async def host_page(request: Request):
    return templates.TemplateResponse("host_apply.html", {"request": request})

@app.post("/api/host/apply")
async def host_apply(
    name:            str = Form(...),
    email:           str = Form(...),
    phone:           str = Form(...),
    category:        str = Form(...),
    bio:             str = Form(...),
    past_experience: str = Form(default=""),
    why_host:        str = Form(...),
    social_links:    str = Form(default="{}"),
):
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM hosts WHERE email=$1", email
        )
        if existing:
            return JSONResponse({"error": "Email already applied"}, status_code=400)
        
        host_id = await conn.fetchval("""
            INSERT INTO hosts (name,email,phone,category,bio,past_experience,why_host,social_links)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING id
        """, name, email, phone, category, bio, past_experience, why_host,
             json.loads(social_links or "{}"))
    
    return JSONResponse({"success": True, "host_id": host_id})

# ─── HOST DASHBOARD ───────────────────────────
@app.get("/host/dashboard")
async def host_dashboard(request: Request, host_id: int):
    # TODO Month 2: replace with cookie/session auth
    async with pool.acquire() as conn:
        host = await conn.fetchrow(
            "SELECT * FROM hosts WHERE id=$1 AND status='approved'", host_id
        )
        if not host:
            return RedirectResponse("/host")
        
        events = await conn.fetch(
            "SELECT * FROM events WHERE host_id=$1 ORDER BY created_at DESC", host_id
        )
        
        # Revenue: Experience/Premium = 50% share, Circle = 30%
        earnings = await conn.fetchval("""
            SELECT COALESCE(SUM(
                CASE package_tier
                    WHEN 'circle'     THEN price_paid * 0.30
                    WHEN 'experience' THEN price_paid * 0.50
                    WHEN 'premium'    THEN price_paid * 0.50
                    ELSE 0
                END
            ), 0)
            FROM documents WHERE host_id=$1 AND payment_status='paid'
        """, host_id)
        
        # Attendees per event
        bookings = await conn.fetch("""
            SELECT event_id, name, email, phone, vibe_tags, attendee_count,
                   price_paid, tracking_id, payment_status, created_at
            FROM documents
            WHERE host_id=$1
            ORDER BY created_at DESC
        """, host_id)
    
    return templates.TemplateResponse("host_dashboard.html", {
        "request": request,
        "host": host,
        "events": events,
        "earnings": int(earnings),
        "bookings": bookings
    })

@app.post("/api/host/events/create")
async def host_create_event(
    host_id:         int  = Form(...),
    title:           str  = Form(...),
    description:     str  = Form(...),
    category:        str  = Form(...),
    package_tier:    str  = Form(...),
    price_per_person:int  = Form(...),
    capacity:        int  = Form(...),
    location_name:   str  = Form(...),
    location_area:   str  = Form(...),
    event_date:      str  = Form(...),
    included:        str  = Form(default="[]"),
):
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    slug += f"-{int(datetime.datetime.now().timestamp())}"
    
    async with pool.acquire() as conn:
        host = await conn.fetchrow(
            "SELECT id FROM hosts WHERE id=$1 AND status='approved'", host_id
        )
        if not host:
            raise HTTPException(403, "Not an approved host")
        
        await conn.execute("""
            INSERT INTO events
            (host_id, slug, title, description, category, package_tier,
             price_per_person, capacity, location_name, location_area,
             event_date, included, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'draft')
        """, host_id, slug, title, description, category, package_tier,
             price_per_person, capacity, location_name, location_area,
             datetime.datetime.fromisoformat(event_date),
             json.loads(included or "[]"))
    
    return JSONResponse({"success": True, "slug": slug})

# ─── ADMIN ────────────────────────────────────
ADMIN_TOKEN = "your_secret_token_here"  # move to env var

@app.get("/admin")
async def admin_page(request: Request, token: str = ""):
    if token != ADMIN_TOKEN:
        return templates.TemplateResponse("admin_login.html", {"request": request})
    async with pool.acquire() as conn:
        hosts    = await conn.fetch("SELECT * FROM hosts ORDER BY created_at DESC")
        events   = await conn.fetch("""
            SELECT e.*, h.name as host_name FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            ORDER BY e.created_at DESC
        """)
        bookings = await conn.fetch("""
            SELECT d.*, e.title as event_title FROM documents d
            LEFT JOIN events e ON d.event_id = e.id
            ORDER BY d.created_at DESC LIMIT 100
        """)
        stats = {
            "volume":  await conn.fetchval("SELECT COALESCE(SUM(price_paid),0) FROM documents WHERE payment_status='paid'"),
            "hosts":   await conn.fetchval("SELECT COUNT(*) FROM hosts WHERE status='approved'"),
            "events":  await conn.fetchval("SELECT COUNT(*) FROM events WHERE status='published'"),
            "tickets": await conn.fetchval("SELECT COUNT(*) FROM documents"),
        }
    return templates.TemplateResponse("admin.html", {
        "request": request, "token": token,
        "hosts": hosts, "events": events,
        "bookings": bookings, "stats": stats
    })

@app.post("/api/admin/hosts/{host_id}/approve")
async def admin_approve_host(host_id: int, token: str = Form(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(403)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE hosts SET status='approved' WHERE id=$1", host_id
        )
    return JSONResponse({"success": True})

@app.post("/api/admin/hosts/{host_id}/reject")
async def admin_reject_host(host_id: int, token: str = Form(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(403)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE hosts SET status='rejected' WHERE id=$1", host_id
        )
    return JSONResponse({"success": True})

@app.post("/api/admin/events/{event_id}/publish")
async def admin_publish_event(event_id: int, token: str = Form(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(403)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status='published' WHERE id=$1", event_id
        )
    return JSONResponse({"success": True})

@app.post("/api/admin/events/{event_id}/cancel")
async def admin_cancel_event(event_id: int, token: str = Form(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(403)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status='cancelled' WHERE id=$1", event_id
        )
    return JSONResponse({"success": True})
```

---

## Step 4 — Wire the JS in `index.html` to the API

The existing JS functions stay intact. Replace their hardcoded data with `fetch()` calls.

### 4a. Replace `allEvents[]` with API call

Find this in `index.html` (line 1992):
```javascript
let allEvents = [ { id: 1, title: "Dhaka Street Photography Walk", ... } ];
```

Replace with:
```javascript
let allEvents = [];
let displayedEvents = [];

async function loadEvents() {
    try {
        const res = await fetch('/api/events');
        allEvents = await res.json();
        // Map DB fields to what renderEvents() expects
        allEvents = allEvents.map(e => ({
            id:          e.id,
            title:       e.title,
            category:    e.category,
            host:        e.host_name || 'DekhaHok Host',
            hostAvatar:  e.avatar_url || `https://api.dicebear.com/7.x/adventurer/svg?seed=${e.host_name}`,
            date:        e.event_date ? new Date(e.event_date).toLocaleDateString('en-GB', {day:'numeric',month:'short'}) : 'TBA',
            time:        e.event_date ? new Date(e.event_date).toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit'}) : '',
            location:    e.location_name || e.location_area,
            price:       e.price_per_person,
            spotsLeft:   e.spots_left,
            image:       e.image_url || `https://picsum.photos/seed/${e.id}/600/400`,
            fallbackImage: `https://picsum.photos/seed/${e.id}/600/400`,
            type:        e.package_tier === 'circle' ? 'Circle' : e.package_tier === 'premium' ? 'Premium' : 'Experience',
            description: e.description || ''
        }));
        displayedEvents = [...allEvents];
        renderEvents(displayedEvents);
    } catch(err) {
        console.error('Failed to load events:', err);
        // Graceful fallback — keep static data if API fails
    }
}
```

Then in `window.onload` (line 3407), replace:
```javascript
// OLD:
renderEvents(allEvents);

// NEW:
loadEvents();
```

### 4b. Replace `openBooking()` to fetch live event

Find `openBooking` (line 2450):
```javascript
// OLD: finds from local array
const event = allEvents.find(e => e.id === eventId);

// NEW: fetch live data but keep fallback
async function openBooking(eventId) {
    try {
        const res = await fetch(`/api/events/${eventId}`);
        const e = await res.json();
        selectedBookingEvent = {
            id:          e.id,
            title:       e.title,
            price:       e.price_per_person,
            spotsLeft:   e.spots_left,
            location:    e.location_name,
            image:       e.image_url || `https://picsum.photos/seed/${e.id}/600/400`,
            fallbackImage: `https://picsum.photos/seed/${e.id}/600/400`,
            type:        e.package_tier,
            ...
        };
    } catch {
        // fallback to local array (keeps working offline)
        selectedBookingEvent = allEvents.find(ev => ev.id === eventId);
    }
    // rest of function unchanged
    showView('booking');
    ...
}
```

### 4c. Replace `simulateBookingPayment()` with real API call

Find `simulateBookingPayment` (line 2563):
```javascript
// OLD: setTimeout fake
// NEW:
async function simulateBookingPayment() {
    document.getElementById('booking-loading').classList.remove('hidden');
    document.getElementById('booking-success-box').classList.add('hidden');
    
    const formData = new FormData();
    formData.append('event_id',       selectedBookingEvent.id);
    formData.append('name',           document.getElementById('booking-name').value);
    formData.append('email',          document.getElementById('booking-email').value);
    formData.append('phone',          document.getElementById('booking-phone').value);
    formData.append('preferences',    document.getElementById('booking-preferences').value || '');
    formData.append('vibe_tags',      selectedVibeVal || '');
    formData.append('attendee_count', document.getElementById('booking-qty').value || 1);
    formData.append('payment_method', selectedPaymentMethodVal || 'bkash');
    
    try {
        const res  = await fetch('/api/book', { method: 'POST', body: formData });
        const data = await res.json();
        
        if (data.tracking_id) {
            document.getElementById('booking-loading').classList.add('hidden');
            document.getElementById('booking-success-box').classList.remove('hidden');
            // Inject tracking ID into success screen
            const tEl = document.getElementById('booking-tracking-id');
            if (tEl) tEl.textContent = data.tracking_id;
            // Update allEvents spot count locally
            const ev = allEvents.find(e => e.id === selectedBookingEvent.id);
            if (ev) ev.spotsLeft = Math.max(0, ev.spotsLeft - 1);
            renderEvents(displayedEvents);
        } else {
            showToast('Booking failed: ' + (data.error || 'Please try again'));
            document.getElementById('booking-loading').classList.add('hidden');
        }
    } catch(err) {
        showToast('Network error. Please try again.');
        document.getElementById('booking-loading').classList.add('hidden');
    }
}
```

### 4d. Wire host application form

Find `nextHostStep()` — Step 1 submits the form. Add API call:
```javascript
async function submitHostApplication() {
    const formData = new FormData();
    formData.append('name',            document.getElementById('host-name-input').value);
    formData.append('email',           document.getElementById('host-email-input').value);
    formData.append('phone',           document.getElementById('host-phone-input').value);
    formData.append('category',        document.getElementById('host-category-input').value);
    formData.append('bio',             document.getElementById('host-bio-input').value);
    formData.append('past_experience', document.getElementById('host-experience-input').value);
    formData.append('why_host',        document.getElementById('host-why-input').value);
    
    const res = await fetch('/api/host/apply', { method: 'POST', body: formData });
    const data = await res.json();
    
    if (data.success) {
        localStorage.setItem('dh_host_id', data.host_id);
        nextHostStep(); // proceeds to "Application Received" screen
    } else {
        showToast(data.error || 'Application failed. Try again.');
    }
}
```

### 4e. Wire host event creation

Find `publishHostEvent()` / `submitCreatedDashboardEvent()`:
```javascript
async function publishHostEvent() {
    const hostId = localStorage.getItem('dh_host_id');
    const formData = new FormData();
    formData.append('host_id',          hostId);
    formData.append('title',            document.getElementById('host-event-title').value);
    formData.append('description',      document.getElementById('host-event-desc').value);
    formData.append('category',         document.getElementById('host-category-input').value);
    formData.append('package_tier',     document.getElementById('host-package-tier').value);
    formData.append('price_per_person', document.getElementById('host-event-price').value);
    formData.append('capacity',         document.getElementById('host-event-capacity').value);
    formData.append('location_name',    document.getElementById('host-event-location').value);
    formData.append('location_area',    document.getElementById('host-area-input').value);
    formData.append('event_date',       document.getElementById('host-event-date').value + 'T' + document.getElementById('host-event-time').value);
    formData.append('included',         JSON.stringify(document.getElementById('host-event-included').value.split('\n').filter(Boolean)));
    
    const res  = await fetch('/api/host/events/create', { method: 'POST', body: formData });
    const data = await res.json();
    
    if (data.success) {
        nextHostStep(); // goes to success screen
    } else {
        showToast(data.error || 'Event creation failed');
    }
}
```

### 4f. Wire admin panel

In `renderAdminDashboard()`, replace hardcoded arrays with fetch:
```javascript
async function renderAdminDashboard() {
    const token = new URLSearchParams(window.location.search).get('token') || '';
    const res = await fetch(`/api/admin/data?token=${token}`);
    if (!res.ok) { showToast('Admin access denied'); return; }
    const data = await res.json();
    
    // Update stat cards
    document.getElementById('admin-stat-volume').textContent = '৳' + data.stats.volume.toLocaleString();
    document.getElementById('admin-stat-hosts').textContent  = data.stats.hosts;
    document.getElementById('admin-stat-events').textContent = data.stats.events;
    document.getElementById('admin-stat-tickets').textContent = data.stats.tickets;
    
    // Render tables using existing table-building code
    renderAdminHostsTable(data.hosts);
    renderAdminEventsTable(data.events);
    renderAdminBookingsTable(data.bookings);
}

// Wire approve/reject buttons
async function approveHost(id) {
    const token = new URLSearchParams(window.location.search).get('token') || '';
    const fd = new FormData(); fd.append('token', token);
    await fetch(`/api/admin/hosts/${id}/approve`, { method: 'POST', body: fd });
    showToast('Host approved ✓');
    renderAdminDashboard();
}
```

---

## Step 5 — Dynamic sitemap

Replace the static `sitemap.xml` file with a route:

```python
@app.get("/sitemap.xml")
async def sitemap():
    async with pool.acquire() as conn:
        events = await conn.fetch(
            "SELECT slug, created_at FROM events WHERE status='published'"
        )
    base = "https://dekhahok.com"
    urls = [
        (f"{base}/",         "1.0", "daily"),
        (f"{base}/#catalog", "0.9", "daily"),
        (f"{base}/host",     "0.8", "monthly"),
        (f"{base}/about",    "0.6", "monthly"),
    ]
    for e in events:
        urls.append((
            f"{base}/events/{e['slug']}",
            "0.8",
            e['created_at'].strftime('%Y-%m-%d')
        ))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f"  <url><loc>{u[0]}</loc>"
        if len(u) == 3 and '-' in str(u[2]):
            xml += f"<lastmod>{u[2]}</lastmod>"
        xml += f"<changefreq>{u[1] if '-' not in str(u[1]) else 'weekly'}</changefreq></url>\n"
    xml += '</urlset>'
    from fastapi.responses import Response
    return Response(content=xml, media_type="application/xml")
```

---

## Step 6 — Seed the DB with the 8 hardcoded events

Run this once to seed your events table from the JS data, so the catalog isn't empty on launch:

```sql
-- First create a system host
INSERT INTO hosts (name, email, phone, category, bio, status)
VALUES ('DekhaHok Team', 'team@dekhahok.com', '+8801884477720', 'creative', 'Official DekhaHok events', 'approved')
ON CONFLICT (email) DO NOTHING;

-- Seed events (map from JS allEvents array)
INSERT INTO events (host_id, slug, title, description, category, package_tier, price_per_person, capacity, booked_count, location_name, location_area, event_date, status)
SELECT h.id, 'dhaka-street-photography-walk', 'Dhaka Street Photography Walk',
'Learn street photography techniques while exploring Dhanmondi Lake, ending with hot tea and adda.',
'creative', 'experience', 499, 12, 8, 'Dhanmondi Lake', 'Dhanmondi',
NOW() + INTERVAL '3 days', 'published'
FROM hosts h WHERE h.email = 'team@dekhahok.com';

-- (repeat for each of the 8 events from allEvents[])
```

---

## Step 7 — Environment & deployment

### Add to `.env` / GCR secrets
```
DB_URL=postgresql://neondb_owner:...@ep-withered-king-a1t4j4mz-pooler.ap-southeast-1.aws.neon.tech/neondb
ADMIN_TOKEN=your_secure_random_token_here
```

### `Dockerfile` — no changes needed
The existing GCR setup works. Just add the new routes to `main.py` and new templates to `templates/`.

### GCR deploy command
```bash
gcloud run deploy dekhahok \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated
```

---

## Step 8 — Testing checklist before merge to main

```
[ ] Home loads with real events from DB
[ ] Category filter (creative/professional/lifestyle/tour) works
[ ] openBooking() fetches live event data
[ ] Booking form → /api/book → tracking ID returned
[ ] Tracking page shows booking from DB
[ ] Host apply form → /api/host/apply → inserted to hosts table
[ ] Admin panel loads at /admin?token=xxx
[ ] Admin can approve a host
[ ] Approved host can create event at /api/host/events/create
[ ] Created event appears as draft in admin
[ ] Admin publishes event → appears on homepage catalog
[ ] Sitemap.xml includes published events
[ ] Mobile nav still works
[ ] bKash step shows (payment_method=bkash stored in DB)
```

---

## What NOT to do yet

| Skip | Reason |
|---|---|
| Real bKash/SSLCommerz integration | Manual payment verification works at this scale. Add in Month 2 |
| Auth / login system | `host_id` via localStorage + query param is sufficient now |
| Matching algorithm | Manual matching by admin is fine for first 20 events |
| Email/SMS notifications | Add after core flow works |
| Image upload | Use external URL field first; S3 upload in Month 2 |
| React/Next.js rewrite | Current Tailwind SPA works fine. Don't touch it |

---

## Month-by-month build priority

| Month | What to build |
|---|---|
| **Now** | Steps 1–8 above. DB wired, booking working, admin functional |
| **2** | Auth (email magic link), SSLCommerz, host email notification on approval |
| **3** | Passport membership (recurring payment), matching score, host public profiles |
| **4+** | Analytics dashboard, review system, referral program |

---

## File summary — what changes, what doesn't

| File | Action |
|---|---|
| `main.py` | Add ~15 new routes (Steps 3 + 5) |
| `templates/index.html` | Convert from standalone SPA to `{% extends "base.html" %}` |
| `templates/base.html` | New — extract nav/footer/scripts from index.html |
| `templates/host_apply.html` | New — extract host-onboarding-view |
| `templates/host_dashboard.html` | New — extract dashboard-view |
| `templates/admin.html` | New — extract admin-view |
| `static/js/main.js` | Extract JS from bottom of index.html, add fetch() wires (Steps 4a–4f) |
| `migrations/002_marketplace.sql` | New — Step 1 SQL |
| `sitemap.xml` → route | Replace static file with dynamic route |
| **Everything else** | Unchanged — existing booking, tracking, bKash flow untouched |

---

# PART 2: Plan from GPT

First, I want to acknowledge the current stage of DekhaHok because it changes the engineering priorities.

You are **not building an MVP anymore**. You already have:

* a working deployed product,
* a validated UI concept,
* real users,
* successful offline events,
* payment/bookings flow,
* host/community model direction.

The next engineering goal is **not more screens**. It is converting the current prototype into a **scalable community marketplace platform**.

I reviewed the attached `index.html`. It already contains the core product vision:

* event discovery feed,
* booking flow,
* host onboarding,
* host dashboard,
* admin moderation,
* pricing packages,
* safety agreement flow. 
  It also already models host revenue sharing and event creation concepts, which align with the marketplace direction we discussed. 

The current file is essentially a **high-fidelity functional prototype** using Tailwind + JavaScript state simulation.  The next phase should separate this into a proper production architecture.

---

# DekhaHok Platform Upgrade Implementation Plan

## Phase 0 — Codebase Stabilization (Week 1)

### Goal:

Move from prototype → maintainable product.

### Current issue:

Everything is inside `index.html`.

Problems:

* impossible to scale
* difficult debugging
* no real database
* no authentication
* no analytics

---

## Recommended stack

Since you already deployed on Google Cloud Run:

### Frontend

Keep:

* React + Tailwind
* TypeScript

Migration:

```
index.html
        ↓
React components
        ↓
Reusable UI system
```

Structure:

```
src/

components/
 ├── EventCard
 ├── BookingCard
 ├── HostCard
 ├── SafetyBadge

pages/
 ├── Home
 ├── EventDetails
 ├── Booking
 ├── HostDashboard
 ├── AdminDashboard

services/
 ├── api.js
 ├── payment.js

hooks/
 ├── useAuth
 ├── useEvents
 ├── useBookings
```

---

# Phase 1 — Real Database System (Week 2-3)

Replace dummy arrays.

Currently:

```javascript
let allEvents = []
let allBookings = []
let hostEvents = []
```

Convert into database models.

---

## User Table

```
User

id
name
phone
email
gender
age_range
area
occupation
interests
privacy_preferences
created_at
```

---

## Event Table

```
Event

id
title
category
host_id
location
date
capacity
price
status
visibility
```

---

## Booking Table

```
Booking

id
user_id
event_id
payment_status
attendance_status
created_at
```

---

## Host Table

```
Host

id
user_id
category
verification_status
revenue_share
rating
```

---

# Phase 2 — Matching Engine (Most Important)

Do not over-engineer AI yet.

Start rule-based.

Your current biggest business risk:

"Can we fill events?"

---

Create:

## User Preference Score

Example:

```
Photography = +30
Food exploration = +20
Startup = +20

Same area = +20

Similar age group = +10

Available Friday = +20
```

Result:

```
User A
+
Event X

Match Score:
82%
```

Show:

"Recommended for you"

---

# Phase 3 — Host Marketplace System

This is where DekhaHok becomes different.

Current host UI direction is correct. The prototype already includes host application inputs and event publishing concepts. 

Build:

## Host Dashboard

### Host Home

```
Hello Rafi 👋

Your communities

Upcoming Events

Revenue

Reviews
```

---

## Create Event Wizard

Step 1:

```
Event Type

○ Photography Walk
○ Food Explorer
○ Book Circle
○ Startup Talk
○ Custom
```

Step 2:

```
Location
Date
Capacity
Price
Description
```

Step 3:

```
Publish
```

---

# Phase 4 — Trust & Safety System

This is your moat.

Your brandbook already emphasizes:

* Security
* Authenticity
* Community
* Privacy

as core values. 

Build:

## User Trust Score

```
Verified phone
+10

Completed meetup
+20

Positive reviews
+30

Reported issue
-50
```

---

Display:

```
✓ Verified Member

3 Meetups Completed
```

---

# Phase 5 — Privacy-First Event Experience

I actually think this is a differentiator.

Do NOT copy Instagram-style meetup culture.

Build:

After event:

Ask:

```
How was your experience?

⭐ ⭐ ⭐ ⭐ ⭐

Would you join another DekhaHok?
```

Then:

Anonymous stories:

> "Met 4 strangers. Left with new friends."

---

# Phase 6 — Community Growth Tools

For influencers/community leaders:

Create:

## Community Partner Dashboard

```
My Community

Members:
240

Events Hosted:
12

Revenue:
৳18,500

Impact:
85 people connected
```

---

# Phase 7 — Automation Layer

This is where your engineering interest matters.

Automate:

## Before event

24 hours before:

WhatsApp:

"Your DekhaHok experience is tomorrow 💚"

---

## After event

Automatically:

* feedback request
* review
* referral coupon

---

## Host payout

Automatic:

```
Event completed
 
↓


Revenue calculated

↓


Host payout generated
```

---

# 90-Day Development Roadmap

## Month 1 — Product Foundation

Priority:

1. React migration
2. Backend API
3. Database
4. Authentication
5. Payment integration

---

## Month 2 — Marketplace

Priority:

1. Host dashboard
2. Event creation
3. Matching algorithm
4. Reviews
5. Analytics

---

## Month 3 — Growth Engine

Priority:

1. Community partners
2. Referral system
3. Membership
4. AI recommendations

---

# Developer Task Priority List

Give the coder this order:

```
P0:
✓ Remove static data
✓ Build backend
✓ Database
✓ Authentication

P1:
✓ Real booking
✓ Payment
✓ Event management
✓ Host dashboard

P2:
✓ Matching engine
✓ Reviews
✓ Referral

P3:
✓ Community marketplace
✓ AI recommendations
✓ Expansion tools
```

---

# One strategic note

Don't turn DekhaHok into a "social media app".

Your advantage is that people **don't need another place to scroll**.

Your product loop should be:

```
Discover
 ↓
Join
 ↓
Meet
 ↓
Create memory
 ↓
Invite others
 ↓
More communities
```

The code should serve that loop.

The current UI concept already captures the right philosophy: safe, curated experiences rather than random chatting. The engineering upgrade should preserve that simplicity while building the infrastructure underneath. 

You have reached the interesting stage where the hardest problem is no longer "can we build it?" — it is "can we reliably create hundreds of meaningful human connections every month?" That's a much better problem to have.
