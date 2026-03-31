import os
import secrets
import string
from typing import Optional

from datetime import datetime, timedelta, time
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from database import get_conn, release_conn, init_db
from models import (
    BookingCreate, BookingResponse, TrackingResponse,
    AdminBookingUpdate, GroupCreate, GroupAssign, GroupUpdate,
    LocationCreate, LocationResponse,
    MeetingPointCreate, MeetingPointResponse,
    RatingCreate, MessageCreate, PartnershipCreate, PartnershipUpdate
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


@app.get("/", include_in_schema=False)
def serve_frontend():
    return FileResponse("static/DekhaHok.html")


@app.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse("admin/index.html")


@app.on_event("startup")
def on_startup():
    init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ADMIN_KEY = os.getenv("ADMIN_SECRET_KEY", "")
FEE_MAP   = {2: 499.00, 5: 249.00}


# ---------------------------------------------------------------------------
# Admin security check: Simple secret key based authentication
# for all internal admin endpoints.
# ---------------------------------------------------------------------------
def require_admin(x_admin_key: str):
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
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
                     preferred_meeting_point, payment_method, payment_sender_digits, fee_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                ),
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
                b.id, g.id, b.rejection_reason
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
        if row and row[18]: # group_id exists
            booking_id = row[17]
            group_id = row[18]
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
            meet_date  = None
            meet_time  = None

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
        rejection_reason=row[19],
        assigned_group_id=row[18]
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
                COUNT(*)                                                                     AS total,
                SUM(CASE WHEN booking_status = 'processing' THEN 1 ELSE 0 END)              AS processing,
                SUM(CASE WHEN booking_status = 'confirmed'  THEN 1 ELSE 0 END)              AS confirmed,
                SUM(CASE WHEN booking_status = 'completed'  THEN 1 ELSE 0 END)              AS completed,
                SUM(CASE WHEN payment_status = 'paid'       THEN 1 ELSE 0 END)              AS paid,
                SUM(CASE WHEN payment_status = 'unpaid'     THEN 1 ELSE 0 END)              AS unpaid,
                SUM(CASE WHEN payment_status = 'paid' THEN fee_amount ELSE 0 END)           AS revenue
            FROM bookings
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
                   assigned_group_id, admin_notes, created_at
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
            "created_at":        str(r[22]),
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
            # Only enforce validation if it wasn't already 'completed'
            if row and row[1] != 'completed':
                if not row[0] or len(row[0].strip()) < 11:
                    raise HTTPException(status_code=400, detail="Cannot complete booking: Missing or invalid mobile number.")

        cursor.execute(f"UPDATE bookings SET {set_clause} WHERE id = %s", values)
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Booking not found.")
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
        cursor.execute("SELECT id FROM meetup_groups WHERE id = %s", (group_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Group not found.")

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
                "point_type": pr[6]
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
        cursor.execute("SELECT id, location_id, name, is_active, latitude, longitude, point_type FROM meeting_points WHERE is_active = TRUE")
        rows = cursor.fetchall()
        return [MeetingPointResponse(id=r[0], location_id=r[1], name=r[2], is_active=r[3], latitude=float(r[4]) if r[4] is not None else None, longitude=float(r[5]) if r[5] is not None else None, point_type=r[6]) for r in rows]
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