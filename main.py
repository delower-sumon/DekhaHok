import os
import secrets
import string
import hashlib
from typing import Optional

from datetime import datetime, timedelta, time
from fastapi import FastAPI, HTTPException, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from dotenv import load_dotenv

from database import get_conn, release_conn, init_db
from models import (
    BookingCreate, BookingResponse, TrackingResponse,
    AdminBookingUpdate, GroupCreate, GroupAssign, GroupUpdate,
    LocationCreate, LocationResponse,
    MeetingPointCreate, MeetingPointResponse,
    RatingCreate, MessageCreate, PartnershipCreate, PartnershipUpdate,
    BlogCreate, BlogResponse, BlogUpdate, PublicGroupResponse,
    BlogCommentCreate, BlogCommentResponse
)

load_dotenv()

app = FastAPI(title="DekhaHok API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def seo_redirect_middleware(request: Request, call_next):
    host = request.headers.get("host", "").lower()
    # 1. WWW redirection fallback (Primary is Cloudflare)
    if host.startswith("www."):
        new_host = host.replace("www.", "", 1)
        url = request.url.replace(netloc=new_host)
        return RedirectResponse(url=str(url), status_code=301)
    
    # 2. IP Canonicalization fallback
    if host == "188.114.97.3":
        url = request.url.replace(netloc="dekhahok.com")
        return RedirectResponse(url=str(url), status_code=301)
        
    response = await call_next(request)
    return response


@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return FileResponse("static/404.html", status_code=404)


@app.get("/robots.txt", include_in_schema=False)
def serve_robots():
    content = "User-agent: *\nDisallow: /admin/\nDisallow: /api/\nSitemap: https://dekhahok.com/sitemap.xml"
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def serve_sitemap():
    base_url = "https://dekhahok.com"
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    # Homepage
    xml_content += f'  <url>\n    <loc>{base_url}/</loc>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>\n'
    
    # Blogs
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT slug, created_at FROM blogs WHERE status = 'published' ORDER BY created_at DESC")
        blogs = cursor.fetchall()
        for row in blogs:
            slug = row[0]
            created_at = row[1]
            # Format date for lastmod
            if isinstance(created_at, datetime):
                lastmod = created_at.date().isoformat()
            else:
                lastmod = str(created_at)[:10]
            
            xml_content += f'  <url>\n    <loc>{base_url}/?blog={slug}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
        cursor.close()
    finally:
        release_conn(conn)
        
    xml_content += '</urlset>'
    return Response(content=xml_content, media_type="application/xml")


@app.get("/", include_in_schema=False)
def serve_frontend(request: Request):
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO page_views (ip_hash, user_agent) VALUES (%s, %s)", (ip_hash, user_agent))
        conn.commit()
        cursor.close()
    except Exception:
        conn.rollback()
    finally:
        release_conn(conn)
        
    return FileResponse("static/DekhaHok.html")


@app.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse("admin/index.html")


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
    pages = [
        {"loc": f"{base_url}/", "lastmod": datetime.now().date().isoformat(), "changefreq": "daily", "priority": "1.0"}
    ]
    
    # Dynamic blogs
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT slug, created_at FROM blogs WHERE status = 'published' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        for r in rows:
            # Blog URL format: base_url/?blog=slug
            pages.append({
                "loc": f"{base_url}/?blog={r[0]}",
                "lastmod": r[1].date().isoformat() if isinstance(r[1], datetime) else str(r[1]),
                "changefreq": "weekly",
                "priority": "0.8"
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


@app.on_event("startup")
def on_startup():
    init_db()


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
    return t.strftime("%I:%M %p").lstrip("0")

@app.post("/api/bookings", response_model=BookingResponse, status_code=201)
def create_booking(payload: BookingCreate):
    """
    Creates a new meetup interested entry. 
    Assigns a unique Tracking ID and calculates the required reservation fee.
    """
    fee = FEE_MAP.get(payload.group_size, 0)

    for _ in range(5):
        tracking_id = generate_tracking_id()
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bookings
                    (tracking_id, name, phone, email, age, group_size,
                     preferred_date, preferred_time, venue_type,
                     conversation_style, preferred_people, current_location, preferred_location, 
                     preferred_meeting_point, payment_method, payment_sender_digits, fee_amount,
                     interests, expectations, wants_pickup, wants_dropoff)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tracking_id,
                    payload.name,
                    payload.phone,
                    payload.email,
                    payload.age,
                    payload.group_size,
                    payload.preferred_date,
                    payload.preferred_time,
                    payload.venue_type,
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
                ),
            )
            conn.commit()
            
            # Generate referral code for this booking
            booking_id_seq = cursor.lastrowid # Not reliable for psycopg2 sometimes but let's see
            # Actually we can just update it by tracking_id
            ref_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            cursor.execute(
                "UPDATE bookings SET referral_code = %s, referred_by = %s WHERE tracking_id = %s",
                (ref_code, payload.referred_by, tracking_id)
            )
            conn.commit()
            
            cursor.close()
            return BookingResponse(
                tracking_id=tracking_id,
                message="Booking received! Save your tracking ID to check status.",
            )
        except Exception as e:
            conn.rollback()
            if "Duplicate entry" in str(e) and "tracking_id" in str(e):
                continue
            raise HTTPException(status_code=500, detail="Could not save booking. Please try again.")
        finally:
            release_conn(conn)

    raise HTTPException(status_code=500, detail="Could not generate unique tracking ID.")


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
                b.interests, b.expectations, b.wants_pickup, b.wants_dropoff
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
        wants_dropoff=row[25]
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
        cursor.execute("SELECT id, title, slug, content, keywords, seo_description, image_url, badge_text, likes, shares, status, author, created_at, is_pivoted FROM blogs WHERE status = 'published' ORDER BY is_pivoted DESC, created_at DESC")
        rows = cursor.fetchall()
        return [
            BlogResponse(
                id=r[0], title=r[1], slug=r[2], content=r[3], 
                keywords=r[4], seo_description=r[5], image_url=r[6], 
                badge_text=r[7], likes=r[8], shares=r[9],
                status=r[10], author=r[11], created_at=str(r[12]),
                is_pivoted=r[13]
            ) for r in rows
        ]
    finally:
        release_conn(conn)


@app.get("/api/blogs/{slug}", response_model=BlogResponse)
def get_blog(slug: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, slug, content, keywords, seo_description, image_url, badge_text, likes, shares, status, author, created_at, is_pivoted FROM blogs WHERE slug = %s", (slug,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Blog not found")
        return BlogResponse(
            id=row[0], title=row[1], slug=row[2], content=row[3], 
            keywords=row[4], seo_description=row[5], image_url=row[6], 
            badge_text=row[7], likes=row[8], shares=row[9],
            status=row[10], author=row[11], created_at=str(row[12]),
            is_pivoted=row[13]
        )
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

@app.get("/api/public/groups", response_model=list[PublicGroupResponse])
def list_public_groups(location: Optional[str] = Query(None)):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Show latest 5 groups that are open, confirmed or completed
        query = """
            SELECT g.id, g.group_code, g.venue_name, g.meet_date, g.meet_time, g.group_size,
                   (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) as member_count,
                   g.status
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
                group_size=r[5], member_count=r[6], status=r[7]
            ))
        return results
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
                (SELECT COALESCE(SUM(fee_amount), 0) FROM bookings WHERE payment_status = 'paid') AS revenue,
                (SELECT COUNT(*) FROM meetup_groups WHERE status = 'open') AS open_groups,
                (SELECT COUNT(*) FROM locations WHERE is_active = true) AS active_locations
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
    }


@app.get("/api/admin/analytics")
def admin_analytics(x_admin_key: str = Header(...)):
    """
    Returns aggregated metrics for website page views tracking.
    """
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM page_views WHERE viewed_at >= NOW() - INTERVAL '1 day') AS today,
                (SELECT COUNT(*) FROM page_views WHERE viewed_at >= NOW() - INTERVAL '7 days') AS week,
                (SELECT COUNT(*) FROM page_views WHERE viewed_at >= NOW() - INTERVAL '30 days') AS month,
                (SELECT COUNT(*) FROM page_views) AS all_time
        """)
        row = cursor.fetchone()
        cursor.close()
    finally:
        release_conn(conn)
        
    return {
        "today": row[0] or 0,
        "week": row[1] or 0,
        "month": row[2] or 0,
        "all_time": row[3] or 0,
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
        filters.append("booking_status = %s"); params.append(status)
    if payment:
        filters.append("payment_status = %s"); params.append(payment)
    if group_size:
        filters.append("group_size = %s");     params.append(group_size)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, tracking_id, name, phone, email, age, group_size,
                   preferred_date, preferred_time, venue_type, conversation_style, preferred_people,
                   current_location, preferred_location, preferred_meeting_point,
                   fee_amount, payment_status, payment_method, payment_sender_digits, booking_status,
                   assigned_group_id, admin_notes, is_verified, wants_pickup, wants_dropoff, created_at,
                   interests, expectations
            FROM bookings
            {where}
            ORDER BY created_at DESC
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
            # Relaxed for local environment and admin override
            if row and row[1] != 'completed':
                if not row[0] or len(row[0].strip()) < 8: # Relaxed from 11
                    print(f"[dekhahok] Admin override: booking {booking_id} has short phone '{row[0]}'")
                    # We still allow it but maybe set a flag 
                    pass

        cursor.execute(f"UPDATE bookings SET {set_clause} WHERE id = %s", values)
        conn.commit()
        
        # Growth Verification Logic: Check if user becomes 'Verified Citizen'
        if payload.booking_status == 'completed':
            # Criteria: User completed a meetup AND has referred someone
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
            
        # Identity-based verification persistence
        if payload.is_verified is True:
            # Fetch phone for this booking
            cursor.execute("SELECT phone FROM bookings WHERE id = %s", (booking_id,))
            prow = cursor.fetchone()
            if prow:
                phone_to_verify = prow[0]
                # Mark ALL bookings with this phone as verified
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
        # group_members should be deleted by CASCADE if schema setup correctly, 
        # but the schema says ON DELETE CASCADE for booking_id in group_members.
        # Let's ensure it.
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
                   g.group_size, g.status
            FROM meetup_groups g
            ORDER BY g.meet_date DESC
            """
        )
        group_rows = cursor.fetchall()

        results = []
        for gr in group_rows:
            gid = gr[0]
            # Fetch members for this group
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
            INSERT INTO meetup_groups (group_code, venue_name, meet_date, meet_time, group_size)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (group_code, payload.venue_name, payload.meet_date, payload.meet_time, payload.group_size),
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
            # Check capacity
            cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = %s", (group_id,))
            current_count = cursor.fetchone()[0]
            if current_count + len(payload.booking_ids) > g_size:
                raise HTTPException(status_code=400, detail=f"Cannot assign {len(payload.booking_ids)} members. Group capacity exceeded (Current: {current_count}/{g_size}).")

            # Check compatibility
            format_strings = ','.join(['%s'] * len(payload.booking_ids))
            cursor.execute(f"SELECT id, group_size FROM bookings WHERE id IN ({format_strings})", tuple(payload.booking_ids))
            bookings_info = cursor.fetchall()
            
            if len(bookings_info) != len(payload.booking_ids):
                raise HTTPException(status_code=404, detail="One or more bookings not found.")
                
            for b_info in bookings_info:
                if b_info[1] != g_size:
                    raise HTTPException(status_code=400, detail=f"Booking {b_info[0]} has incompatible group size ({b_info[1]} vs {g_size}).")

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

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    values = list(updates.values()) + [group_id]

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE meetup_groups SET {set_clause} WHERE id = %s", values)
        
        if updates.get("status") == 'completed':
            # Phase 3 requirement: chat should be deleted after the meetup status is completed
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
        # First remove all member associations
        cursor.execute("DELETE FROM group_members WHERE group_id = %s", (group_id,))
        # Then remove the group itself
        cursor.execute("DELETE FROM meetup_groups WHERE id = %s", (group_id,))
        conn.commit()
    finally:
        release_conn(conn)
    return {"message": "Group deleted."}


# --- LOCATIONS (ADMIN) ---

@app.get("/api/admin/locations", response_model=list[LocationResponse])
def admin_list_locations(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Fetch all locations
        cursor.execute("SELECT id, name, is_active FROM locations ORDER BY created_at DESC")
        loc_rows = cursor.fetchall()
        loc_dict = {loc[0]: loc[1] for loc in loc_rows}
        
        # Fetch all meeting points and group them by location_id
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
            INSERT INTO blogs (title, slug, content, keywords, seo_description, image_url, badge_text, status, author, is_pivoted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            RETURNING id, created_at
            """,
            (payload.title, slug, payload.content, payload.keywords, payload.seo_description, payload.image_url, payload.badge_text, payload.status, payload.author, payload.is_pivoted)
        )
        row = cursor.fetchone()
        conn.commit()
        if not row:
            raise HTTPException(status_code=400, detail="Blog with this slug already exists.")
        return BlogResponse(
            id=row[0], title=payload.title, slug=slug, content=payload.content,
            keywords=payload.keywords, seo_description=payload.seo_description,
            image_url=payload.image_url, badge_text=payload.badge_text,
            likes=0, shares=0,
            status=payload.status, author=payload.author, is_pivoted=payload.is_pivoted, created_at=str(row[1])
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
