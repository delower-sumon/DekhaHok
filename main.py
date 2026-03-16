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
    LocationCreate, LocationResponse
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
                     conversation_style, preferred_people, current_location, preferred_location, fee_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                b.tracking_id, b.name, b.group_size, b.preferred_date,
                b.preferred_time, b.venue_type, b.booking_status, b.payment_status, b.fee_amount,
                g.venue_name, g.meet_date, g.meet_time, b.current_location, b.preferred_location
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
    )


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


# ===========================================================================
# ADMIN
# ===========================================================================

@app.get("/api/admin/dashboard")
def admin_dashboard(x_admin_key: str = Header(...)):
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
                   current_location, preferred_location,
                   fee_amount, payment_status, booking_status,
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
            "current_location":  r[12],
            "preferred_location": r[13],
            "fee_amount":        float(r[14]),
            "payment_status":    r[15],
            "booking_status":    r[16],
            "assigned_group_id": r[17],
            "admin_notes":       r[18],
            "created_at":        str(r[19]),
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

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    values = list(updates.values()) + [booking_id]

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE bookings SET {set_clause} WHERE id = %s", values)
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Booking not found.")
        cursor.close()
    finally:
        release_conn(conn)

    return {"message": "Booking updated."}


@app.get("/api/admin/groups")
def admin_list_groups(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT g.id, g.group_code, g.venue_name, g.meet_date, g.meet_time,
                   g.group_size, g.status, COUNT(gm.id) AS member_count
            FROM meetup_groups g
            LEFT JOIN group_members gm ON gm.group_id = g.id
            GROUP BY g.id
            ORDER BY g.meet_date DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
    finally:
        release_conn(conn)

    return [
        {
            "id":           r[0],
            "group_code":   r[1],
            "venue_name":   r[2],
            "meet_date":    str(r[3]),
            "meet_time":    format_time_12h(r[4]),
            "group_size":   r[5],
            "status":       r[6],
            "member_count": r[7],
        }
        for r in rows
    ]


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
        cursor.execute("SELECT id, name, is_active FROM locations ORDER BY created_at DESC")
        rows = cursor.fetchall()
        cursor.close()
    finally:
        release_conn(conn)
    return [{"id": r[0], "name": r[1], "is_active": r[2]} for r in rows]


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