import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Connection pool — Neon pooler endpoint handles PgBouncer on their side,
# so we keep our app-side pool small (2-5 is plenty).
# We use ThreadedConnectionPool for safe access across FastAPI threads.
# ---------------------------------------------------------------------------
_pool = pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=os.getenv("DATABASE_URL"),
)


def get_conn():
    """Borrow a connection from the pool."""
    return _pool.getconn()


def release_conn(conn):
    """Return a connection to the pool."""
    _pool.putconn(conn)


# ---------------------------------------------------------------------------
# Schema bootstrap
# PostgreSQL differences from MySQL:
#   - SERIAL instead of AUTO_INCREMENT
#   - TEXT/VARCHAR instead of ENUM (simpler, no ALTER needed later)
#   - TRUE/FALSE instead of 1/0
#   - %s placeholders work the same way
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meeting_points (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bookings (
    id                SERIAL PRIMARY KEY,
    tracking_id       VARCHAR(12)  NOT NULL UNIQUE,
    name              VARCHAR(120) NOT NULL,
    phone             VARCHAR(20)  NOT NULL,
    email             VARCHAR(120),
    age               SMALLINT,
    group_size        SMALLINT     NOT NULL,
    preferred_date    DATE         NOT NULL,
    preferred_time    TIME         NOT NULL DEFAULT '17:00:00',
    venue_type        VARCHAR(20)  NOT NULL,
    conversation_style TEXT,
    preferred_people  TEXT,
    current_location  VARCHAR(200),
    preferred_location VARCHAR(200),
    preferred_meeting_point VARCHAR(200),
    fee_amount        NUMERIC(8,2) NOT NULL DEFAULT 0.00,
    payment_status    VARCHAR(10)  NOT NULL DEFAULT 'unpaid',
    payment_method    VARCHAR(20),
    payment_sender_digits VARCHAR(10),
    booking_status    VARCHAR(15)  NOT NULL DEFAULT 'processing',
    assigned_group_id INT,
    admin_notes       TEXT,
    wants_pickup      BOOLEAN DEFAULT FALSE,
    wants_dropoff     BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meetup_groups (
    id           SERIAL PRIMARY KEY,
    group_code   VARCHAR(20)  NOT NULL UNIQUE,
    venue_name   VARCHAR(200) NOT NULL,
    meet_date    DATE         NOT NULL,
    meet_time    TIME         NOT NULL,
    group_size   SMALLINT     NOT NULL,
    status       VARCHAR(15)  NOT NULL DEFAULT 'open',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS group_members (
    id         SERIAL PRIMARY KEY,
    group_id   INT NOT NULL,
    booking_id INT NOT NULL,
    UNIQUE (booking_id),
    FOREIGN KEY (group_id)   REFERENCES meetup_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)      ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_chats (
    id           SERIAL PRIMARY KEY,
    group_id     INT NOT NULL REFERENCES meetup_groups(id) ON DELETE CASCADE,
    sender_id    INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    message      TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS partnership_requests (
    id SERIAL PRIMARY KEY,
    restaurant_name VARCHAR(200) NOT NULL,
    contact_number VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS page_views (
    id SERIAL PRIMARY KEY,
    ip_hash VARCHAR(64),
    user_agent TEXT,
    viewed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS blogs (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    content TEXT NOT NULL,
    keywords TEXT,
    seo_description TEXT,
    image_url TEXT,
    badge_text VARCHAR(50),
    likes INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'published',
    author VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS blog_comments (
    id SERIAL PRIMARY KEY,
    blog_id INT NOT NULL REFERENCES blogs(id) ON DELETE CASCADE,
    user_name VARCHAR(100) NOT NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def init_db():
    """
    Initialises the database by creating necessary tables and applying migrations.
    This runs on application startup to ensure the schema is always up-to-date.
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(SCHEMA_SQL)
        
        # Migrations for existing DB
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS current_location VARCHAR(200)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS preferred_location VARCHAR(200)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS preferred_meeting_point VARCHAR(200)")
        cursor.execute("ALTER TABLE meeting_points ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 8)")
        cursor.execute("ALTER TABLE meeting_points ADD COLUMN IF NOT EXISTS longitude DECIMAL(11, 8)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_sender_digits VARCHAR(10)")
        cursor.execute("ALTER TABLE meetup_groups ALTER COLUMN group_code TYPE VARCHAR(20)")
        cursor.execute("ALTER TABLE meeting_points ADD COLUMN IF NOT EXISTS point_type VARCHAR(20) DEFAULT 'public_place'")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS rejection_reason TEXT")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS referral_code VARCHAR(12) UNIQUE")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS referred_by VARCHAR(12)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS wants_pickup BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS wants_dropoff BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS image_url TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS badge_text VARCHAR(50)")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS shares INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS admin_notes TEXT")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS interests TEXT")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS expectations TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS is_pivoted BOOLEAN DEFAULT FALSE")
        
        # User Ratings table creation moved here for robustness
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ratings (
                id           SERIAL PRIMARY KEY,
                rater_id     INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
                ratee_id     INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
                group_id     INT NOT NULL REFERENCES meetup_groups(id) ON DELETE CASCADE,
                score        SMALLINT NOT NULL CHECK (score >= 1 AND score <= 5),
                comment      TEXT,
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (rater_id, ratee_id, group_id)
            )
        """)
        
        # Initial locations
        initial_locations = [
            'শাহবাগ', 'ফার্মগেট', 'গুলশান', 'মিরপুর',
            'উত্তরা', 'বিজয় সরণি', 'আগারগাঁও', 'পুরান ঢাকা'
        ]
        for loc in initial_locations:
            cursor.execute("INSERT INTO locations (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (loc,))
        
        # Seed initial blogs
        initial_blogs = [
            (
                "Best places to meet in Dhaka", 
                "best-places-to-meet-in-dhaka", 
                "Dhaka is a city of life and culture. For those looking to meet new people, locations like Dhanmondi Lake, Gulshan 2, and various rooftop cafes offer the perfect setting...",
                "Dhaka meetup, premium restaurants Dhaka, safe meeting spots",
                "Looking for the best places to meet new people in Dhaka? Check out our top 5 recommendations.",
                "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=500&auto=format&fit=crop&q=60",
                "Dhaka meetup"
            ),
            (
                "Safe meeting spots Dhanmondi", 
                "safe-meeting-spots-dhanmondi", 
                "Dhanmondi is known for its academic and cultural vibe. When meeting someone new, safety is priority. Dhanmondi Lake and Rabindra Sarobar are busy, safe places...",
                "Dhanmondi hangout, safe spots Dhaka, Rabindra Sarobar",
                "Explore the safest spots for networking and dating in Dhanmondi, Dhaka.",
                "https://images.unsplash.com/photo-1582213782179-e0d53f98f2ca?w=500&auto=format&fit=crop&q=60",
                "Dhanmondi hangout"
            ),
            (
                "Networking events Dhaka", 
                "networking-events-dhaka", 
                "Networking in Dhaka has shifted from formal offices to social gatherings. Coffee shops in Gulshan and Banani now host informal meetups for professionals...",
                "Dhaka networking, professional meetups, Gulshan events",
                "How to find the best networking events in Dhaka for professional growth.",
                "https://images.unsplash.com/photo-1515187029135-18ee286d815b?w=500&auto=format&fit=crop&q=60",
                "Dhaka networking"
            )
        ]
        for title, slug, content, keywords, seo_desc, img, badge in initial_blogs:
            cursor.execute("""
                INSERT INTO blogs (title, slug, content, keywords, seo_description, image_url, badge_text) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) 
                ON CONFLICT (slug) DO NOTHING
            """, (title, slug, content, keywords, seo_desc, img, badge))
            
        conn.commit()
        cursor.close()
        print("[dekhahok] Database tables ready.")
    except Exception as e:
        conn.rollback()
        print(f"[dekhahok] Database init error: {e}")
        raise
    finally:
        release_conn(conn)