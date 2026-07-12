import os
import asyncio
import secrets
import string
import hashlib
import json
import hmac
import base64
import httpx
import re
from typing import Optional
from pydantic import BaseModel

from datetime import datetime, timedelta, time
from fastapi import FastAPI, HTTPException, Header, Query, Request, Response, Body, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from database import get_conn, release_conn, init_db
from models import (
    BookingCreate, BookingResponse, TrackingResponse,
    AdminBookingUpdate, GroupCreate, GroupAssign, GroupUpdate,
    LocationCreate, LocationResponse,
    MeetingPointCreate, MeetingPointResponse,
    RatingCreate, MessageCreate, PartnershipCreate, PartnershipUpdate,
    BlogCreate, BlogResponse, BlogUpdate, PublicGroupResponse,
    BlogCommentCreate, BlogCommentResponse,
    UserCreate, UserLogin, HostApply, EventCreate,
    SessionBookCreate, HireRequestCreate
)

load_dotenv()

app = FastAPI(title="DekhaHok API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join("static", "favicon.png"))


templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Cryptographic & Password Verification Helpers (Zero Dependencies)
# ---------------------------------------------------------------------------

SESSION_SECRET = os.getenv("SESSION_SECRET", "default_secret_key_12345").encode('utf-8')

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}:{pwd_hash.hex()}"

def verify_password(password: str, hashed_password: str) -> bool:
    if not hashed_password or ":" not in hashed_password:
        return False
    try:
        salt, stored_hash = hashed_password.split(":", 1)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return pwd_hash.hex() == stored_hash
    except Exception:
        return False

def get_avatar_for_user(full_name: str, email: str, gender: Optional[str] = None) -> str:
    import urllib.parse
    name_cleaned = urllib.parse.quote(full_name.strip() if full_name else "User")
    # Using a modern color palette for the background
    return f"https://ui-avatars.com/api/?name={name_cleaned}&background=047857&color=fff&size=150&bold=true&rounded=true"

def create_session_cookie(user_id: int, email: str, role: str) -> str:
    payload = json.dumps({"user_id": user_id, "email": email, "role": role})
    payload_b64 = base64.b64encode(payload.encode('utf-8')).decode('utf-8')
    sig = hmac.new(SESSION_SECRET, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_session_cookie(cookie_val: str) -> dict | None:
    if not cookie_val or "." not in cookie_val:
        return None
    try:
        payload_b64, sig = cookie_val.split(".", 1)
        expected_sig = hmac.new(SESSION_SECRET, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload_json = base64.b64decode(payload_b64.encode('utf-8')).decode('utf-8')
        return json.loads(payload_json)
    except Exception:
        return None

def get_current_user(dh_session: Optional[str] = Cookie(None)):
    if not dh_session:
        return None
    session_data = verify_session_cookie(dh_session)
    if not session_data:
        return None
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.email, u.role, u.full_name, u.avatar_url, h.experience_years
            FROM users u
            LEFT JOIN hosts h ON u.id = h.user_id
            WHERE u.id = %s
        """, (session_data["user_id"],))
        row = cursor.fetchone()
        cursor.close()
        if row:
            return {
                "user_id": row[0],
                "email": row[1],
                "role": row[2],
                "name": row[3],
                "avatar": f"/api/users/{row[0]}/avatar",
                "experience_years": row[5] or 0
            }
        return None
    finally:
        release_conn(conn)

def require_role(allowed_roles: list[str]):
    def dependency(user = Depends(get_current_user)):
        if not user:
            raise HTTPException(status_code=401, detail="Please log in to continue.")
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Access denied. Insufficient permissions.")
        return user
    return dependency

def user_context_processor(request: Request):
    dh_session = request.cookies.get("dh_session")
    user = None
    unread_notifications = []
    suggested_events = []
    if dh_session:
        user = get_current_user(dh_session)
        if user:
            conn = get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, type, title, message, action_url, created_at 
                    FROM notifications 
                    WHERE user_id = %s AND is_read = FALSE
                    ORDER BY created_at DESC LIMIT 5
                """, (user["user_id"],))
                rows = cursor.fetchall()
                for r in rows:
                    unread_notifications.append({
                        "id": r[0], "type": r[1], "title": r[2], 
                        "message": r[3], "action_url": r[4], "created_at": r[5]
                    })
                
                # Smart Suggestions for empty notifications
                if len(unread_notifications) == 0:
                    cursor.execute("""
                        SELECT id, title, category 
                        FROM events 
                        WHERE status = 'published'
                        ORDER BY RANDOM() LIMIT 3
                    """)
                    sugg_rows = cursor.fetchall()
                    for sr in sugg_rows:
                        suggested_events.append({"id": sr[0], "title": sr[1], "category": sr[2]})
                        
                cursor.close()
            except Exception:
                pass
            finally:
                release_conn(conn)
                
    return {"user": user, "unread_notifications": unread_notifications, "suggested_events": suggested_events}

def local_time_filter(dt):
    if not dt:
        return ""
    # Format e.g., "July 26, 08PM"
    formatted = dt.strftime("%B %d, %I%p")
    # Clean up leading zero in hour (08PM -> 8PM)
    formatted = formatted.replace(", 0", ", ")
    # Convert PM -> Pm, AM -> Am
    formatted = formatted.replace("AM", "Am").replace("PM", "Pm")
    return formatted

templates.context_processors.append(user_context_processor)
templates.env.filters["local_time"] = local_time_filter


@app.middleware("http")
async def seo_redirect_middleware(request: Request, call_next):
    host = request.headers.get("host", "").lower()
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    
    # 1. Force Non-WWW
    should_redirect = False
    new_host = host
    if host.startswith("www."):
        new_host = host.replace("www.", "", 1)
        should_redirect = True
    
    # 2. IP Canonicalization
    elif host == "188.114.97.3":
        new_host = "dekhahok.com"
        should_redirect = True

    # 3. Force HTTPS (Except for localhost/127.0.0.1)
    new_scheme = scheme
    if scheme == "http" and host != "localhost" and not host.startswith("127.0.0.1") and ":" not in host:
        new_scheme = "https"
        should_redirect = True

    if should_redirect:
        url = request.url.replace(scheme=new_scheme, netloc=new_host)
        return RedirectResponse(url=str(url), status_code=301)
        
    response = await call_next(request)
    
    # 3. Technical SEO Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # 4. Performance Caching for Static Assets
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        
    return response


@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return FileResponse("static/404.html", status_code=404)





@app.get("/", include_in_schema=False)
def serve_frontend(request: Request):
    conn = get_conn()
    blogs = []
    total_members = 380
    try:
        cursor = conn.cursor()
        
        # Calculate real total number of users and verified hosts
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM users) + 
                (SELECT COUNT(*) FROM hosts WHERE verification_status = 'VERIFIED')
        """)
        row = cursor.fetchone()
        if row and row[0]:
            total_members = row[0]
            
        # Fetch latest 6 published blogs
        cursor.execute("SELECT id, title, slug, content, keywords, seo_description, image_url, image_alt, badge_text, likes, shares, author, created_at, is_pivoted FROM blogs WHERE status = 'published' ORDER BY is_pivoted DESC, created_at DESC LIMIT 6")
        rows = cursor.fetchall()
        for r in rows:
            blogs.append({
                "id": r[0], "title": r[1], "slug": r[2], "content": r[3],
                "keywords": r[4], "description": r[5], "image": r[6],
                "image_alt": r[7], "badge": r[8], "likes": r[9], "shares": r[10],
                "author": r[11], "date": local_time_filter(r[12]), "is_pivoted": r[13]
            })
        # Fetch all published events for SSR and client JSON
        cursor.execute("""
            SELECT e.id, e.title, e.description, e.category, NULL as package_tier, e.price_per_person,
                   e.capacity, e.booked_count, e.location_name, e.location_area, e.event_date,
                   CASE WHEN e.image_url IS NOT NULL AND e.image_url != '' THEN 1 ELSE 0 END as has_image, 
                   e.included, e.status, h.id as host_id, u.full_name as host_name,
                   u.avatar_url as host_avatar, u.id as user_id, h.verification_status as host_verification_status,
                   h.profession as host_profession, h.experience_years as host_experience, h.is_founding as host_is_founding, e.booking_model
            FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            LEFT JOIN users u ON h.user_id = u.id
            WHERE e.status = 'published'
            ORDER BY e.event_date ASC
        """)
        evt_rows = cursor.fetchall()
        events = []
        for r in evt_rows:
            events.append({
                "id": r[0], "title": r[1], "description": r[2], "category": r[3],
                "package_tier": r[4], "price_per_person": float(r[5]), "capacity": r[6],
                "booked_count": r[7], "location_name": r[8], "location_area": r[9],
                "event_date": str(r[10]) if r[10] else None, "image_url": f"/api/events/{r[0]}/image" if r[11] else None, "included": r[12] or [],
                "status": r[13], "host_id": r[14], "host_name": r[15] or "DekhaHok Host",
                "host_avatar": f"/api/users/{r[17]}/avatar" if r[17] else f"https://api.dicebear.com/7.x/adventurer/svg?seed={r[15]}",
                "host_verification_status": r[18],
                "host_profession": r[19] or "",
                "host_experience": r[20] or 0,
                "host_is_founding": bool(r[21]),
                "booking_model": r[22] or "ticketed",
                "event_date_formatted": local_time_filter(r[10]) if r[10] else "TBA"
            })
            
        displayed_events = [e for e in events if e["category"].lower() not in ("travel", "professional", "sports")]
        travel_events = [e for e in events if e["category"].lower() == "travel"]
        sports_events = [e for e in events if e["category"].lower() == "sports"]
        professional_events = [e for e in events if e["category"].lower() == "professional"]
        
        import json
        events_json = json.dumps(events)
        
        cursor.close()
    finally:
        release_conn(conn)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "blogs": blogs,
        "total_members": total_members,
        "displayed_events": displayed_events,
        "travel_events": travel_events,
        "sports_events": sports_events,
        "professional_events": professional_events,
        "events_json": events_json
    })


@app.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse("admin/index.html")

@app.get("/admin/blogs/new", include_in_schema=False)
def serve_admin_blog_new():
    return FileResponse("admin/blog_edit.html")

@app.get("/admin/blogs/{blog_id}/edit", include_in_schema=False)
def serve_admin_blog_edit(blog_id: int):
    return FileResponse("admin/blog_edit.html")
@app.get("/privacy-policy", include_in_schema=False)
def serve_privacy(request: Request):
    return templates.TemplateResponse("privacy_policy.html", {"request": request})


@app.get("/terms-of-service", include_in_schema=False)
def serve_terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})


@app.get("/about", include_in_schema=False)
def serve_about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/contact", include_in_schema=False)
def serve_contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})


@app.get("/partnership", include_in_schema=False)
def serve_partnership(request: Request):
    return templates.TemplateResponse("partnership.html", {"request": request})


@app.get("/safety", include_in_schema=False)
def serve_safety(request: Request):
    return templates.TemplateResponse("safety.html", {"request": request})


@app.get("/host-guidelines", include_in_schema=False)
def serve_host_guidelines(request: Request):
    return templates.TemplateResponse("host_guidelines.html", {"request": request})



@app.get("/blog", include_in_schema=False)
def serve_blog_list(request: Request):
    conn = get_conn()
    blogs = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, slug, content, keywords, seo_description, image_url, image_alt, badge_text, likes, shares, author, created_at, is_pivoted FROM blogs WHERE status = 'published' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        for r in rows:
            blogs.append({
                "id": r[0], "title": r[1], "slug": r[2], "content": r[3],
                "keywords": r[4], "description": r[5], "image": r[6],
                "image_alt": r[7], "badge": r[8], "likes": r[9], "shares": r[10],
                "author": r[11], "date": local_time_filter(r[12]), "is_pivoted": r[13]
            })
        cursor.close()
    finally:
        release_conn(conn)
    return templates.TemplateResponse("blog_list.html", {"request": request, "blogs": blogs})


@app.get("/booking/{event_id}", include_in_schema=False)
def serve_booking_page(request: Request, event_id: int):
    import urllib.parse
    dh_session = request.cookies.get("dh_session")
    user = None
    if dh_session:
        user = get_current_user(dh_session)
        
    event = None
    existing_booking = None
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Increment views
        cursor.execute("UPDATE events SET views = COALESCE(views, 0) + 1 WHERE id = %s", (event_id,))
        conn.commit()

        # 1. Fetch Event details for SEO tags and fallback
        cursor.execute("SELECT id, title, description, image_url, price_per_person, slug, COALESCE(views, 0), booking_model FROM events WHERE id = %s", (event_id,))
        evt_row = cursor.fetchone()
        if evt_row:
            event = {
                "id": evt_row[0],
                "title": evt_row[1],
                "description": evt_row[2],
                "image_url": evt_row[3],
                "price": float(evt_row[4]),
                "slug": evt_row[5],
                "views": evt_row[6],
                "booking_model": evt_row[7] or "ticketed"
            }
            
        # 2. Check for existing booking if user is logged in
        if user:
            cursor.execute("SELECT tracking_id FROM bookings WHERE user_id = %s AND event_id = %s AND booking_status NOT IN ('cancelled', 'rejected')", (user["user_id"], event_id))
            row = cursor.fetchone()
            if row:
                existing_booking = {"tracking_id": row[0]}
                
        cursor.close()
    finally:
        release_conn(conn)
        
    template_name = "booking.html"
    if event and event["booking_model"] == "session":
        template_name = "booking_session.html"
    elif event and event["booking_model"] == "hire":
        template_name = "booking_hire.html"

    return templates.TemplateResponse(template_name, {
        "request": request, 
        "user": user, 
        "event_id": event_id, 
        "event": event,
        "existing_booking": existing_booking
    })


@app.get("/host", include_in_schema=False)
def serve_host_landing(request: Request):
    dh_session = request.cookies.get("dh_session")
    user = None
    if dh_session:
        user = get_current_user(dh_session)
        
    conn = get_conn()
    featured_hosts = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.id, u.full_name, u.avatar_url, h.profession, h.operating_area, h.bio, h.is_founding, u.id
            FROM hosts h
            JOIN users u ON h.user_id = u.id
            WHERE h.verification_status = 'VERIFIED' AND u.id != 1
            ORDER BY h.id DESC
            LIMIT 6
        """)
        rows = cursor.fetchall()
        for r in rows:
            featured_hosts.append({
                "id": r[0],
                "full_name": r[1],
                "avatar_url": r[2] or f"/api/users/{r[7]}/avatar",
                "profession": r[3],
                "operating_area": r[4],
                "bio": r[5],
                "is_founding": r[6]
            })
        cursor.close()
    except Exception as e:
        print(f"Error serving host landing: {e}")
    finally:
        release_conn(conn)
        
    return templates.TemplateResponse("host.html", {
        "request": request,
        "user": user,
        "featured_hosts": featured_hosts
    })


@app.get("/host/apply", include_in_schema=False)
def serve_host_apply(request: Request):
    dh_session = request.cookies.get("dh_session")
    user = None
    host = None
    if dh_session:
        user = get_current_user(dh_session)
        if user:
            conn = get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT id, verification_status FROM hosts WHERE user_id = %s", (user["user_id"],))
                row = cursor.fetchone()
                if row:
                    host = {
                        "id": row[0],
                        "verification_status": row[1]
                    }
                cursor.close()
            finally:
                release_conn(conn)
    return templates.TemplateResponse("host_apply.html", {"request": request, "user": user, "host": host})

@app.get("/host/events/new", include_in_schema=False)
def serve_host_event_create(request: Request):
    dh_session = request.cookies.get("dh_session")
    if not dh_session:
        return RedirectResponse("/login")
    user = get_current_user(dh_session)
    if not user:
        return RedirectResponse("/login")
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, verification_status, host_type FROM hosts WHERE user_id = %s", (user["user_id"],))
        host_row = cursor.fetchone()
        if not host_row:
            return RedirectResponse("/host/apply")
        
        host_id, verification_status, host_type = host_row
        if verification_status != "VERIFIED" and user["role"] != "admin":
            return RedirectResponse("/host/apply")
            
        host_info = {
            "id": host_id,
            "host_type": host_type or "community"
        }
    finally:
        release_conn(conn)
        
    return templates.TemplateResponse("host_event_create.html", {"request": request, "user": user, "host": host_info})

@app.get("/host/events/{event_id}/edit", include_in_schema=False)
def serve_host_event_edit(event_id: int, request: Request):
    dh_session = request.cookies.get("dh_session")
    if not dh_session:
        return RedirectResponse("/login")
    user = get_current_user(dh_session)
    if not user:
        return RedirectResponse("/login")
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        host_dict = {}
        if user["role"] != "admin":
            cursor.execute("SELECT id, host_type, verification_status FROM hosts WHERE user_id = %s", (user["user_id"],))
            host_row = cursor.fetchone()
            if not host_row:
                return RedirectResponse("/host/apply")
            host_id = host_row[0]
            host_dict = {
                "id": host_row[0],
                "host_type": host_row[1],
                "verification_status": host_row[2]
            }
        else:
            host_id = None
            cursor.execute("SELECT host_id FROM events WHERE id = %s", (event_id,))
            ev_host_row = cursor.fetchone()
            if ev_host_row:
                cursor.execute("SELECT id, host_type, verification_status FROM hosts WHERE id = %s", (ev_host_row[0],))
                h_row = cursor.fetchone()
                if h_row:
                    host_dict = {
                        "id": h_row[0],
                        "host_type": h_row[1],
                        "verification_status": h_row[2]
                    }
            
        # If admin, we don't strictly enforce host_id match
        if host_id:
            cursor.execute("""
                SELECT id, title, description, category, NULL as package_tier, price_per_person, capacity, 
                       location_name, location_area, event_date, included, image_url, is_recurring,
                       image_url_2, image_url_3, image_url_4
                FROM events WHERE id = %s AND host_id = %s
            """, (event_id, host_id))
        else:
            cursor.execute("""
                SELECT id, title, description, category, NULL as package_tier, price_per_person, capacity, 
                       location_name, location_area, event_date, included, image_url, is_recurring,
                       image_url_2, image_url_3, image_url_4
                FROM events WHERE id = %s
            """, (event_id,))
            
        event_row = cursor.fetchone()
        if not event_row:
            return RedirectResponse("/host/dashboard")
            
        import json
        included_list = []
        try:
            if isinstance(event_row[10], list):
                included_list = event_row[10]
            else:
                included_list = json.loads(event_row[10] or "[]")
        except:
            pass
            
        evt_dict = {
            "id": event_row[0],
            "title": event_row[1],
            "description": event_row[2],
            "category": event_row[3],
            "package_tier": event_row[4],
            "price_per_person": float(event_row[5]),
            "capacity": event_row[6],
            "location_name": event_row[7],
            "location_area": event_row[8],
            "event_date_iso": event_row[9].strftime('%Y-%m-%dT%H:%M') if event_row[9] else "",
            "included": included_list if isinstance(included_list, list) else [],
            "included_str": "\n".join(included_list) if isinstance(included_list, list) else "",
            "image_url": event_row[11] or "",
            "is_recurring": bool(event_row[12]),
            "image_url_2": event_row[13] or "",
            "image_url_3": event_row[14] or "",
            "image_url_4": event_row[15] or ""
        }
    finally:
        release_conn(conn)
        
    return templates.TemplateResponse("host_event_edit.html", {
        "request": request, 
        "user": user, 
        "event": evt_dict,
        "event_data_json": json.dumps(evt_dict),
        "host": host_dict
    })

@app.get("/host/dashboard", include_in_schema=False)
def serve_host_dashboard(request: Request):
    dh_session = request.cookies.get("dh_session")
    if not dh_session:
        return RedirectResponse("/login")
    user = get_current_user(dh_session)
    if not user:
        return RedirectResponse("/login")
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, verification_status, revenue_share_pct, profession, host_type FROM hosts WHERE user_id = %s", (user["user_id"],))
        host_row = cursor.fetchone()
        if not host_row:
            cursor.close()
            return RedirectResponse("/host/apply")
        
        host_id, verification_status, revenue_share, profession, host_type = host_row
        if verification_status != "VERIFIED":
            cursor.close()
            return RedirectResponse("/host/apply")
            
        # Retrieve all events for this host
        cursor.execute("""
            SELECT id, slug, title, description, category, NULL as package_tier, price_per_person, capacity, booked_count, location_name, location_area, event_date, status, included 
            FROM events 
            WHERE host_id = %s 
            ORDER BY event_date DESC
        """, (host_id,))
        event_rows = cursor.fetchall()
        
        events = []
        total_earnings = 0.0
        people_reached = 0
        
        for r in event_rows:
            ev_id = r[0]
            # Fetch bookings for this event
            cursor.execute("""
                SELECT id, tracking_id, name, email, phone, group_size, booking_status, payment_status, fee_amount, discount_amount, created_at 
                FROM bookings 
                WHERE event_id = %s 
                ORDER BY created_at DESC
            """, (ev_id,))
            booking_rows = cursor.fetchall()
            
            bookings_list = []
            event_revenue = 0.0
            for b in booking_rows:
                b_id, tracking_id, b_name, b_email, b_phone, g_size, b_status, p_status, fee, discount, created_at = b
                bookings_list.append({
                    "id": b_id,
                    "tracking_id": tracking_id,
                    "name": b_name,
                    "email": b_email,
                    "phone": b_phone,
                    "group_size": g_size,
                    "booking_status": b_status,
                    "payment_status": p_status,
                    "fee_amount": float(fee or 0),
                    "discount_amount": float(discount or 0),
                    "created_at": str(created_at)
                })
                if p_status == 'paid' or b_status == 'confirmed':
                    event_revenue += float(fee or 0) - float(discount or 0)
                    people_reached += g_size
            
            host_event_earnings = event_revenue * float(revenue_share or 0.5)
            total_earnings += host_event_earnings
            
            # Format clean strings for the dashboard UI
            raw_dt = r[11]
            if isinstance(raw_dt, datetime):
                formatted_date = raw_dt.strftime("%b %d, %Y at %I:%M %p")
            else:
                try:
                    dt = datetime.fromisoformat(str(raw_dt).replace('Z', '+00:00'))
                    formatted_date = dt.strftime("%b %d, %Y at %I:%M %p")
                except Exception:
                    formatted_date = str(raw_dt) if raw_dt else ""
                
            loc_name = r[9] or ""
            loc_area = r[10] or ""
            if loc_area and loc_area.lower() not in loc_name.lower():
                formatted_location = f"{loc_name} ({loc_area})"
            else:
                formatted_location = loc_name
            
            events.append({
                "id": ev_id,
                "slug": r[1],
                "title": r[2],
                "description": r[3],
                "category": r[4],
                "package_tier": r[5],
                "price_per_person": float(r[6]),
                "capacity": r[7],
                "booked_count": r[8],
                "location_name": r[9],
                "location_area": r[10],
                "event_date": formatted_date,
                "formatted_location": formatted_location,
                "status": r[12],
                "included": r[13] or [],
                "attendees": bookings_list,
                "revenue": host_event_earnings
            })
            
        # Retrieve actual user reviews for this host's events
        cursor.execute("""
            SELECT r.comment, r.score, r.created_at, b_rater.name, e.title
            FROM user_ratings r
            JOIN bookings b_rater ON b_rater.id = r.rater_id
            JOIN events e ON e.id = b_rater.event_id
            WHERE e.host_id = %s AND r.comment IS NOT NULL AND r.comment != ''
            ORDER BY r.created_at DESC
        """, (host_id,))
        review_rows = cursor.fetchall()
        
        reviews = []
        for r_row in review_rows:
            reviews.append({
                "comment": r_row[0],
                "score": r_row[1],
                "stars": "⭐" * int(r_row[1]),
                "created_at": str(r_row[2]),
                "attendee_name": r_row[3],
                "event_title": r_row[4]
            })
            
        cursor.close()
    finally:
        release_conn(conn)
        
    # Fetch hire requests for artists
    hire_requests = []
    if host_type == 'artist':
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.id, h.tracking_id, h.client_name, h.occasion_type, h.event_date, h.event_location, h.guest_count, h.budget_range, h.status, h.message, h.created_at, e.title, h.client_phone, b.payment_status
                FROM hire_requests h
                JOIN events e ON h.event_id = e.id
                LEFT JOIN bookings b ON b.hire_request_id = h.id
                WHERE h.host_id = %s
                ORDER BY h.created_at DESC
            """, (host_id,))
            rows = cursor.fetchall()
            for r in rows:
                hire_requests.append({
                    "id": r[0], "tracking_id": r[1], "client_name": r[2], "occasion": r[3], 
                    "event_date": r[4], "location": r[5], "guests": r[6], "budget": r[7], 
                    "status": r[8], "message": r[9], "created_at": r[10], "event_title": r[11],
                    "client_phone": r[12], "payment_status": r[13]
                })
        finally:
            release_conn(conn)
            
    # Fetch session slots for session hosts
    sessions = []
    if host_type == 'session':
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.slot_date, s.slot_time, s.duration_mins, s.is_booked, s.created_at, e.title,
                       b.name, b.email, b.phone, b.booking_status
                FROM host_slots s
                JOIN events e ON s.event_id = e.id
                LEFT JOIN bookings b ON b.slot_id = s.id
                WHERE e.host_id = %s
                ORDER BY s.slot_date DESC, s.slot_time DESC
            """, (host_id,))
            rows = cursor.fetchall()
            for r in rows:
                dt = datetime.combine(r[1], r[2]) if r[1] and r[2] else None
                sessions.append({
                    "id": r[0], "slot_time": dt, "duration_mins": r[3], "is_booked": r[4], "created_at": r[5], "event_title": r[6],
                    "client_name": r[7], "client_email": r[8], "client_phone": r[9], "booking_status": r[10]
                })
        finally:
            release_conn(conn)
        
    host_info = {
        "id": host_id,
        "verification_status": verification_status,
        "revenue_share_pct": float(revenue_share or 0.5),
        "profession": profession or "Community Host",
        "host_type": host_type or "community"
    }
    
    return templates.TemplateResponse("host_dashboard.html", {
        "request": request, 
        "user": user, 
        "host": host_info, 
        "events": events, 
        "total_earnings": total_earnings, 
        "people_reached": people_reached,
        "events_count": len(events),
        "reviews": reviews,
        "hire_requests": hire_requests,
        "sessions": sessions
    })


@app.get("/robots.txt", include_in_schema=False)
def robots():
    content = "User-agent: *\nDisallow: /admin/\nDisallow: /api/\nSitemap: https://dekhahok.com/sitemap.xml"
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap():
    """
    Dynamically generates sitemap.xml including the homepage and all published blogs.
    """
    base_url = "https://dekhahok.com"
    
    # Static pages
    current_date = datetime.now().date().isoformat()
    pages = [
        {"loc": f"{base_url}/", "lastmod": current_date, "changefreq": "daily", "priority": "1.0"},
        {"loc": f"{base_url}/about", "lastmod": current_date, "changefreq": "monthly", "priority": "0.8"},
        {"loc": f"{base_url}/contact", "lastmod": current_date, "changefreq": "monthly", "priority": "0.8"},
        {"loc": f"{base_url}/partnership", "lastmod": current_date, "changefreq": "monthly", "priority": "0.7"},
        {"loc": f"{base_url}/blog", "lastmod": current_date, "changefreq": "daily", "priority": "0.9"},
        {"loc": f"{base_url}/privacy-policy", "lastmod": current_date, "changefreq": "monthly", "priority": "0.3"},
        {"loc": f"{base_url}/terms-of-service", "lastmod": current_date, "changefreq": "monthly", "priority": "0.3"},
        {"loc": f"{base_url}/safety", "lastmod": current_date, "changefreq": "monthly", "priority": "0.4"},
        {"loc": f"{base_url}/host-guidelines", "lastmod": current_date, "changefreq": "monthly", "priority": "0.4"},
    ]
    
    # Dynamic blogs
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT slug, created_at FROM blogs WHERE status = 'published' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        for r in rows:
            # SEO-Friendly Blog URL
            pages.append({
                "loc": f"{base_url}/blog/{r[0]}",
                "lastmod": r[1].date().isoformat() if isinstance(r[1], datetime) else str(r[1]),
                "changefreq": "weekly",
                "priority": "0.8"
            })
        # Dynamic events
        cursor.execute("SELECT id, created_at FROM events WHERE status = 'published' ORDER BY created_at DESC")
        event_rows = cursor.fetchall()
        for er in event_rows:
            pages.append({
                "loc": f"{base_url}/booking/{er[0]}",
                "lastmod": er[1].date().isoformat() if isinstance(er[1], datetime) else str(er[1]),
                "changefreq": "daily",
                "priority": "0.9"
            })
            
        cursor.close()
    finally:
        release_conn(conn)

    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for p in pages:
        xml_content += f'  <url>\n'
        xml_content += f'    <loc>{p["loc"]}</loc>\n'
        xml_content += f'    <lastmod>{p["lastmod"]}</lastmod>\n'
        xml_content += f'    <changefreq>{p["changefreq"]}</changefreq>\n'
        xml_content += f'    <priority>{p["priority"]}</priority>\n'
        xml_content += f'  </url>\n'
    xml_content += '</urlset>'
    
    return Response(content=xml_content, media_type="application/xml")


async def run_daily_rollover():
    while True:
        utc_now = datetime.utcnow()
        dhaka_time = utc_now + timedelta(hours=6)
        target_time = dhaka_time.replace(hour=23, minute=0, second=0, microsecond=0)
        
        if dhaka_time >= target_time:
            target_time += timedelta(days=1)
            
        wait_seconds = (target_time - dhaka_time).total_seconds()
        print(f"Next rollover scheduled in {wait_seconds} seconds (at 11 PM Dhaka time)")
        await asyncio.sleep(wait_seconds)
        
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.title, e.event_date, h.user_id 
                FROM events e
                JOIN hosts h ON e.host_id = h.id
                WHERE e.status = 'published' 
                  AND e.is_recurring = TRUE 
                  AND e.event_date < NOW()
            """)
            expired_events = cursor.fetchall()
            
            for event_id, title, old_date, host_user_id in expired_events:
                new_date = old_date + timedelta(days=7)
                cursor.execute("UPDATE events SET event_date = %s WHERE id = %s", (new_date, event_id))
                
                # Notify Host
                msg = f"Your weekly recurring event '{title}' has been auto-renewed for {new_date.strftime('%B %d, %I:%M %p')}. If you cannot host, please edit the event."
                cursor.execute("""
                    INSERT INTO notifications (user_id, type, title, message, action_url) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (host_user_id, "SYSTEM", "Event Auto-Renewed", msg, f"/host/events/{event_id}/edit"))
                
                # Optional: Find admin user and notify them too (assuming user 1 is admin, or we can skip admin notification for now since they can just check the feeds). Let's skip admin spam for now.
                print(f"[Rollover] Event {event_id} ({title}) rolled over to {new_date}")
                
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"[Rollover Error] {e}")
        finally:
            release_conn(conn)


@app.on_event("startup")
def on_startup():
    init_db()
    asyncio.create_task(run_daily_rollover())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ADMIN_KEY = os.getenv("ADMIN_SECRET_KEY", "dekhahok-admin-pw-2024")
FEE_MAP   = {2: 499.00, 5: 249.00}

# ---------------------------------------------------------------------------
# Admin security check: Simple secret key based authentication
# for all internal admin endpoints.
# ---------------------------------------------------------------------------
def require_admin(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")


def generate_tracking_id() -> str:
    charset = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(charset) for _ in range(8))
    return f"DH-{suffix}"


# ===========================================================================
# PUBLIC
# ===========================================================================


def format_time_12h(t) -> Optional[str]:
    if not t:
        return None
    if isinstance(t, str):
        try:
            # Handle "17:00" or "17:00:00"
            parts = t.split(":")
            t = time(int(parts[0]), int(parts[1]))
        except:
            return t
    return t.strftime("%I:%M %p")

@app.get("/login", include_in_schema=False)
def get_login_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/auth/google")
def google_login(request: Request, next: Optional[str] = None):
    import urllib.parse
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id or "apps.googleusercontent.com" not in client_id:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth configuration error: GOOGLE_CLIENT_ID is missing or invalid in the server environment variables. Please check your deployment settings."
        )
    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if "dekhahok.com" in host else "http"
    redirect_uri = f"{scheme}://{host}/auth/callback"
    
    state_str = f"next={next}" if next and next.startswith("/") else "dekhahok_auth_state"
    
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=openid%20email%20profile"
        f"&state={urllib.parse.quote(state_str)}"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def google_callback(request: Request, code: str, state: str, response: Response):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth configuration error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is missing from the environment."
        )
    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if "dekhahok.com" in host else "http"
    redirect_uri = f"{scheme}://{host}/auth/callback"
    
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }
        )
        if token_resp.status_code != 200:
            raise HTTPException(400, f"Token exchange failed: {token_resp.text}")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        
        profile_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if profile_resp.status_code != 200:
            raise HTTPException(400, "Failed to get user info from Google")
        profile = profile_resp.json()
        
    email = profile.get("email")
    full_name = profile.get("name", "Google User")
    avatar_url = profile.get("picture", "")
    sub = profile.get("sub")
    
    if not email:
        raise HTTPException(400, "Google OAuth did not return an email address")
        
    avatar_url = avatar_url or get_avatar_for_user(full_name, email)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, role, google_id FROM users WHERE email = %s", (email,))
        user_row = cursor.fetchone()
        
        if user_row:
            user_id, role, existing_google_id = user_row
            if not existing_google_id:
                cursor.execute("UPDATE users SET google_id = %s, avatar_url = %s WHERE id = %s", (sub, avatar_url, user_id))
            else:
                cursor.execute("UPDATE users SET avatar_url = %s WHERE id = %s", (avatar_url, user_id))
            conn.commit()
        else:
            role = 'admin' if email == 'team@dekhahok.com' else 'user'
            cursor.execute("""
                INSERT INTO users (email, google_id, full_name, avatar_url, role)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (email, sub, full_name, avatar_url, role))
            user_id = cursor.fetchone()[0]
            conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
        
    session_val = create_session_cookie(user_id, email, role)
    
    next_url = "/"
    if state and state.startswith("next="):
        next_val = state.split("=", 1)[1]
        import urllib.parse
        next_val = urllib.parse.unquote(next_val)
        if next_val.startswith("/"):
            next_url = next_val
            
    response = RedirectResponse(url=next_url)
    response.set_cookie(
        key="dh_session",
        value=session_val,
        httponly=True,
        max_age=30*24*60*60,
        samesite="lax",
        secure=True if "dekhahok.com" in host else False
    )
    return response

@app.post("/auth/signup")
def manual_signup(payload: UserCreate, response: Response):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (payload.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        pwd_hash = hash_password(payload.password)
        role = 'admin' if payload.email == 'team@dekhahok.com' else 'user'
        avatar_url = get_avatar_for_user(payload.full_name, payload.email)
        
        cursor.execute("""
            INSERT INTO users (email, password_hash, full_name, phone, role, avatar_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (payload.email, pwd_hash, payload.full_name, payload.phone, role, avatar_url))
        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
        
    session_val = create_session_cookie(user_id, payload.email, role)
    response.set_cookie(key="dh_session", value=session_val, httponly=True, max_age=30*24*60*60, samesite="lax")
    return {"message": "Sign-up successful", "user_id": user_id, "role": role}

@app.post("/auth/login")
def manual_login(payload: UserLogin, response: Response):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password_hash, role, full_name FROM users WHERE email = %s", (payload.email,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Invalid email or password")
        
        user_id, pwd_hash, role, full_name = row
        if not pwd_hash or not verify_password(payload.password, pwd_hash):
            raise HTTPException(status_code=400, detail="Invalid email or password")
        cursor.close()
    finally:
        release_conn(conn)
        
    session_val = create_session_cookie(user_id, payload.email, role)
    response.set_cookie(key="dh_session", value=session_val, httponly=True, max_age=30*24*60*60, samesite="lax")
    return {"message": "Login successful", "user_id": user_id, "role": role, "name": full_name}

@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(key="dh_session")
    return {"message": "Logged out successfully"}

@app.get("/auth/me")
def check_me(user = Depends(get_current_user)):
    if not user:
        return {"logged_in": False}
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, avatar_url, role FROM users WHERE id = %s", (user["user_id"],))
        row = cursor.fetchone()
        if row:
            return {
                "logged_in": True,
                "user_id": user["user_id"],
                "email": user["email"],
                "role": row[2],
                "name": row[0],
                "avatar": f"/api/users/{user['user_id']}/avatar"
            }
        return {"logged_in": False}
    finally:
        release_conn(conn)


@app.post("/api/users/profile")
def update_user_profile(payload: dict = Body(...), current_user = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Please log in to update your profile.")
        
    avatar_base64 = payload.get("avatar_base64")
    full_name = payload.get("full_name")
    experience_years = payload.get("experience_years")
    
    if not avatar_base64 and not full_name and experience_years is None:
        raise HTTPException(status_code=400, detail="No updates provided.")
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        if avatar_base64 and full_name:
            cursor.execute(
                "UPDATE users SET avatar_url = %s, full_name = %s WHERE id = %s",
                (avatar_base64, full_name, current_user["user_id"])
            )
        elif avatar_base64:
            cursor.execute(
                "UPDATE users SET avatar_url = %s WHERE id = %s",
                (avatar_base64, current_user["user_id"])
            )
        elif full_name:
            cursor.execute(
                "UPDATE users SET full_name = %s WHERE id = %s",
                (full_name, current_user["user_id"])
            )
            
        if experience_years is not None and current_user["role"] in ["host", "admin"]:
            cursor.execute(
                "UPDATE hosts SET experience_years = %s WHERE user_id = %s",
                (experience_years, current_user["user_id"])
            )
            
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    
    return {"message": "Profile updated successfully"}

@app.get("/api/users/{user_id}/avatar")
def get_user_avatar(user_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_url, full_name FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return RedirectResponse(url="https://api.dicebear.com/7.x/adventurer/svg?seed=Unknown")
        
        avatar_url, full_name = row
        if not avatar_url:
            return RedirectResponse(url=f"https://api.dicebear.com/7.x/adventurer/svg?seed={full_name}")
            
        if avatar_url.startswith("data:image"):
            try:
                header, encoded = avatar_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]
                decoded = base64.b64decode(encoded)
                return Response(content=decoded, media_type=media_type)
            except Exception:
                return RedirectResponse(url=f"https://api.dicebear.com/7.x/adventurer/svg?seed={full_name}")
        else:
            return RedirectResponse(url=avatar_url)
    finally:
        release_conn(conn)

@app.get("/api/events/{event_id}/image")
def get_event_image(event_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT image_url FROM events WHERE id = %s", (event_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return RedirectResponse(url="/static/assets/dekhahok_adda.jpg")
            
        image_url = row[0]
        if image_url.startswith("data:image"):
            try:
                header, encoded = image_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]
                decoded = base64.b64decode(encoded)
                return Response(content=decoded, media_type=media_type)
            except Exception:
                return RedirectResponse(url="/static/assets/dekhahok_adda.jpg")
        else:
            return RedirectResponse(url=image_url)
    finally:
        release_conn(conn)

@app.get("/api/events/{event_id}/image/{index}")
def get_event_extra_image(event_id: int, index: int):
    if index not in [2, 3, 4]:
        raise HTTPException(status_code=400, detail="Invalid image index")
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        col = f"image_url_{index}"
        cursor.execute(f"SELECT {col} FROM events WHERE id = %s", (event_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="Image not found")
            
        image_url = row[0]
        if image_url.startswith("data:image"):
            try:
                header, encoded = image_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]
                decoded = base64.b64decode(encoded)
                return Response(content=decoded, media_type=media_type)
            except:
                raise HTTPException(status_code=404, detail="Image error")
        return RedirectResponse(url=image_url)
    finally:
        release_conn(conn)

@app.post("/api/bookings", response_model=BookingResponse, status_code=201)
def create_booking(payload: BookingCreate, current_user = Depends(get_current_user)):
    """
    Creates a new meetup interested entry. 
    Assigns a unique Tracking ID and calculates the required reservation fee.
    Supports global site-wide discounts and individual coupons.
    """
    discount = 0.0
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Determine event_id and basic fee before adjustments
        event_id = payload.event_id
        host_id = None
        
        if not event_id:
            # Legacy booking, fall back to circle event
            cursor.execute("SELECT id, price_per_person, host_id FROM events WHERE slug = 'dekhahok-circle-adda'")
            circle_row = cursor.fetchone()
            if circle_row:
                event_id = circle_row[0]
                host_id = circle_row[2]
                fee = FEE_MAP.get(payload.group_size, float(circle_row[1]) * payload.group_size)
            else:
                fee = FEE_MAP.get(payload.group_size, 299.00 * payload.group_size)
            
            # Map legacy inputs
            preferred_date = payload.preferred_date or datetime.now().date()
            preferred_time = payload.preferred_time or "17:00"
            venue_type = payload.venue_type or "public_place"
            booking_status = "processing"
        else:
            # Event-based booking
            cursor.execute("SELECT host_id, price_per_person, capacity, booked_count, event_date, location_name, status FROM events WHERE id = %s", (event_id,))
            ev_row = cursor.fetchone()
            if not ev_row:
                raise HTTPException(400, "Event not found")
            host_id, ppp, capacity, booked, ev_date, loc_name, ev_status = ev_row
            if ev_status != 'published':
                raise HTTPException(400, "Event is not published")
                
            fee = float(ppp) * payload.group_size
            preferred_date = ev_date.date() if ev_date else datetime.now().date()
            preferred_time = ev_date.strftime("%H:%M") if ev_date else "17:00"
            venue_type = "public_place"
            
            if booked + payload.group_size > capacity:
                booking_status = "waitlist"
            else:
                booking_status = "processing"
        
        # 1. Apply Global Site-wide Discount
        cursor.execute("SELECT value FROM site_settings WHERE key = 'global_discount_percent'")
        row = cursor.fetchone()
        global_discount_pct = float(row[0]) if row else 0.0
        if global_discount_pct > 0:
            fee = round(fee * (1 - global_discount_pct / 100))

        # 1.5 Apply Female Discount
        if payload.gender and payload.gender.lower() == 'female':
            female_discount = fee * 0.20
            discount += female_discount
 
        # 2. Apply Coupon Code if provided
        coupon_cleaned = payload.coupon_code.strip().upper() if payload.coupon_code else ""
        if coupon_cleaned:
            cursor.execute(
                "SELECT discount_type, value, usage_limit, expires_at FROM coupons WHERE code = %s",
                (coupon_cleaned,)
            )
            coupon = cursor.fetchone()
            if coupon:
                d_type, d_val, d_limit, d_expiry = coupon
                if d_expiry:
                    now = datetime.now(d_expiry.tzinfo) if d_expiry.tzinfo else datetime.now()
                    if now > d_expiry:
                        raise HTTPException(status_code=400, detail="Coupon expired")
                
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE coupon_code = %s", (coupon_cleaned,))
                usage_count = cursor.fetchone()[0]
                if d_limit and usage_count >= d_limit:
                    raise HTTPException(status_code=400, detail="Coupon limit reached")
                
                if d_type == 'percent':
                    discount = fee * (float(d_val) / 100.0)
                else:
                    discount = float(d_val)
            else:
                raise HTTPException(status_code=400, detail="Invalid coupon code")

        fee = max(0.0, fee - discount)
        payment_status = "unpaid"
        
        # Auto-verify free bookings
        if fee == 0.0 or booking_status == "waitlist":
            payment_status = "unpaid" if booking_status == "waitlist" else "paid"
            if not payload.payment_method:
                payload.payment_method = "beta_promo" if booking_status != "waitlist" else "bkash"
            if not payload.payment_sender_digits:
                payload.payment_sender_digits = "00"

        if not payload.email:
            raise HTTPException(status_code=400, detail="Email address is required to place a booking.")

        user_id = current_user["user_id"] if current_user else None
        auto_created_user = False
        temp_password = None
        
        if not user_id:
            email_cleaned = payload.email.strip().lower()
            cursor.execute("SELECT id FROM users WHERE email = %s", (email_cleaned,))
            user_row = cursor.fetchone()
            if user_row:
                user_id = user_row[0]
            else:
                # Create a new user account
                temp_pwd = payload.phone.strip() if payload.phone else "".join(secrets.choice(string.digits) for _ in range(8))
                pwd_hash = hash_password(temp_pwd)
                avatar_url = get_avatar_for_user(payload.name, email_cleaned, payload.gender)
                phone_cleaned = payload.phone.strip() if payload.phone else None
                
                cursor.execute("""
                    INSERT INTO users (email, password_hash, full_name, phone, role, avatar_url)
                    VALUES (%s, %s, %s, %s, 'user', %s)
                    RETURNING id
                """, (email_cleaned, pwd_hash, payload.name.strip(), phone_cleaned, avatar_url))
                user_id = cursor.fetchone()[0]
                auto_created_user = True
                temp_password = temp_pwd

        for _ in range(5):
            tracking_id = generate_tracking_id()
            try:
                cursor.execute(
                    """
                    INSERT INTO bookings
                        (tracking_id, name, phone, email, age, group_size,
                         preferred_date, preferred_time, venue_type,
                         conversation_style, preferred_people, current_location, preferred_location, 
                         preferred_meeting_point, payment_method, payment_sender_digits, fee_amount,
                         interests, expectations, wants_pickup, wants_dropoff, vibe, discount_amount, 
                         coupon_code, payment_status, booking_status, gender, event_id, host_id, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        tracking_id,
                        payload.name,
                        payload.phone,
                        payload.email,
                        payload.age,
                        payload.group_size,
                        preferred_date,
                        preferred_time,
                        venue_type,
                        payload.conversation_style,
                        payload.preferred_people,
                        payload.current_location,
                        payload.preferred_location,
                        payload.preferred_meeting_point,
                        payload.payment_method,
                        payload.payment_sender_digits,
                        fee,
                        payload.interests,
                        payload.expectations,
                        payload.wants_pickup,
                        payload.wants_dropoff,
                        payload.vibe,
                        discount,
                        coupon_cleaned or None,
                        payment_status,
                        booking_status,
                        payload.gender,
                        event_id,
                        host_id,
                        user_id
                    ),
                )
                booking_id = cursor.fetchone()[0]
                
                # If booking is active (not waitlisted), increment booked_count of event
                if booking_status != "waitlist":
                    cursor.execute("UPDATE events SET booked_count = booked_count + %s WHERE id = %s", (payload.group_size, event_id))
                
                # Send Host Notification
                if host_id:
                    cursor.execute("SELECT user_id FROM hosts WHERE id = %s", (host_id,))
                    h_row = cursor.fetchone()
                    if h_row:
                        h_user_id = h_row[0]
                        cursor.execute("SELECT title FROM events WHERE id = %s", (event_id,))
                        ev_row = cursor.fetchone()
                        if ev_row:
                            ev_title = ev_row[0]
                            cursor.execute("""
                                INSERT INTO notifications (user_id, type, title, message, action_url)
                                VALUES (%s, 'booking', 'New Booking Received!', %s, %s)
                            """, (h_user_id, f"{payload.name} just booked {payload.group_size} seat(s) for '{ev_title}'.", "/host/dashboard"))

                conn.commit()
                
                # Generate referral code for this booking
                ref_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
                cursor.execute(
                    "UPDATE bookings SET referral_code = %s, referred_by = %s WHERE id = %s",
                    (ref_code, payload.referred_by, booking_id)
                )
                conn.commit()
                
                return BookingResponse(
                    tracking_id=tracking_id,
                    message="Booking received! Save your tracking ID to check status.",
                    auto_created_user=auto_created_user,
                    temp_password=temp_password
                )
            except Exception as e:
                conn.rollback()
                if "Duplicate entry" in str(e) and "tracking_id" in str(e):
                    continue
                raise HTTPException(status_code=500, detail=f"Could not save booking. {e}")
                
        raise HTTPException(status_code=500, detail="Could not generate unique tracking ID.")
    finally:
        release_conn(conn)

@app.get("/api/events")
def api_list_events(category: Optional[str] = None):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        query = """
            SELECT e.id, e.title, e.description, e.category, NULL as package_tier, e.price_per_person,
                   e.capacity, e.booked_count, e.location_name, e.location_area, e.event_date,
                   CASE WHEN e.image_url IS NOT NULL AND e.image_url != '' THEN 1 ELSE 0 END as has_image, 
                   e.included, e.status, h.id as host_id, u.full_name as host_name,
                   u.avatar_url as host_avatar, u.id as user_id, h.verification_status as host_verification_status,
                   h.profession as host_profession, h.is_founding as host_is_founding, e.booking_model
            FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            LEFT JOIN users u ON h.user_id = u.id
            WHERE e.status = 'published'
        """
        params = []
        if category and category != 'all':
            query += " AND e.category = %s"
            params.append(category.capitalize())
        query += " ORDER BY e.event_date ASC"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r[0], "title": r[1], "description": r[2], "category": r[3],
                "package_tier": r[4], "price_per_person": float(r[5]), "capacity": r[6],
                "booked_count": r[7], "location_name": r[8], "location_area": r[9],
                "event_date": str(r[10]) if r[10] else None, "image_url": f"/api/events/{r[0]}/image" if r[11] else None, "included": r[12] or [],
                "status": r[13], "host_id": r[14], "host_name": r[15] or "DekhaHok Host",
                "host_avatar": f"/api/users/{r[17]}/avatar" if r[17] else f"https://api.dicebear.com/7.x/adventurer/svg?seed={r[15]}",
                "host_verification_status": r[18],
                "host_profession": r[19] or "",
                "host_experience": r[20] or 0,
                "host_is_founding": bool(r[21]),
                "booking_model": r[22] or "ticketed"
            })
        cursor.close()
    finally:
        release_conn(conn)
    return results

@app.get("/api/events/{event_id}")
def api_event_detail(event_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.id, e.title, e.description, e.category, NULL as package_tier, e.price_per_person,
                   e.capacity, e.booked_count, e.location_name, e.location_area, e.event_date,
                   CASE WHEN e.image_url IS NOT NULL AND e.image_url != '' THEN 1 ELSE 0 END as has_image, 
                   e.included, e.status, h.id as host_id, u.full_name as host_name,
                   u.avatar_url as host_avatar, h.bio as host_bio, u.id as user_id, h.verification_status as host_verification_status,
                   h.profession as host_profession, h.experience_years as host_experience, e.is_recurring,
                   CASE WHEN e.image_url_2 IS NOT NULL AND e.image_url_2 != '' THEN 1 ELSE 0 END as has_image_2,
                   CASE WHEN e.image_url_3 IS NOT NULL AND e.image_url_3 != '' THEN 1 ELSE 0 END as has_image_3,
                   CASE WHEN e.image_url_4 IS NOT NULL AND e.image_url_4 != '' THEN 1 ELSE 0 END as has_image_4,
                   e.youtube_link, h.is_founding as host_is_founding, COALESCE(e.views, 0) as views
            FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            LEFT JOIN users u ON h.user_id = u.id
            WHERE e.id = %s
        """, (event_id,))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(404, "Event not found")
        
        result = {
            "id": r[0], "title": r[1], "description": r[2], "category": r[3],
            "package_tier": r[4], "price_per_person": float(r[5]), "capacity": r[6],
            "booked_count": r[7], "location_name": r[8], "location_area": r[9],
            "event_date": str(r[10]) if r[10] else None, 
            "image_url": f"/api/events/{r[0]}/image" if r[11] else None, 
            "included": r[12] or [],
            "status": r[13], 
            "host_id": r[14], 
            "host_name": r[15] or "DekhaHok Host",
            "host_avatar": f"/api/users/{r[18]}/avatar" if r[18] else f"https://api.dicebear.com/7.x/adventurer/svg?seed={r[15]}",
            "host_bio": r[17] or "",
            "host_verification_status": r[19],
            "host_profession": r[20] or "",
            "host_experience": r[21] or 0,
            "is_recurring": r[22] if len(r) > 22 else False,
            "image_url_2": f"/api/events/{r[0]}/image/2" if len(r) > 23 and r[23] else None,
            "image_url_3": f"/api/events/{r[0]}/image/3" if len(r) > 24 and r[24] else None,
            "image_url_4": f"/api/events/{r[0]}/image/4" if len(r) > 24 and r[24] else None,
            "youtube_link": r[25] if len(r) > 25 else None,
            "host_is_founding": bool(r[26]) if len(r) > 26 else False,
            "views": r[27] if len(r) > 27 else 0
        }
        cursor.close()
    finally:
        release_conn(conn)
    return result

@app.get("/api/host/{host_id}/profile")
def get_host_profile(host_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, category, host_type, verification_status, bio, operating_area
            FROM hosts
            WHERE id = %s
        """, (host_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Host not found")
        
        return {
            "id": row[0],
            "user_id": row[1],
            "category": row[2],
            "host_type": row[3],
            "verification_status": row[4],
            "bio": row[5],
            "operating_area": row[6]
        }
    finally:
        release_conn(conn)

@app.post("/api/host/apply")
def host_apply(payload: HostApply, user = Depends(require_role(["user", "host", "admin"]))):
    if not payload.avatar_url:
        raise HTTPException(status_code=400, detail="Profile picture is required for hosts.")
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM hosts WHERE user_id = %s", (user["user_id"],))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="You have already applied to host.")
        
        cursor.execute("""
            INSERT INTO hosts (user_id, nid_number, profession, category, host_type, operating_area, bio, social_links, verification_status, experience_years)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s)
            RETURNING id
        """, (user["user_id"], payload.nid_number, payload.profession, payload.category, payload.host_type, payload.operating_area, payload.bio, payload.social_links or '{}', payload.experience_years))
        host_id = cursor.fetchone()[0]
        
        cursor.execute("UPDATE users SET avatar_url = %s WHERE id = %s", (payload.avatar_url, user["user_id"]))
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Application submitted successfully! It is pending admin approval.", "host_id": host_id}

def generate_session_slots_for_event(cursor, host_id, event_id, available_days_str, available_times_str, session_duration_mins):
    if not available_days_str or not available_times_str:
        return
    
    days_map = {
        'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3,
        'Friday': 4, 'Saturday': 5, 'Sunday': 6
    }
    allowed_days = [days_map[d.strip()] for d in available_days_str.split(',') if d.strip() in days_map]
    if not allowed_days:
        return
        
    start_times = [t.strip() for t in available_times_str.split(',') if t.strip()]
    if not start_times:
        return
        
    today = datetime.now().date()
    duration = session_duration_mins or 60
    
    for i in range(28): # 4 weeks
        current_date = today + timedelta(days=i)
        if current_date.weekday() in allowed_days:
            for st_str in start_times:
                try:
                    # Parse start time
                    st_time = datetime.strptime(st_str, "%H:%M").time()
                    st_dt = datetime.combine(current_date, st_time)
                    
                    # Calculate end time
                    et_dt = st_dt + timedelta(minutes=duration)
                    et_time = et_dt.time()
                    
                    # Check if slot already exists
                    cursor.execute("""
                        SELECT id FROM host_slots
                        WHERE event_id = %s AND slot_date = %s AND start_time = %s
                    """, (event_id, current_date, st_time))
                    
                    if not cursor.fetchone():
                        # Insert slot
                        cursor.execute("""
                            INSERT INTO host_slots (host_id, event_id, slot_date, start_time, end_time, is_booked, is_blocked)
                            VALUES (%s, %s, %s, %s, %s, false, false)
                        """, (host_id, event_id, current_date, st_time, et_time))
                except Exception as e:
                    print(f"Error generating slot: {e}")
@app.post("/api/host/events/create")
@app.post("/api/host/listings/create")
def host_create_event(payload: EventCreate, user = Depends(require_role(["host", "admin"]))):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, verification_status FROM hosts WHERE user_id = %s", (user["user_id"],))
        host_row = cursor.fetchone()
        if not host_row:
            raise HTTPException(status_code=400, detail="You do not have a registered host profile.")
        host_id, status = host_row
        if status != 'VERIFIED' and user["role"] != 'admin':
            raise HTTPException(status_code=403, detail="Host verification pending. You cannot publish events yet.")
        
        slug = re.sub(r'[^a-z0-9]+', '-', payload.title.lower()).strip('-')
        slug += f"-{int(datetime.now().timestamp())}"
        
        event_dt = None
        if payload.event_date:
            try:
                event_dt = datetime.fromisoformat(payload.event_date.replace("Z", "+00:00"))
            except Exception:
                pass
            
        status = 'published' if user["role"] == 'admin' else 'draft'
        
        cursor.execute("""
            INSERT INTO events (
                host_id, slug, title, description, category, listing_type, booking_model,
                starting_rate, service_area, occasion_types, portfolio_url, availability_note,
                session_duration_mins, max_per_session, advance_notice_hours,
                price_per_person, capacity, location_name, location_area, event_date, included, status,
                image_url, image_url_2, image_url_3, image_url_4, youtube_link, is_recurring,
                start_time, end_time, available_days, available_times
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            host_id, slug, payload.title, payload.description, payload.category, payload.listing_type, payload.booking_model,
            payload.starting_rate, payload.service_area, payload.occasion_types, payload.portfolio_url, payload.availability_note,
            payload.session_duration_mins, payload.max_per_session, payload.advance_notice_hours,
            payload.price_per_person, payload.capacity, payload.location_name, payload.location_area, event_dt, payload.included or '[]', status,
            payload.image_base64, payload.image_base64_2, payload.image_base64_3, payload.image_base64_4, payload.youtube_link, payload.is_recurring,
            payload.start_time, payload.end_time, payload.available_days, payload.available_times
        ))
        event_id = cursor.fetchone()[0]
        
        if payload.booking_model == 'session':
            generate_session_slots_for_event(
                cursor, host_id, event_id, 
                payload.available_days, 
                payload.available_times, 
                payload.session_duration_mins
            )
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Event created successfully!", "event_id": event_id, "slug": slug}

@app.post("/api/host/events/{event_id}/update")
def host_update_event(event_id: int, payload: EventCreate, user = Depends(require_role(["host", "admin"]))):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        if user["role"] != "admin":
            cursor.execute("SELECT id FROM hosts WHERE user_id = %s", (user["user_id"],))
            host_row = cursor.fetchone()
            if not host_row:
                raise HTTPException(status_code=403, detail="Not a host.")
            host_id = host_row[0]
            
            cursor.execute("SELECT id FROM events WHERE id = %s AND host_id = %s", (event_id, host_id))
            if not cursor.fetchone():
                raise HTTPException(status_code=403, detail="Not your event.")
                
        event_dt = None
        if payload.event_date:
            try:
                event_dt = datetime.fromisoformat(payload.event_date.replace("Z", "+00:00"))
            except Exception:
                pass
            
        # Construct update fields dynamically based on whether images were provided or not
        update_fields = [
            "title=%s", "description=%s", "category=%s", "price_per_person=%s", "capacity=%s",
            "location_name=%s", "location_area=%s", "event_date=%s", "included=%s", "is_recurring=%s", "youtube_link=%s",
            "listing_type=%s", "booking_model=%s", "starting_rate=%s", "service_area=%s", "occasion_types=%s",
            "portfolio_url=%s", "availability_note=%s", "session_duration_mins=%s", "max_per_session=%s", "advance_notice_hours=%s",
            "start_time=%s", "end_time=%s", "available_days=%s", "available_times=%s"
        ]
        update_values = [
            payload.title, payload.description, payload.category, payload.price_per_person, payload.capacity,
            payload.location_name, payload.location_area, event_dt, payload.included or '[]', payload.is_recurring, payload.youtube_link,
            payload.listing_type, payload.booking_model, payload.starting_rate, payload.service_area, payload.occasion_types,
            payload.portfolio_url, payload.availability_note, payload.session_duration_mins, payload.max_per_session, payload.advance_notice_hours,
            payload.start_time, payload.end_time, payload.available_days, payload.available_times
        ]
        
        if payload.image_base64:
            update_fields.append("image_url=%s")
            update_values.append(payload.image_base64)
            
        if payload.image_base64_2:
            update_fields.append("image_url_2=%s")
            update_values.append(payload.image_base64_2)
            
        if payload.image_base64_3:
            update_fields.append("image_url_3=%s")
            update_values.append(payload.image_base64_3)
            
        if payload.image_base64_4:
            update_fields.append("image_url_4=%s")
            update_values.append(payload.image_base64_4)
            
        update_values.append(event_id)
        
        cursor.execute(f"""
            UPDATE events 
            SET {", ".join(update_fields)}
            WHERE id = %s
            RETURNING host_id
        """, tuple(update_values))
        
        row = cursor.fetchone()
        if row and payload.booking_model == 'session':
            ev_host_id = row[0]
            generate_session_slots_for_event(
                cursor, ev_host_id, event_id, 
                payload.available_days, 
                payload.available_times, 
                payload.session_duration_mins
            )
            
        conn.commit()
    finally:
        release_conn(conn)
    return {"message": "Event updated successfully!"}

@app.post("/api/events/{event_id}/bookings/{booking_id}/promote")
def promote_attendee(event_id: int, booking_id: int, user = Depends(require_role(["host", "admin"]))):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        if user["role"] != 'admin':
            cursor.execute("SELECT id FROM hosts WHERE user_id = %s", (user["user_id"],))
            host_row = cursor.fetchone()
            if not host_row:
                raise HTTPException(403, "Not authorized.")
            host_id = host_row[0]
            
            cursor.execute("SELECT id FROM events WHERE id = %s AND host_id = %s", (event_id, host_id))
            if not cursor.fetchone():
                raise HTTPException(403, "Not authorized to promote attendees for this event.")
                
        cursor.execute("SELECT id, booking_status, group_size FROM bookings WHERE id = %s AND event_id = %s FOR UPDATE", (booking_id, event_id))
        booking = cursor.fetchone()
        if not booking:
            raise HTTPException(404, "Booking not found")
        b_id, b_status, g_size = booking
        if b_status != "waitlist" and b_status != "processing":
            raise HTTPException(400, "Attendee is not in waitlist or processing status")
            
        cursor.execute("SELECT id, capacity, booked_count, status FROM events WHERE id = %s FOR UPDATE", (event_id,))
        event = cursor.fetchone()
        if not event or event[3] != 'published':
            raise HTTPException(404, "Event not active")
        e_id, cap, booked, ev_status = event
        
        spots_left = cap - booked
        if spots_left < g_size:
            raise HTTPException(400, "Not enough spots in the event capacity to promote this booking.")
            
        cursor.execute("UPDATE bookings SET booking_status = 'confirmed', payment_status = 'paid' WHERE id = %s", (booking_id,))
        cursor.execute("UPDATE events SET booked_count = booked_count + %s WHERE id = %s", (g_size, event_id))
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Transaction failed: {str(e)}")
    finally:
        release_conn(conn)
    return {"status": "success", "message": "Attendee promoted to active registration."}

@app.get("/track/{tracking_id}", include_in_schema=False)
def track_page(request: Request, tracking_id: str):
    prefix = tracking_id.upper()[:3]
    if prefix == "HR-":
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.client_name, h.occasion_type, h.event_date, h.status, h.message, h.budget_range, h.created_at, u.full_name as artist_name, u.email as artist_email, u.phone as artist_phone, b.payment_status, b.fee_amount
                FROM hire_requests h
                JOIN hosts ho ON h.host_id = ho.id
                JOIN users u ON ho.user_id = u.id
                LEFT JOIN bookings b ON b.hire_request_id = h.id
                WHERE h.tracking_id = %s
            """, (tracking_id.upper(),))
            row = cursor.fetchone()
            if not row:
                return RedirectResponse(url="/?error=invalid_tracking")
            data = {
                "tracking_id": tracking_id.upper(),
                "client_name": row[0],
                "occasion": row[1],
                "event_date": row[2],
                "status": row[3],
                "message": row[4],
                "budget": row[5],
                "created_at": row[6],
                "artist_name": row[7],
                "artist_email": row[8],
                "artist_phone": row[9],
                "payment_status": row[10],
                "fee_amount": row[11]
            }
            return templates.TemplateResponse("track_hire.html", {"request": request, "data": data})
        finally:
            release_conn(conn)
    elif prefix == "SB-":
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.name, b.booking_status, hs.slot_time, hs.duration_mins, u.full_name as host_name, u.email as host_email, u.phone as host_phone
                FROM bookings b
                JOIN host_slots hs ON b.slot_id = hs.id
                JOIN events e ON b.event_id = e.id
                JOIN hosts h ON e.host_id = h.id
                JOIN users u ON h.user_id = u.id
                WHERE b.tracking_id = %s
            """, (tracking_id.upper(),))
            row = cursor.fetchone()
            if not row:
                return RedirectResponse(url="/?error=invalid_tracking")
            data = {
                "tracking_id": tracking_id.upper(),
                "client_name": row[0],
                "status": row[1],
                "slot_time": row[2],
                "duration_mins": row[3],
                "host_name": row[4],
                "host_email": row[5],
                "host_phone": row[6]
            }
            return templates.TemplateResponse("track_session.html", {"request": request, "data": data})
        finally:
            release_conn(conn)
    else:
        # Fallback to homepage so user can track DH- tickets via modal
        return RedirectResponse(url=f"/?track={tracking_id}")

@app.post("/api/track/{tracking_id}/cancel")
def cancel_hire_request(tracking_id: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, status FROM hire_requests WHERE tracking_id = %s", (tracking_id.upper(),))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Tracking ID not found")
            
        hr_id, status = row
        if status in ('completed', 'rejected', 'cancelled'):
            raise HTTPException(400, "Cannot cancel this request in its current state")
            
        cursor.execute("UPDATE hire_requests SET status = 'cancelled' WHERE id = %s", (hr_id,))
        cursor.execute("UPDATE bookings SET booking_status = 'cancelled' WHERE hire_request_id = %s", (hr_id,))
        
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, str(e))
    finally:
        release_conn(conn)

@app.post("/api/track/{tracking_id}/pay")
def pay_hire_request(tracking_id: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM hire_requests WHERE tracking_id = %s", (tracking_id.upper(),))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Tracking ID not found")
            
        hr_id = row[0]
        
        cursor.execute("UPDATE bookings SET payment_status = 'verifying' WHERE hire_request_id = %s", (hr_id,))
        
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, str(e))
    finally:
        release_conn(conn)

@app.get("/api/bookings/track/{tracking_id}", response_model=TrackingResponse)
def track_booking(tracking_id: str):
    """
    Public tracking endpoint. 
    Returns the current status, payment verification, and group details.
    Reveals the specific venue only at 3 PM the day before the event.
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                b.tracking_id, b.name, b.group_size, b.preferred_date,
                b.preferred_time, b.venue_type, b.booking_status, b.payment_status, b.fee_amount,
                g.venue_name, g.meet_date, g.meet_time, b.current_location, b.preferred_location,
                b.payment_method, b.payment_sender_digits, b.preferred_meeting_point,
                b.id, g.id, b.rejection_reason, b.referral_code, b.is_verified,
                b.interests, b.expectations, b.wants_pickup, b.wants_dropoff, b.vibe, b.discount_amount
            FROM bookings b
            LEFT JOIN group_members gm ON gm.booking_id = b.id
            LEFT JOIN meetup_groups g  ON g.id = gm.group_id
            WHERE b.tracking_id = %s OR b.phone = %s
            ORDER BY b.created_at DESC
            LIMIT 1
            """,
            (tracking_id.upper(), tracking_id),
        )
        row = cursor.fetchone()
        
        group_members = []
        rated_member_ids = []
        if row and row[18]: # group_id exists
            booking_id = row[17]
            group_id = row[18]
            # Get members
            cursor.execute(
                """
                SELECT b.name, b.phone, b.age, b.id,        
                       (SELECT AVG(score) FROM user_ratings WHERE ratee_id = b.id) as avg_rating
                FROM group_members gm
                JOIN bookings b ON b.id = gm.booking_id     
                WHERE gm.group_id = %s AND b.id != %s       
                """,
                (group_id, booking_id)
            )
            members = cursor.fetchall()
            for m in members:
                group_members.append({
                    "name": m[0],
                    "phone": m[1],
                    "age": m[2],
                    "id": m[3],
                    "rating": round(float(m[4]), 1) if m[4] is not None else 0
                })
            
            # Get already rated members by this user in this group
            cursor.execute(
                "SELECT ratee_id FROM user_ratings WHERE rater_id = %s AND group_id = %s",
                (booking_id, group_id)
            )
            rated_member_ids = [r[0] for r in cursor.fetchall()]
            
        cursor.close()
    finally:
        release_conn(conn)

    if not row:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")

    venue_name = row[9]
    meet_date  = row[10]
    meet_time  = row[11]

    # Visibility logic: Hide event details until 3 PM the day BEFORE meet_date
    if meet_date:
        reveal_dt = datetime.combine(meet_date - timedelta(days=1), time(15, 0))
        if datetime.now() < reveal_dt:
            venue_name = "Revealing soon (3 PM day before event)"
            # Date and Time should stay visible for planning, only name is hidden

    return TrackingResponse(
        tracking_id=row[0],
        name=row[1],
        group_size=row[2],
        preferred_date=row[3],
        preferred_time=format_time_12h(row[4]),
        venue_type=row[5],
        booking_status=row[6],
        payment_status=row[7],
        fee_amount=float(row[8]),
        assigned_venue=venue_name,
        meet_date=meet_date,
        meet_time=format_time_12h(meet_time),
        current_location=row[12],
        preferred_location=row[13],
        payment_method=row[14],
        payment_sender_digits=row[15],
        preferred_meeting_point=row[16],
        group_members=group_members,
        rated_member_ids=rated_member_ids,
        rejection_reason=row[19],
        assigned_group_id=row[18],
        referral_code=row[20],
        is_verified=row[21],
        interests=row[22],
        expectations=row[23],
        wants_pickup=row[24],
        wants_dropoff=row[25],
        vibe=row[26],
        discount_amount=float(row[27] or 0.0)
    )


@app.post("/api/bookings/rate")
def rate_mate(payload: RatingCreate, tracking_id: str = Header(...)):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Get rater_id from tracking_id (or phone)
        cursor.execute("SELECT id FROM bookings WHERE tracking_id = %s OR phone = %s ORDER BY created_at DESC LIMIT 1", (tracking_id.upper(), tracking_id))
        rater = cursor.fetchone()
        if not rater:
            raise HTTPException(status_code=404, detail="Rater not found.")
        rater_id = rater[0]

        # Ensure rater and ratee are in the same group
        cursor.execute(
            """
            SELECT group_id FROM group_members 
            WHERE group_id = %s AND booking_id IN (%s, %s)
            """,
            (payload.group_id, rater_id, payload.ratee_id)
        )
        if len(cursor.fetchall()) < 2:
            raise HTTPException(status_code=403, detail="You can only rate people in your group.")

        cursor.execute(
            """
            INSERT INTO user_ratings (rater_id, ratee_id, group_id, score, comment)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rater_id, ratee_id, group_id) DO UPDATE 
            SET score = EXCLUDED.score, comment = EXCLUDED.comment
            """,
            (rater_id, payload.ratee_id, payload.group_id, payload.score, payload.comment)
        )
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Rating submitted successfully!"}


@app.get("/api/bookings/chat/{group_id}")
def get_chat_messages(group_id: int, tracking_id: str = Header(...)):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Verify user is in the group (can match tracking_id or phone)
        cursor.execute(
            """
            SELECT 1 FROM group_members gm 
            JOIN bookings b ON b.id = gm.booking_id 
            WHERE gm.group_id = %s AND (b.tracking_id = %s OR b.phone = %s)
            """,
            (group_id, tracking_id.upper(), tracking_id)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Not authorized to access this chat.")

        # Check group status (no chat if completed)
        cursor.execute("SELECT status FROM meetup_groups WHERE id = %s", (group_id,))
        g_status = cursor.fetchone()
        if g_status and g_status[0] == 'completed':
            return [] # Chat is deleted

        cursor.execute(
            """
            SELECT c.message, b.name, c.created_at, b.id = (SELECT id FROM bookings WHERE tracking_id = %s OR phone = %s ORDER BY created_at DESC LIMIT 1) as is_me
            FROM group_chats c
            JOIN bookings b ON b.id = c.sender_id
            WHERE c.group_id = %s
            ORDER BY c.created_at ASC
            """,
            (tracking_id.upper(), tracking_id, group_id)
        )
        rows = cursor.fetchall()
        cursor.close()
    finally:
        release_conn(conn)
    
    return [
        {"message": r[0], "sender": r[1], "time": r[2].isoformat(), "is_me": r[3]}
        for r in rows
    ]


@app.post("/api/bookings/chat")
def send_chat_message(payload: MessageCreate, tracking_id: str = Header(...)):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Get sender_id (match tracking_id or phone)
        cursor.execute("SELECT id FROM bookings WHERE tracking_id = %s OR phone = %s ORDER BY created_at DESC LIMIT 1", (tracking_id.upper(), tracking_id))
        sender = cursor.fetchone()
        if not sender: raise HTTPException(status_code=404, detail="Sender not found.")
        sender_id = sender[0]

        # Verify group status
        cursor.execute("SELECT status FROM meetup_groups WHERE id = %s", (payload.group_id,))
        g_status = cursor.fetchone()
        if not g_status or g_status[0] == 'completed':
            raise HTTPException(status_code=403, detail="Chat is disabled for completed meetups.")

        # Ensure user is in the group
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND booking_id = %s",
            (payload.group_id, sender_id)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="You are not in this group.")

        cursor.execute(
            "INSERT INTO group_chats (group_id, sender_id, message) VALUES (%s, %s, %s)",
            (payload.group_id, sender_id, payload.message)
        )
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Sent"}


# --- LOCATIONS (PUBLIC) ---

@app.get("/api/locations", response_model=list[LocationResponse])
def list_locations_public():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, is_active FROM locations WHERE is_active = TRUE ORDER BY name ASC")
        rows = cursor.fetchall()
        cursor.close()
    finally:
        release_conn(conn)
    return [{"id": r[0], "name": r[1], "is_active": r[2]} for r in rows]

@app.post("/api/partnerships")
def create_partnership(payload: PartnershipCreate):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO partnership_requests (restaurant_name, contact_number)
            VALUES (%s, %s)
            """,
            (payload.restaurant_name, payload.contact_number)
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Could not submit request.")
    finally:
        release_conn(conn)
    return {"message": "Partnership request submitted successfully."}


# --- BLOGS (PUBLIC) ---

@app.get("/api/blogs", response_model=list[BlogResponse])
def list_blogs():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, slug, content, keywords, seo_description, image_url, image_alt, badge_text, likes, shares, status, author, created_at, is_pivoted FROM blogs WHERE status = 'published' ORDER BY is_pivoted DESC, created_at DESC")
        rows = cursor.fetchall()
        return [
            BlogResponse(
                id=r[0], title=r[1], slug=r[2], content=r[3], 
                keywords=r[4], seo_description=r[5], image_url=r[6], 
                image_alt=r[7], badge_text=r[8], likes=r[9], shares=r[10],
                status=r[11], author=r[12], created_at=str(r[13]),
                is_pivoted=r[14]
            ) for r in rows
        ]
    finally:
        release_conn(conn)


@app.get("/api/blogs/{slug}", response_model=BlogResponse)
def get_blog(slug: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, slug, content, keywords, seo_description, image_url, image_alt, badge_text, likes, shares, status, author, created_at, is_pivoted FROM blogs WHERE slug = %s", (slug,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Blog not found")
        return BlogResponse(
            id=row[0], title=row[1], slug=row[2], content=row[3], 
            keywords=row[4], seo_description=row[5], image_url=row[6], 
            image_alt=row[7], badge_text=row[8], likes=row[9], shares=row[10],
            status=row[11], author=row[12], created_at=str(row[13]),
            is_pivoted=row[14]
        )
    finally:
        release_conn(conn)


@app.get("/blog/{slug}", include_in_schema=False)
def serve_blog_detail(request: Request, slug: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Increment view count
        cursor.execute("UPDATE blogs SET views = views + 1 WHERE slug = %s", (slug,))
        conn.commit()
        
        cursor.execute("SELECT id, title, content, keywords, seo_description, image_url, image_alt, likes, shares, author, author_title, author_image_url, created_at, badge_text, slug, views FROM blogs WHERE slug = %s AND status = 'published'", (slug,))
        row = cursor.fetchone()
        if not row:
            return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
        
        blog_data = {
            "id": row[0],
            "title": row[1] or "Untitled",
            "content": row[2] or "",
            "keywords": row[3] or "",
            "description": row[4] or "",
            "image": row[5] or "",
            "image_alt": row[6] or "",
            "likes": row[7] or 0,
            "shares": row[8] or 0,
            "author": row[9] or "Team DekhaHok",
            "author_title": row[10] or "Contributor",
            "author_image_url": row[11] or "",
            "date": local_time_filter(row[12]),
            "badge": row[13] or "Story",
            "slug": row[14],
            "views": row[15] or 0
        }
        
        # Fetch other blogs
        cursor.execute("SELECT title, slug, image_url, badge_text, created_at, views FROM blogs WHERE status = 'published' AND slug != %s ORDER BY RANDOM() LIMIT 3", (slug,))
        others = cursor.fetchall()
        other_blogs = []
        for o in others:
            other_blogs.append({
                "title": o[0],
                "slug": o[1],
                "image": o[2],
                "badge": o[3] or "Story",
                "date": local_time_filter(o[4]),
                "views": o[5] or 0
            })
            
        return templates.TemplateResponse("blog_detail.html", {"request": request, "blog": blog_data, "other_blogs": other_blogs})
    except Exception as e:
        print(f"Error serving blog {slug}: {e}")
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    finally:
        release_conn(conn)


# ── Blog Interactions ──────────────────────────────────────────────────────

@app.post("/api/blogs/{blog_id}/like")
def like_blog(blog_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE blogs SET likes = likes + 1 WHERE id = %s RETURNING likes", (blog_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Blog not found")
        conn.commit()
        return {"likes": row[0]}
    finally:
        release_conn(conn)

@app.post("/api/blogs/{blog_id}/share")
def share_blog(blog_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE blogs SET shares = shares + 1 WHERE id = %s RETURNING shares", (blog_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Blog not found")
        conn.commit()
        return {"shares": row[0]}
    finally:
        release_conn(conn)

@app.get("/api/blogs/{blog_id}/comments", response_model=list[BlogCommentResponse])
def list_blog_comments(blog_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, blog_id, user_name, comment, created_at FROM blog_comments WHERE blog_id = %s ORDER BY created_at DESC", (blog_id,))
        rows = cursor.fetchall()
        return [
            BlogCommentResponse(
                id=r[0], blog_id=r[1], user_name=r[2], comment=r[3], created_at=str(r[4])
            ) for r in rows
        ]
    finally:
        release_conn(conn)

@app.post("/api/blogs/{blog_id}/comments")
def add_blog_comment(blog_id: int, payload: BlogCommentCreate):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO blog_comments (blog_id, user_name, comment) VALUES (%s, %s, %s) RETURNING id, created_at",
            (blog_id, payload.user_name, payload.comment)
        )
        row = cursor.fetchone()
        conn.commit()
        return {"id": row[0], "created_at": str(row[1])}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_conn(conn)


# --- PUBLIC DISCOVERY ---

@app.get("/api/public/stats")
def public_stats():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE booking_status = 'waitlist'")
        waitlist_count = cursor.fetchone()[0]
        return {
            "waitlist_count": waitlist_count
        }
    finally:
        release_conn(conn)

@app.get("/api/public/groups", response_model=list[PublicGroupResponse])
def list_public_groups(location: Optional[str] = Query(None)):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Show latest 5 groups that are open, confirmed or completed
        query = """
            SELECT g.id, g.group_code, g.venue_name, g.meet_date, g.meet_time, g.group_size,
                   (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) as member_count,
                   g.status, g.image_url
            FROM meetup_groups g
            WHERE g.status IN ('open', 'confirmed', 'completed')
        """
        params = []
        if location:
            query += " AND g.venue_name ILIKE %s"
            params.append(f"%{location}%")
        
        query += " ORDER BY g.meet_date DESC LIMIT 5"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            results.append(PublicGroupResponse(
                id=r[0], group_code=r[1], venue_name=r[2],
                meet_date=r[3], meet_time=format_time_12h(r[4]),
                group_size=r[5], member_count=r[6], status=r[7], image_url=r[8]
            ))
        return results
    finally:
        release_conn(conn)


@app.get("/api/public/reviews")
def list_public_reviews():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Fetch high ratings with comments for social proof
        cursor.execute("""
            SELECT DISTINCT ON (b.name) r.comment, b.name, b.age, g.venue_name, r.score, r.created_at
            FROM user_ratings r
            JOIN bookings b ON b.id = r.ratee_id
            JOIN meetup_groups g ON g.id = r.group_id
            WHERE r.score >= 4 AND r.comment IS NOT NULL AND r.comment != ''
            ORDER BY b.name, r.created_at DESC
            LIMIT 6
        """)
        rows = cursor.fetchall()
        # Sort back to chronological order after DISTINCT ON
        rows.sort(key=lambda x: x[5], reverse=True)
        
        return [
            {"comment": r[0], "name": r[1], "age": r[2], "venue": r[3], "score": r[4]}
            for r in rows
        ]
    finally:
        release_conn(conn)


@app.post("/api/coupons/validate")
def validate_coupon(payload: dict = Body(...)):
    code = payload.get("code", "").upper()
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT discount_type, value, usage_limit, expires_at FROM coupons WHERE code = %s", (code,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invalid coupon code.")
        
        d_type, d_val, limit, expires = row
        
        # Check expiry
        if expires and expires < datetime.now(expires.tzinfo):
            raise HTTPException(status_code=400, detail="Coupon expired.")
            
        # Check usage limit
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE coupon_code = %s", (code,))
        used_count = cursor.fetchone()[0]
        if limit and used_count >= limit:
            raise HTTPException(status_code=400, detail="Usage limit reached.")
            
        return {"discount_type": d_type, "value": float(d_val)}
    finally:
        release_conn(conn)


@app.get("/api/admin/coupons")
def admin_list_coupons(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, discount_type, value, usage_limit, expires_at, created_at FROM coupons ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [
            {
                "id": r[0], "code": r[1], "discount_type": r[2], "value": float(r[3]),
                "usage_limit": r[4], "expires_at": str(r[5]) if r[5] else None,
                "created_at": str(r[6])
            } for r in rows
        ]
    finally:
        release_conn(conn)


@app.post("/api/admin/coupons")
def admin_create_coupon(payload: dict = Body(...), x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO coupons (code, discount_type, value, usage_limit, expires_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (payload['code'].upper(), payload['discount_type'], payload['value'], payload.get('usage_limit'), payload.get('expires_at'))
        )
        conn.commit()
        return {"id": cursor.fetchone()[0]}
    finally:
        release_conn(conn)


@app.delete("/api/admin/coupons/{coupon_id}")
def admin_delete_coupon(coupon_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM coupons WHERE id = %s", (coupon_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        release_conn(conn)


@app.get("/api/admin/match-suggestions")
def admin_match_suggestions(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Group pending bookings by vibe and date to suggest clusters
        cursor.execute("""
            SELECT vibe, preferred_date, group_size, COUNT(*) as count
            FROM bookings
            WHERE booking_status = 'processing' AND payment_status = 'paid'
            GROUP BY vibe, preferred_date, group_size
            HAVING COUNT(*) >= 1
            ORDER BY preferred_date ASC, count DESC
        """)
        rows = cursor.fetchall()
        
        suggestions = []
        for r in rows:
            vibe, p_date, size, count = r
            # Get the member details for this potential group
            cursor.execute("""
                SELECT tracking_id, name, preferred_location, interests
                FROM bookings
                WHERE vibe = %s AND preferred_date = %s AND group_size = %s AND booking_status = 'processing' AND payment_status = 'paid'
            """, (vibe, p_date, size))
            members = [
                {"tracking_id": m[0], "name": m[1], "location": m[2], "interests": m[3]} 
                for m in cursor.fetchall()
            ]
            
            suggestions.append({
                "vibe": vibe,
                "date": str(p_date),
                "size": size,
                "potential_count": count,
                "members": members
            })
        return suggestions
    finally:
        release_conn(conn)


# ===========================================================================
# ADMIN
# ===========================================================================

@app.get("/api/admin/partnerships")
def admin_list_partnerships(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, restaurant_name, contact_number, status, created_at FROM partnership_requests ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [{"id": r[0], "restaurant_name": r[1], "contact_number": r[2], "status": r[3], "created_at": str(r[4])} for r in rows]
    finally:
        release_conn(conn)

@app.patch("/api/admin/partnerships/{partnership_id}")
def admin_update_partnership(partnership_id: int, payload: PartnershipUpdate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE partnership_requests SET status = %s WHERE id = %s", (payload.status, partnership_id))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Partnership request not found.")
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Partnership updated."}

@app.delete("/api/admin/partnerships/{partnership_id}")
def admin_delete_partnership(partnership_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM partnership_requests WHERE id = %s", (partnership_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Partnership request not found.")
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Partnership deleted."}

@app.get("/api/admin/dashboard")
def admin_dashboard(x_admin_key: str = Header(...)):
    """
    Fetches aggregate statistics for the admin overview, 
    including revenue, booking counts by status, and overall totals.
    """
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM bookings) AS total,
                (SELECT COUNT(*) FROM bookings WHERE booking_status = 'processing') AS processing,
                (SELECT COUNT(*) FROM bookings WHERE booking_status = 'confirmed') AS confirmed,
                (SELECT COUNT(*) FROM bookings WHERE booking_status = 'completed') AS completed,
                (SELECT COUNT(*) FROM bookings WHERE payment_status = 'paid') AS paid,
                (SELECT COUNT(*) FROM bookings WHERE payment_status = 'unpaid') AS unpaid,
                (SELECT COALESCE(SUM(b.fee_amount), 0) FROM bookings b JOIN events e ON b.event_id = e.id WHERE b.payment_status = 'paid' AND e.status = 'completed') AS revenue,
                (SELECT COUNT(*) FROM meetup_groups WHERE status = 'open') AS open_groups,
                (SELECT COUNT(*) FROM locations WHERE is_active = true) AS active_locations,
                (SELECT COUNT(*) FROM hosts WHERE verification_status = 'VERIFIED') AS verified_hosts,
                (SELECT COUNT(*) FROM events WHERE status = 'published') AS published_events,
                (SELECT COALESCE(SUM(b.group_size), 0) FROM bookings b JOIN events e ON b.event_id = e.id WHERE e.status = 'completed') AS tickets_issued,
                (SELECT COUNT(*) FROM hosts WHERE verification_status = 'PENDING') AS pending_hosts
            """
        )
        row = cursor.fetchone()
        cursor.close()
    finally:
        release_conn(conn)

    return {
        "total":      row[0] or 0,
        "processing": row[1] or 0,
        "confirmed":  row[2] or 0,
        "completed":  row[3] or 0,
        "paid":       row[4] or 0,
        "unpaid":     row[5] or 0,
        "revenue":    float(row[6] or 0),
        "open_groups": row[7] or 0,
        "active_locations": row[8] or 0,
        "verified_hosts": row[9] or 0,
        "published_events": row[10] or 0,
        "tickets_issued": row[11] or 0,
        "pending_hosts": row[12] or 0,
    }


@app.get("/api/admin/bookings")
def admin_list_bookings(
    status:     Optional[str] = Query(None),
    payment:    Optional[str] = Query(None),
    group_size: Optional[int] = Query(None),
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)

    filters, params = [], []
    if status:
        filters.append("b.booking_status = %s"); params.append(status)
    if payment:
        filters.append("b.payment_status = %s"); params.append(payment)
    if group_size:
        filters.append("b.group_size = %s");     params.append(group_size)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT b.id, b.tracking_id, b.name, b.phone, b.email, b.age, b.group_size,
                   b.preferred_date, b.preferred_time, b.venue_type, b.conversation_style, b.preferred_people,
                   b.current_location, b.preferred_location, b.preferred_meeting_point,
                   b.fee_amount, b.payment_status, b.payment_method, b.payment_sender_digits, b.booking_status,
                   b.assigned_group_id, b.admin_notes, b.is_verified, b.wants_pickup, b.wants_dropoff, b.created_at,
                   b.interests, b.expectations, b.event_id, e.title as event_title
            FROM bookings b
            LEFT JOIN events e ON b.event_id = e.id
            {where}
            ORDER BY b.created_at DESC
            """,
            params,
        )
        rows = cursor.fetchall()
        cursor.close()
    finally:
        release_conn(conn)

    return [
        {
            "id":                r[0],
            "tracking_id":       r[1],
            "name":              r[2],
            "phone":             r[3],
            "email":             r[4],
            "age":               r[5],
            "group_size":        r[6],
            "preferred_date":    str(r[7]),
            "preferred_time":    format_time_12h(r[8]),
            "venue_type":        r[9],
            "conversation_style": r[10],
            "preferred_people":  r[11],
            "current_location":   r[12],
            "preferred_location": r[13],
            "preferred_meeting_point": r[14],
            "fee_amount":        float(r[15]),
            "payment_status":    r[16],
            "payment_method":    r[17],
            "payment_sender_digits": r[18],
            "booking_status":    r[19],
            "assigned_group_id": r[20],
            "admin_notes":       r[21],
            "is_verified":       r[22],
            "wants_pickup":      r[23],
            "wants_dropoff":     r[24],
            "created_at":        str(r[25]),
            "interests":         r[26],
            "expectations":      r[27],
            "event_id":          r[28],
            "event_title":       r[29] or "DekhaHok Circle Adda",
        }
        for r in rows
    ]


@app.patch("/api/admin/bookings/{booking_id}")
def admin_update_booking(
    booking_id: int,
    payload: AdminBookingUpdate,
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)
    updates = {}
    if payload.payment_status is not None: updates["payment_status"] = payload.payment_status
    if payload.booking_status is not None: updates["booking_status"] = payload.booking_status
    if payload.admin_notes    is not None: updates["admin_notes"]    = payload.admin_notes
    if payload.rejection_reason is not None: updates["rejection_reason"] = payload.rejection_reason
    if payload.is_verified is not None: updates["is_verified"] = payload.is_verified
    if payload.wants_pickup is not None: updates["wants_pickup"] = payload.wants_pickup
    if payload.wants_dropoff is not None: updates["wants_dropoff"] = payload.wants_dropoff

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    values = list(updates.values()) + [booking_id]

    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Check if setting to 'completed' and booking has a phone number
        if payload.booking_status == 'completed':
            cursor.execute("SELECT phone, booking_status FROM bookings WHERE id = %s", (booking_id,))
            row = cursor.fetchone()
            if row and row[1] != 'completed':
                if not row[0] or len(row[0].strip()) < 8:
                    pass

        cursor.execute(f"UPDATE bookings SET {set_clause} WHERE id = %s", values)
        
        # Send Notification to User if booking status was updated
        if payload.booking_status:
            cursor.execute("SELECT user_id, event_id FROM bookings WHERE id = %s", (booking_id,))
            b_row = cursor.fetchone()
            if b_row and b_row[0]:
                b_user_id = b_row[0]
                cursor.execute("""
                    INSERT INTO notifications (user_id, type, title, message, action_url)
                    VALUES (%s, 'booking_update', 'Booking Update', %s, %s)
                """, (b_user_id, f"Your booking status has been updated to '{payload.booking_status}'.", "/#status-tracking-view"))
                
        conn.commit()
        
        if payload.booking_status == 'completed':
            cursor.execute("SELECT referral_code FROM bookings WHERE id = %s", (booking_id,))
            row = cursor.fetchone()
            if row:
                ref_code = row[0]
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE referred_by = %s", (ref_code,))
                ref_count = cursor.fetchone()[0]
                if ref_count > 0:
                    cursor.execute("UPDATE bookings SET is_verified = TRUE WHERE id = %s", (booking_id,))
                    conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Booking not found.")
            
        if payload.is_verified is True:
            cursor.execute("SELECT phone FROM bookings WHERE id = %s", (booking_id,))
            prow = cursor.fetchone()
            if prow:
                phone_to_verify = prow[0]
                cursor.execute("UPDATE bookings SET is_verified = TRUE WHERE phone = %s", (phone_to_verify,))
        
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)

    return {"message": "Booking updated."}


@app.delete("/api/admin/bookings/{booking_id}")
def admin_delete_booking(booking_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Booking not found.")
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Booking deleted."}

@app.get("/api/admin/groups")
def admin_list_groups(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT g.id, g.group_code, g.venue_name, g.meet_date, g.meet_time,
                   g.group_size, g.status, g.image_url
            FROM meetup_groups g
            ORDER BY g.meet_date DESC
            """
        )
        group_rows = cursor.fetchall()

        results = []
        for gr in group_rows:
            gid = gr[0]
            cursor.execute(
                """
                SELECT b.id, b.name, b.phone, b.tracking_id
                FROM group_members gm
                JOIN bookings b ON b.id = gm.booking_id
                WHERE gm.group_id = %s
                """,
                (gid,),
            )
            member_rows = cursor.fetchall()
            members = [
                {"id": m[0], "name": m[1], "phone": m[2], "tracking_id": m[3]}
                for m in member_rows
            ]

            results.append({
                "id":           gr[0],
                "group_code":   gr[1],
                "venue_name":   gr[2],
                "meet_date":    str(gr[3]),
                "meet_time":    format_time_12h(gr[4]),
                "group_size":   gr[5],
                "status":       gr[6],
                "image_url":    gr[7],
                "member_count": len(members),
                "members":      members,
            })
        cursor.close()
    finally:
        release_conn(conn)

    return results


@app.delete("/api/admin/groups/{group_id}/members/{booking_id}")
def admin_remove_group_member(
    group_id: int,
    booking_id: int,
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM group_members WHERE group_id = %s AND booking_id = %s",
            (group_id, booking_id),
        )
        cursor.execute(
            "UPDATE bookings SET assigned_group_id = NULL, booking_status = 'processing' WHERE id = %s",
            (booking_id,),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Member not found in group.")
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Member removed from group."}


@app.post("/api/admin/groups", status_code=201)
def admin_create_group(payload: GroupCreate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)

    date_str   = payload.meet_date.strftime("%Y%m%d")
    suffix     = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    group_code = f"GRP-{date_str}-{suffix}"

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO meetup_groups (group_code, venue_name, meet_date, meet_time, group_size, image_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (group_code, payload.venue_name, payload.meet_date, payload.meet_time, payload.group_size, payload.image_url),
        )
        group_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        print(f"[dekhahok] Create group error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_conn(conn)

    return {"id": group_id, "group_code": group_code, "message": "Group created."}


@app.post("/api/admin/groups/{group_id}/assign")
def admin_assign_members(
    group_id: int,
    payload: GroupAssign,
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, group_size FROM meetup_groups WHERE id = %s", (group_id,))
        group_row = cursor.fetchone()
        if not group_row:
            raise HTTPException(status_code=404, detail="Group not found.")
        g_size = group_row[1]

        if payload.booking_ids:
            cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = %s", (group_id,))
            current_count = cursor.fetchone()[0]
            if current_count + len(payload.booking_ids) > g_size:
                raise HTTPException(status_code=400, detail=f"Cannot assign {len(payload.booking_ids)} members. Group capacity exceeded.")

            format_strings = ','.join(['%s'] * len(payload.booking_ids))
            cursor.execute(f"SELECT id, group_size FROM bookings WHERE id IN ({format_strings})", tuple(payload.booking_ids))
            bookings_info = cursor.fetchall()
            
            if len(bookings_info) != len(payload.booking_ids):
                raise HTTPException(status_code=404, detail="One or more bookings not found.")
                
            for b_info in bookings_info:
                if b_info[1] != g_size:
                    raise HTTPException(status_code=400, detail=f"Booking {b_info[0]} has incompatible group size.")

        for booking_id in payload.booking_ids:
            cursor.execute(
                "INSERT INTO group_members (group_id, booking_id) VALUES (%s, %s) ON CONFLICT (booking_id) DO NOTHING",
                (group_id, booking_id),
            )
            cursor.execute(
                "UPDATE bookings SET booking_status = 'confirmed', assigned_group_id = %s WHERE id = %s",
                (group_id, booking_id),
            )

        conn.commit()
        cursor.close()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_conn(conn)

    return {"message": f"{len(payload.booking_ids)} booking(s) assigned to group {group_id}."}


@app.patch("/api/admin/groups/{group_id}")
def admin_update_group(
    group_id: int,
    payload: GroupUpdate,
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)

    updates = {}
    if payload.venue_name is not None: updates["venue_name"] = payload.venue_name
    if payload.meet_date  is not None: updates["meet_date"]  = payload.meet_date
    if payload.meet_time  is not None: updates["meet_time"]  = payload.meet_time
    if payload.group_size is not None: updates["group_size"] = payload.group_size
    if payload.status     is not None: updates["status"]     = payload.status
    if payload.image_url  is not None: updates["image_url"]  = payload.image_url

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    values = list(updates.values()) + [group_id]

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE meetup_groups SET {set_clause} WHERE id = %s", values)
        
        if updates.get("status") == 'completed':
            cursor.execute("DELETE FROM group_chats WHERE group_id = %s", (group_id,))

        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Group not found.")
        cursor.close()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_conn(conn)

    return {"message": "Group updated."}


@app.delete("/api/admin/groups/{group_id}")
def admin_delete_group(group_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM group_members WHERE group_id = %s", (group_id,))
        cursor.execute("DELETE FROM meetup_groups WHERE id = %s", (group_id,))
        conn.commit()
    finally:
        release_conn(conn)
    return {"message": "Group deleted."}


# --- PAYOUTS (ADMIN) ---

@app.get("/api/admin/payouts", include_in_schema=False)
def admin_list_payouts(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.id, e.title, e.event_date, e.host_payment_status,
                   u.full_name as host_name, u.phone as host_phone,
                   COALESCE(SUM(b.fee_amount), 0) as total_revenue,
                   COUNT(b.id) as paid_bookings,
                   h.revenue_share_pct
            FROM events e
            JOIN hosts h ON e.host_id = h.id
            JOIN users u ON h.user_id = u.id
            LEFT JOIN bookings b ON b.event_id = e.id AND b.payment_status = 'paid' AND b.booking_status = 'confirmed'
            WHERE e.status IN ('published', 'completed')
            GROUP BY e.id, u.full_name, u.phone, h.revenue_share_pct
            ORDER BY e.event_date DESC
        """)
        rows = cursor.fetchall()
        payouts = []
        for r in rows:
            total_rev = float(r[6])
            share = float(r[8] or 0.5)
            payouts.append({
                "event_id": r[0],
                "event_title": r[1],
                "event_date": r[2].isoformat() if r[2] else None,
                "host_payment_status": r[3] or 'unpaid',
                "host_name": r[4],
                "host_phone": r[5],
                "total_revenue": total_rev,
                "host_payout": total_rev * share,
                "platform_profit": total_rev * (1 - share),
                "paid_bookings": r[7]
            })
        return payouts
    finally:
        release_conn(conn)

class PayoutUpdate(BaseModel):
    host_payment_status: str

@app.patch("/api/admin/payouts/{event_id}", include_in_schema=False)
def admin_update_payout(event_id: int, payload: PayoutUpdate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET host_payment_status = %s WHERE id = %s", (payload.host_payment_status, event_id))
        conn.commit()
        return {"message": "Payout status updated"}
    finally:
        release_conn(conn)


# --- LOCATIONS (ADMIN) ---

@app.get("/api/admin/locations", response_model=list[LocationResponse])
def admin_list_locations(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, is_active FROM locations ORDER BY created_at DESC")
        loc_rows = cursor.fetchall()
        loc_dict = {loc[0]: loc[1] for loc in loc_rows}
        
        cursor.execute("SELECT id, location_id, name, is_active, latitude, longitude, point_type FROM meeting_points")
        point_rows = cursor.fetchall()
        
        points_map = {}
        for pr in point_rows:
            lid = pr[1]
            if lid not in points_map:
                points_map[lid] = []
            points_map[lid].append({
                "id": pr[0], "location_id": lid, "name": pr[2], "is_active": pr[3],
                "latitude": float(pr[4]) if pr[4] is not None else None,
                "longitude": float(pr[5]) if pr[5] is not None else None,
                "point_type": pr[6],
                "area_name": loc_dict.get(lid, "Unknown")
            })

        results = []
        for loc in loc_rows:
            results.append({
                "id": loc[0],
                "name": loc[1],
                "is_active": loc[2],
                "points": points_map.get(loc[0], [])
            })
            
        cursor.close()
    finally:
        release_conn(conn)
    return results


@app.post("/api/admin/locations", status_code=201)
def admin_create_location(payload: LocationCreate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO locations (name) VALUES (%s) RETURNING id", (payload.name,))
        location_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Location already exists or invalid data.")
    finally:
        release_conn(conn)
    return {"id": location_id, "message": "Location created."}


@app.get("/api/locations/{location_id}/points", response_model=list[MeetingPointResponse])
def list_meeting_points(location_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, location_id, name, is_active, latitude, longitude, point_type FROM meeting_points WHERE location_id = %s AND is_active = TRUE", (location_id,))
        rows = cursor.fetchall()
        return [MeetingPointResponse(id=r[0], location_id=r[1], name=r[2], is_active=r[3], latitude=float(r[4]) if r[4] is not None else None, longitude=float(r[5]) if r[5] is not None else None, point_type=r[6]) for r in rows]
    finally:
        release_conn(conn)


@app.get("/api/all-points", response_model=list[MeetingPointResponse])
def list_all_meeting_points():
    """Returns all active meeting points for the map."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.location_id, p.name, p.is_active, p.latitude, p.longitude, p.point_type, l.name
            FROM meeting_points p
            JOIN locations l ON l.id = p.location_id
            WHERE p.is_active = TRUE
        """)
        rows = cursor.fetchall()
        return [MeetingPointResponse(
            id=r[0], location_id=r[1], name=r[2], is_active=r[3], 
            latitude=float(r[4]) if r[4] is not None else None, 
            longitude=float(r[5]) if r[5] is not None else None, 
            point_type=r[6], area_name=r[7]
        ) for r in rows]
    finally:
        release_conn(conn)


@app.post("/api/admin/locations/{location_id}/points", response_model=MeetingPointResponse)
def create_meeting_point(location_id: int, payload: MeetingPointCreate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO meeting_points (location_id, name, latitude, longitude, point_type) VALUES (%s, %s, %s, %s, %s) RETURNING id, location_id, name, is_active, latitude, longitude, point_type",
            (location_id, payload.name, payload.latitude, payload.longitude, payload.point_type)
        )
        row = cursor.fetchone()
        conn.commit()
        return MeetingPointResponse(id=row[0], location_id=row[1], name=row[2], is_active=row[3], latitude=float(row[4]) if row[4] is not None else None, longitude=float(row[5]) if row[5] is not None else None, point_type=row[6])
    finally:
        release_conn(conn)


@app.delete("/api/admin/points/{point_id}")
def delete_meeting_point(point_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM meeting_points WHERE id = %s", (point_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Meeting point not found")
        conn.commit()
        return {"message": "Meeting point deleted"}
    finally:
        release_conn(conn)


@app.patch("/api/admin/points/{point_id}")
def admin_update_point(
    point_id: int,
    payload: MeetingPointCreate,
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE meeting_points SET name = %s, latitude = %s, longitude = %s, point_type = %s WHERE id = %s",
            (payload.name, payload.latitude, payload.longitude, payload.point_type, point_id)
        )
        conn.commit()
    finally:
        release_conn(conn)
    return {"message": "Point updated."}


@app.patch("/api/admin/locations/{location_id}")
def admin_update_location(
    location_id: int,
    is_active: bool,
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE locations SET is_active = %s WHERE id = %s", (is_active, location_id))
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Location updated."}


@app.delete("/api/admin/locations/{location_id}")
def admin_delete_location(location_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM locations WHERE id = %s", (location_id,))
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"message": "Location deleted."}


@app.post("/api/admin/blogs", response_model=BlogResponse)
def admin_create_blog(payload: BlogCreate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    if payload.slug:
        slug = payload.slug.strip()
    else:
        slug = payload.title.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == '-')
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO blogs (title, slug, content, keywords, seo_description, image_url, image_alt, badge_text, status, author, author_title, author_image_url, is_pivoted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            RETURNING id, created_at
            """,
            (payload.title, slug, payload.content, payload.keywords, payload.seo_description, payload.image_url, payload.image_alt, payload.badge_text, payload.status, payload.author, payload.author_title, payload.author_image_url, payload.is_pivoted)
        )
        row = cursor.fetchone()
        conn.commit()
        if not row:
            raise HTTPException(status_code=400, detail="Blog with this slug already exists.")
        return BlogResponse(
            id=row[0], title=payload.title, slug=slug, content=payload.content,
            keywords=payload.keywords, seo_description=payload.seo_description,
            image_url=payload.image_url, image_alt=payload.image_alt, badge_text=payload.badge_text,
            likes=0, shares=0,
            status=payload.status, author=payload.author,
            author_title=payload.author_title, author_image_url=payload.author_image_url,
            is_pivoted=payload.is_pivoted, created_at=str(row[1])
        )
    finally:
        release_conn(conn)

@app.patch("/api/admin/blogs/{blog_id}")
def admin_update_blog(blog_id: int, payload: BlogUpdate, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    updates = payload.dict(exclude_unset=True)
    if not updates: 
        return {"message": "No changes"}
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cols = []
        vals = []
        for k, v in updates.items():
            cols.append(f"{k} = %s")
            vals.append(v)
        
        vals.append(blog_id)
        query = f"UPDATE blogs SET {', '.join(cols)}, updated_at = NOW() WHERE id = %s"
        cursor.execute(query, tuple(vals))
        conn.commit()
        return {"message": "Blog updated"}
    finally:
        release_conn(conn)

@app.delete("/api/admin/blogs/{blog_id}")
def admin_delete_blog(blog_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blogs WHERE id = %s", (blog_id,))
        conn.commit()
        return {"message": "Blog deleted"}
    finally:
        release_conn(conn)

# --- SITE SETTINGS ---

@app.get("/api/public/settings")
def get_public_settings():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM site_settings WHERE key = 'global_discount_percent'")
        row = cursor.fetchone()
        return {row[0]: row[1]} if row else {"global_discount_percent": "0"}
    finally:
        release_conn(conn)

@app.get("/api/admin/settings")
def get_admin_settings(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM site_settings")
        rows = cursor.fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        release_conn(conn)

@app.patch("/api/admin/settings")
def update_admin_settings(payload: dict = Body(...), x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        for k, v in payload.items():
            cursor.execute(
                "INSERT INTO site_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (k, str(v))
            )
        conn.commit()
        return {"message": "Settings updated"}
    finally:
        release_conn(conn)


# --- ADMIN HOST & EVENT MARKETPLACE MANAGEMENT ---

@app.get("/api/admin/hosts")
def get_admin_hosts(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.id, u.full_name, u.email, h.nid_number, h.category, h.operating_area, h.bio, h.verification_status, h.revenue_share_pct, h.created_at, h.is_founding 
            FROM hosts h 
            JOIN users u ON h.user_id = u.id
            ORDER BY h.created_at DESC
        """)
        rows = cursor.fetchall()
        hosts = []
        for r in rows:
            hosts.append({
                "id": r[0],
                "name": r[1],
                "email": r[2],
                "nid_number": r[3],
                "category": r[4],
                "operating_area": r[5],
                "bio": r[6],
                "verification_status": r[7],
                "revenue_share_pct": float(r[8] or 0.5),
                "created_at": str(r[9]),
                "is_founding": bool(r[10])
            })
        cursor.close()
    finally:
        release_conn(conn)
    return hosts


@app.patch("/api/admin/hosts/{host_id}")
def update_admin_host(host_id: int, payload: dict = Body(...), x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        cols = []
        vals = []
        if "verification_status" in payload:
            cols.append("verification_status = %s")
            vals.append(payload["verification_status"])
            
            if payload["verification_status"] == 'VERIFIED':
                cols.append("verified_at = NOW()")
                cursor.execute("UPDATE users SET role = 'host' WHERE id = (SELECT user_id FROM hosts WHERE id = %s)", (host_id,))
            elif payload["verification_status"] == 'SUSPENDED':
                cursor.execute("UPDATE users SET role = 'user' WHERE id = (SELECT user_id FROM hosts WHERE id = %s)", (host_id,))
                
        if "revenue_share_pct" in payload:
            cols.append("revenue_share_pct = %s")
            vals.append(payload["revenue_share_pct"])
            
        if "is_founding" in payload:
            cols.append("is_founding = %s")
            vals.append(payload["is_founding"])
            
        if not cols:
            cursor.close()
            return {"message": "No changes"}
            
        vals.append(host_id)
        query = f"UPDATE hosts SET {', '.join(cols)} WHERE id = %s"
        cursor.execute(query, tuple(vals))
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"status": "success", "message": "Host verification updated successfully"}


@app.get("/api/admin/events")
def get_admin_events(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.id, e.title, e.category, NULL as package_tier, e.price_per_person, e.capacity, e.booked_count, e.location_name, e.location_area, e.event_date, e.status, u.full_name as host_name, e.host_id, e.booking_model
            FROM events e
            LEFT JOIN hosts h ON e.host_id = h.id
            LEFT JOIN users u ON h.user_id = u.id
            ORDER BY e.event_date DESC
        """)
        rows = cursor.fetchall()
        events = []
        for r in rows:
            events.append({
                "id": r[0],
                "title": r[1],
                "category": r[2],
                "package_tier": r[3],
                "price": float(r[4]),
                "capacity": r[5],
                "booked_count": r[6],
                "location_name": r[7],
                "location_area": r[8],
                "event_date": str(r[9]) if r[9] else "",
                "status": r[10],
                "host_name": r[11] or "DekhaHok Team",
                "host_id": r[12],
                "booking_model": r[13] or "ticketed"
            })
        cursor.close()
    finally:
        release_conn(conn)
    return events


@app.patch("/api/admin/events/{event_id}")
def update_admin_event(event_id: int, payload: dict = Body(...), x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cols = []
        vals = []
        if "status" in payload:
            cols.append("status = %s")
            vals.append(payload["status"])
        if "title" in payload:
            cols.append("title = %s")
            vals.append(payload["title"])
        if "price_per_person" in payload:
            cols.append("price_per_person = %s")
            vals.append(payload["price_per_person"])
        if "capacity" in payload:
            cols.append("capacity = %s")
            vals.append(payload["capacity"])
            
        if not cols:
            cursor.close()
            return {"message": "No changes"}
            
        vals.append(event_id)
        query = f"UPDATE events SET {', '.join(cols)} WHERE id = %s"
        cursor.execute(query, tuple(vals))
        
        # Insert Notification if event was published
        if "status" in payload and payload["status"] == "published":
            cursor.execute("SELECT host_id, title FROM events WHERE id = %s", (event_id,))
            event_row = cursor.fetchone()
            if event_row:
                h_id, ev_title = event_row
                cursor.execute("SELECT user_id FROM hosts WHERE id = %s", (h_id,))
                h_user_row = cursor.fetchone()
                if h_user_row:
                    h_user_id = h_user_row[0]
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, message, action_url)
                        VALUES (%s, 'approval', 'Experience Published!', %s, %s)
                    """, (h_user_id, f"Your experience '{ev_title}' has been approved and is now live on the platform.", f"/booking/{event_id}"))
        
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"status": "success", "message": "Event status updated successfully"}


@app.delete("/api/admin/events/{event_id}")
def delete_admin_event(event_id: int, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Check if event is published
        cursor.execute("SELECT status FROM events WHERE id = %s", (event_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")
        if row[0] == "published":
            raise HTTPException(status_code=400, detail="Cannot delete a published event. Please unpublish it first.")
            
        cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)
    return {"status": "success", "message": "Event deleted successfully"}


@app.post("/api/admin/bookings/{booking_id}/transfer")
def transfer_attendee_event(booking_id: int, payload: dict = Body(...), x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    target_event_id = payload.get("target_event_id")
    if not target_event_id:
        raise HTTPException(400, "target_event_id is required")
        
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, event_id, booking_status, group_size, payment_status FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
        b_row = cursor.fetchone()
        if not b_row:
            raise HTTPException(404, "Booking not found")
        b_id, current_ev_id, b_status, g_size, p_status = b_row
        
        if current_ev_id == target_event_id:
            raise HTTPException(400, "Booking is already in the target event")
            
        cursor.execute("SELECT id, capacity, booked_count, status, price_per_person FROM events WHERE id = %s FOR UPDATE", (target_event_id,))
        t_row = cursor.fetchone()
        if not t_row:
            raise HTTPException(404, "Target event not found")
        t_id, t_cap, t_booked, t_status, t_price = t_row
        
        if b_status == 'confirmed':
            if (t_cap - t_booked) < g_size:
                raise HTTPException(400, "Not enough capacity in the target event to transfer this booking.")
                
        if current_ev_id and b_status == 'confirmed':
            cursor.execute("UPDATE events SET booked_count = GREATEST(0, booked_count - %s) WHERE id = %s", (g_size, current_ev_id))
            
        if b_status == 'confirmed':
            cursor.execute("UPDATE events SET booked_count = booked_count + %s WHERE id = %s", (g_size, target_event_id))
            
        cursor.execute("SELECT host_id FROM events WHERE id = %s", (target_event_id,))
        t_host_id = cursor.fetchone()[0]
        
        new_fee = float(t_price) * g_size
        
        cursor.execute("""
            UPDATE bookings 
            SET event_id = %s, host_id = %s, fee_amount = %s
            WHERE id = %s
        """, (target_event_id, t_host_id, new_fee, booking_id))
        
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Transfer transaction failed: {str(e)}")
    finally:
        release_conn(conn)
    return {"status": "success", "message": "Booking transferred successfully"}

# ---------------------------------------------------------------------------
# Phase 4: Session & Hire API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/events/{event_id}/slots")
def get_event_slots(event_id: int):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, slot_date, slot_time, duration_mins, is_booked FROM host_slots WHERE event_id = %s ORDER BY slot_date ASC, slot_time ASC", (event_id,))
        slots = []
        for r in cursor.fetchall():
            dt = datetime.combine(r[1], r[2]) if r[1] and r[2] else None
            slots.append({"id": r[0], "slot_time": dt.isoformat() + "+06:00" if dt else "", "duration_mins": r[3], "is_booked": r[4]})
        return {"slots": slots}
    finally:
        release_conn(conn)

@app.post("/api/sessions/book")
def book_session(payload: SessionBookCreate, dh_session: Optional[str] = Cookie(None)):
    user = get_current_user(dh_session)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Verify slot is not booked
        cursor.execute("SELECT is_booked, event_id FROM host_slots WHERE id = %s", (payload.slot_id,))
        slot_info = cursor.fetchone()
        if not slot_info:
            raise HTTPException(404, "Slot not found")
        if slot_info[0]:
            raise HTTPException(400, "Slot is already booked")
        
        if slot_info[1] != payload.event_id:
            raise HTTPException(400, "Slot does not belong to this event")

        # Fetch event
        cursor.execute("SELECT host_id, price_per_person FROM events WHERE id = %s", (payload.event_id,))
        ev_info = cursor.fetchone()
        if not ev_info:
            raise HTTPException(404, "Event not found")
        
        host_id, fee = ev_info
        
        # Mark slot booked
        cursor.execute("UPDATE host_slots SET is_booked = TRUE WHERE id = %s", (payload.slot_id,))
        
        # Create booking entry
        import secrets
        tracking_id = "SB-" + secrets.token_hex(4).upper()
        
        user_id = user["user_id"] if user else None
        
        cursor.execute("""
            INSERT INTO bookings (tracking_id, user_id, event_id, name, phone, email, booking_status, payment_status, fee_amount, booking_model, slot_id, group_size)
            VALUES (%s, %s, %s, %s, %s, %s, 'confirmed', 'paid', %s, 'session', %s, 1)
            RETURNING id
        """, (tracking_id, user_id, payload.event_id, payload.name, payload.phone, payload.email, fee, payload.slot_id))
        
        booking_id = cursor.fetchone()[0]
        conn.commit()
        
        return {"status": "success", "tracking_id": tracking_id, "message": "Session booked successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Failed to book session: {str(e)}")
    finally:
        release_conn(conn)

@app.post("/api/hire")
def submit_hire_request(payload: HireRequestCreate, dh_session: Optional[str] = Cookie(None)):
    user = get_current_user(dh_session)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Fetch host
        cursor.execute("SELECT id FROM hosts WHERE id = %s", (payload.host_id,))
        if not cursor.fetchone():
            raise HTTPException(404, "Host not found")
            
        import secrets
        tracking_id = "HR-" + secrets.token_hex(4).upper()
        
        cursor.execute("""
            INSERT INTO hire_requests (host_id, event_id, client_name, client_email, client_phone, occasion_type, event_date, event_location, guest_count, message, budget_range, tracking_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (payload.host_id, payload.event_id, payload.client_name, payload.client_email, payload.client_phone, payload.occasion_type, payload.event_date, payload.event_location, payload.guest_count, payload.message, payload.budget_range, tracking_id))
        
        hr_id = cursor.fetchone()[0]
        
        # Create a booking entry to unify tracking
        user_id = user["user_id"] if user else None
        cursor.execute("""
            INSERT INTO bookings (tracking_id, user_id, event_id, name, phone, email, booking_status, payment_status, fee_amount, booking_model, hire_request_id, group_size, preferred_date, venue_type)
            VALUES (%s, %s, %s, %s, %s, %s, 'processing', 'unpaid', 0, 'hire', %s, %s, %s, 'tbd')
        """, (tracking_id, user_id, payload.event_id, payload.client_name, payload.client_phone, payload.client_email, hr_id, payload.guest_count or 1, payload.event_date or '1970-01-01'))

        conn.commit()
        
        return {"status": "success", "tracking_id": tracking_id, "message": "Hire request submitted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Failed to submit hire request: {str(e)}")
    finally:
        release_conn(conn)

class SlotCreate(BaseModel):
    event_id: int
    date: str
    times: str

@app.post("/api/host/slots/add")
def host_add_slots(payload: SlotCreate, dh_session: Optional[str] = Cookie(None)):
    user = get_current_user(dh_session)
    if not user or user["role"] not in ("host", "admin"):
        raise HTTPException(403, "Unauthorized")
        
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Verify host owns event
        cursor.execute("SELECT e.id, 60 as session_duration_mins, h.id FROM events e JOIN hosts h ON e.host_id = h.id WHERE e.id = %s AND h.user_id = %s", (payload.event_id, user["user_id"]))
        ev_info = cursor.fetchone()
        if not ev_info:
            raise HTTPException(403, "Not your event")
            
        duration = ev_info[1] or 60
            
        from datetime import datetime
        # parse times
        time_list = [t.strip() for t in payload.times.split(",") if t.strip()]
        for t in time_list:
            try:
                dt_str = f"{payload.date} {t}"
                dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
                host_id = ev_info[2]
                cursor.execute("INSERT INTO host_slots (host_id, event_id, slot_date, slot_time, duration_mins, is_booked) VALUES (%s, %s, %s, %s, %s, FALSE)", (host_id, payload.event_id, dt.date(), dt.time(), duration))
            except Exception as ex:
                pass
                
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        release_conn(conn)

class HireActionPayload(BaseModel):
    fee_amount: Optional[float] = None

@app.post("/api/hire/{hr_id}/{action}")
def handle_hire_request(hr_id: int, action: str, payload: Optional[HireActionPayload] = None, dh_session: Optional[str] = Cookie(None)):
    user = get_current_user(dh_session)
    if not user or user["role"] not in ("host", "admin"):
        raise HTTPException(403, "Unauthorized")
        
    if action not in ("accept", "decline"):
        raise HTTPException(400, "Invalid action")
        
    status_to_set = "accepted" if action == "accept" else "rejected"
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Verify host owns request
        cursor.execute("SELECT h.id FROM hire_requests h JOIN hosts ho ON h.host_id = ho.id WHERE h.id = %s AND ho.user_id = %s", (hr_id, user["user_id"]))
        if not cursor.fetchone():
            raise HTTPException(403, "Not your request")
            
        cursor.execute("UPDATE hire_requests SET status = %s WHERE id = %s", (status_to_set, hr_id))
        
        # Also update the bookings table
        booking_status = "confirmed" if action == "accept" else "rejected"
        fee_amount = payload.fee_amount if payload and payload.fee_amount else 0
        
        cursor.execute("UPDATE bookings SET booking_status = %s, fee_amount = %s WHERE hire_request_id = %s", (booking_status, fee_amount, hr_id))
        
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        release_conn(conn)

@app.post("/api/hire/{hr_id}/payout")
def request_hire_payout(hr_id: int, dh_session: Optional[str] = Cookie(None)):
    user = get_current_user(dh_session)
    if not user or user["role"] not in ("host", "admin"):
        raise HTTPException(403, "Unauthorized")
        
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Verify host owns request and it's paid
        cursor.execute("""
            SELECT b.id FROM bookings b 
            JOIN hire_requests h ON b.hire_request_id = h.id
            JOIN hosts ho ON h.host_id = ho.id 
            WHERE h.id = %s AND ho.user_id = %s AND b.payment_status = 'paid'
        """, (hr_id, user["user_id"]))
        
        if not cursor.fetchone():
            raise HTTPException(400, "Invalid request or not paid yet")
            
        cursor.execute("UPDATE bookings SET payment_status = 'payout_requested' WHERE hire_request_id = %s", (hr_id,))
        conn.commit()
        
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(500, str(e))
    finally:
        release_conn(conn)
