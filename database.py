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
# Create pool with TCP Keepalives to prevent Neon/Supabase from aggressively dropping idle connections
_pool = pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=os.getenv("DATABASE_URL"),
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5
)


def get_conn():
    """
    Borrow a connection from the pool and verify it is still alive.
    If the connection is dead, trash it and get a new one.
    """
    conn = _pool.getconn()
    try:
        # Pre-ping the connection to ensure it hasn't been silently closed by the server
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    except psycopg2.OperationalError:
        # If the connection is dead, close it properly and throw it away
        _pool.putconn(conn, close=True)
        # Fetch a fresh connection
        conn = _pool.getconn()
    return conn


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
    vibe              VARCHAR(50),
    discount_amount   NUMERIC(8,2) DEFAULT 0.00,
    coupon_code       VARCHAR(20),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupons (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    discount_type VARCHAR(10) NOT NULL, -- 'percent' or 'fixed'
    value NUMERIC(8,2) NOT NULL,
    usage_limit INT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
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



CREATE TABLE IF NOT EXISTS blogs (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    keywords TEXT,
    seo_description TEXT,
    image_url TEXT,
    status TEXT DEFAULT 'published',
    is_pivoted BOOLEAN DEFAULT FALSE,
    likes INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    author TEXT DEFAULT 'Team DekhaHok',
    author_title TEXT,
    author_image_url TEXT,
    badge_text TEXT,
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
        
        # New tables for marketplace transition
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(200) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                google_id VARCHAR(255) UNIQUE,
                full_name VARCHAR(120) NOT NULL,
                avatar_url TEXT,
                phone VARCHAR(20),
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hosts (
                id SERIAL PRIMARY KEY,
                user_id INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                nid_number VARCHAR(20) NOT NULL,
                profession VARCHAR(100),
                category VARCHAR(50) NOT NULL,
                operating_area VARCHAR(100),
                bio TEXT,
                host_type VARCHAR(50) DEFAULT 'individual',
                social_links JSONB DEFAULT '{}',
                verification_status VARCHAR(20) DEFAULT 'PENDING',
                is_founding BOOLEAN DEFAULT FALSE,
                revenue_share_pct DECIMAL(4,2) DEFAULT 0.50,
                verified_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                host_id INT REFERENCES hosts(id) ON DELETE SET NULL,
                slug VARCHAR(250) UNIQUE NOT NULL,
                title VARCHAR(300) NOT NULL,
                description TEXT,
                category VARCHAR(50) NOT NULL,
                listing_type VARCHAR(50) DEFAULT 'event',
                booking_model VARCHAR(50),
                external_link VARCHAR(255),
                price_per_person NUMERIC(8,2) NOT NULL DEFAULT 0.00,
                capacity INT NOT NULL DEFAULT 10,
                booked_count INT NOT NULL DEFAULT 0,
                location_name VARCHAR(300),
                location_area VARCHAR(100),
                event_date TIMESTAMPTZ,
                image_url TEXT,
                included JSONB DEFAULT '[]',
                status VARCHAR(20) DEFAULT 'draft',
                host_payment_status VARCHAR(20) DEFAULT 'unpaid',
                is_recurring BOOLEAN DEFAULT FALSE,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS host_slots (
                id SERIAL PRIMARY KEY,
                host_id INTEGER REFERENCES hosts(id),
                event_id INTEGER REFERENCES events(id),
                slot_date DATE NOT NULL,
                slot_time TIME NOT NULL,
                is_booked BOOLEAN DEFAULT FALSE,
                booking_id INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (event_id, slot_date, slot_time)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hire_requests (
                id SERIAL PRIMARY KEY,
                host_id INTEGER REFERENCES hosts(id),
                event_id INTEGER REFERENCES events(id),
                client_name VARCHAR(200) NOT NULL,
                client_email VARCHAR(200) NOT NULL,
                client_phone VARCHAR(20),
                occasion_type VARCHAR(200),
                event_date DATE,
                event_location VARCHAR(300),
                guest_count INTEGER,
                message TEXT,
                budget_range VARCHAR(100),
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Migrations for existing DB
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS current_location VARCHAR(200)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS preferred_location VARCHAR(200)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS preferred_meeting_point VARCHAR(200)")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS host_payment_status VARCHAR(20) DEFAULT 'unpaid'")
        cursor.execute("ALTER TABLE meeting_points ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 8)")
        cursor.execute("ALTER TABLE meeting_points ADD COLUMN IF NOT EXISTS longitude DECIMAL(11, 8)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20)")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_sender_digits VARCHAR(10)")
        cursor.execute("ALTER TABLE meetup_groups ALTER COLUMN group_code TYPE VARCHAR(20)")
        cursor.execute("ALTER TABLE meeting_points ADD COLUMN IF NOT EXISTS point_type VARCHAR(20) DEFAULT 'public_place'")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS image_url TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS badge_text VARCHAR(50)")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS shares INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS admin_notes TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS is_pivoted BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS author_title TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS author_image_url TEXT")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS vibe VARCHAR(50)")
        
        # Phase 1 Migrations
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS listing_type VARCHAR(50) DEFAULT 'event'")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS booking_model VARCHAR(50)")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS external_link VARCHAR(255)")
        cursor.execute("ALTER TABLE hosts ADD COLUMN IF NOT EXISTS host_type VARCHAR(50) DEFAULT 'individual'")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS starting_rate INTEGER")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS service_area VARCHAR(200)")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS occasion_types TEXT")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS portfolio_url TEXT")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS availability_note TEXT")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS session_duration_mins INTEGER")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS max_per_session INTEGER DEFAULT 1")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS advance_notice_hours INTEGER DEFAULT 24")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS hide_price BOOLEAN DEFAULT FALSE")
        cursor.execute("UPDATE events SET booking_model = 'community' WHERE booking_model IS NULL")
        
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(8,2) DEFAULT 0.00")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(20)")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS image_alt TEXT")
        cursor.execute("ALTER TABLE meetup_groups ADD COLUMN IF NOT EXISTS image_url TEXT")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS gender VARCHAR(10)")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE hosts ADD COLUMN IF NOT EXISTS profession VARCHAR(100)")
        
        # Category renaming migration
        cursor.execute("UPDATE events SET category = 'travel' WHERE category = 'nature-escapes'")
        
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS image_url_2 TEXT")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS image_url_3 TEXT")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS image_url_4 TEXT")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS youtube_link VARCHAR(255)")
        cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0")
        

        # Marketplace foreign key fields for bookings
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS event_id INT REFERENCES events(id) ON DELETE SET NULL")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS host_id INT REFERENCES hosts(id) ON DELETE SET NULL")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id) ON DELETE SET NULL")
        
        # Coupons table migration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id SERIAL PRIMARY KEY,
                code VARCHAR(20) NOT NULL UNIQUE,
                discount_type VARCHAR(10) NOT NULL,
                value NUMERIC(8,2) NOT NULL,
                usage_limit INT,
                expires_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Indexes for grouping optimization
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_preferred_date ON bookings(preferred_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_vibe ON bookings(vibe)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_location ON bookings(preferred_location)")
        
        # Site Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS site_settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("INSERT INTO site_settings (key, value) VALUES ('global_discount_percent', '0') ON CONFLICT DO NOTHING")

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
        
        # Notifications table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT,
                is_read BOOLEAN DEFAULT FALSE,
                action_url VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Initial locations
        initial_locations = [
            'শাহবাগ', 'ফার্মগেট', 'গুলশান', 'মিরপুর',
            'উত্তরা', 'বিজয় সরণি', 'আগারগাঁও', 'পুরান ঢাকা'
        ]
        for loc in initial_locations:
            cursor.execute("INSERT INTO locations (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (loc,))
        
        # Nuke legacy seeded blogs for good
        legacy_slugs = [
            "best-places-to-meet-in-dhaka",
            "safe-meeting-spots-dhanmondi", 
            "networking-events-dhaka"
        ]
        cursor.execute("DELETE FROM blogs WHERE slug IN %s", (tuple(legacy_slugs),))
        
        # Seed Robindro Sorobor Blog
        cursor.execute("""
            INSERT INTO blogs (slug, title, seo_description, content, author, image_url, badge_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
        """, (
            "robindro-sorobor-photography-walk",
            "A Morning at Robindro Sorobor: Capturing the Soul of Dhaka",
            "Our recent photography walk at Robindro Sorobor brought together passionate photographers. Here is a recap of our magical morning.",
            "We recently hosted a photography walk at Robindro Sorobor, one of Dhaka's most iconic and vibrant cultural spots. It was an early morning event, and as the sun rose, casting a golden hue over the lake, over 25 community members gathered with their cameras and smartphones, ready to capture the soul of the city.<br><br>The event kicked off with a brief introduction by our host, an experienced local photographer who shared tips on composition, lighting, and storytelling through lenses. From the rustic boats gently bobbing on the water to the energetic joggers and the tranquil nature surrounding the amphitheater, every corner offered a unique frame.<br><br>What made this walk truly special was the sense of community. Beginners learned from professionals, and strangers bonded over a shared passion. We explored the lakeside pathways, clicking candid portraits, stunning landscapes, and the everyday life of Dhaka waking up.<br><br>After two hours of shooting, we sat down at a nearby cafe for some tea and snacks, reviewing our shots and discussing techniques. The energy was palpable, and the feedback was overwhelmingly positive. It wasn't just about taking pictures; it was about seeing our city from a new perspective and connecting with like-minded individuals.<br><br>If you missed this one, don't worry! We have many more such experiences lined up. Check out our <a href='/' class='text-emerald-600 underline'>Photography Walk listing</a> and join us next time. Let's create beautiful memories and stunning portfolios together!",
            "DekhaHok Team",
            "https://dekhahok.com/static/assets/og-default.jpg",
            "Recap"
        ))
        
        # Create default admin user and host
        cursor.execute("""
            INSERT INTO users (email, full_name, role)
            VALUES ('team@dekhahok.com', 'DekhaHok Team', 'admin')
            ON CONFLICT (email) DO NOTHING
        """)
        cursor.execute("SELECT id FROM users WHERE email = 'team@dekhahok.com'")
        team_user_id = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO hosts (user_id, nid_number, category, operating_area, bio, verification_status, revenue_share_pct)
            VALUES (%s, '0000000000', 'Creative', 'Dhaka', 'Official DekhaHok Host Account', 'VERIFIED', 0.50)
            ON CONFLICT (user_id) DO NOTHING
        """, (team_user_id,))
        cursor.execute("SELECT id FROM hosts WHERE user_id = %s", (team_user_id,))
        team_host_id = cursor.fetchone()[0]
        
        # Migrate legacy bookings with no event_id to default event (runs once)
        cursor.execute("SELECT COUNT(*) FROM site_settings WHERE key = 'legacy_bookings_migrated'")
        already_migrated = cursor.fetchone()[0] > 0
        if not already_migrated:
            cursor.execute("SELECT COUNT(*) FROM bookings WHERE event_id IS NULL")
            unlinked_count = cursor.fetchone()[0]
            if unlinked_count > 0:
                cursor.execute("""
                    INSERT INTO events (host_id, slug, title, description, category, price_per_person, capacity, status)
                    VALUES (%s, 'dekhahok-circle-adda', 'DekhaHok Circle Adda', 'Casual cafe adda for meeting new friends.', 'Lifestyle', 299.00, 10000, 'published')
                    ON CONFLICT (slug) DO NOTHING
                """, (team_host_id,))
                
                cursor.execute("SELECT id FROM events WHERE slug = 'dekhahok-circle-adda'")
                circle_event_id = cursor.fetchone()[0]
                
                cursor.execute("""
                    UPDATE bookings 
                    SET event_id = %s, host_id = %s 
                    WHERE event_id IS NULL
                """, (circle_event_id, team_host_id))
                
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE event_id = %s", (circle_event_id,))
                event_bookings_count = cursor.fetchone()[0]
                cursor.execute("UPDATE events SET booked_count = %s WHERE id = %s", (event_bookings_count, circle_event_id))
            
            cursor.execute("INSERT INTO site_settings (key, value) VALUES ('legacy_bookings_migrated', 'true') ON CONFLICT DO NOTHING")
        
        # Ensure is_founding column exists in hosts table for backward compatibility
        cursor.execute("ALTER TABLE hosts ADD COLUMN IF NOT EXISTS is_founding BOOLEAN DEFAULT FALSE")

        # Marketplace model migrations for bookings & hire requests
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_model VARCHAR(50) DEFAULT 'ticketed'")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS slot_id INTEGER REFERENCES host_slots(id) ON DELETE SET NULL")
        cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS hire_request_id INTEGER REFERENCES hire_requests(id) ON DELETE SET NULL")
        cursor.execute("ALTER TABLE hire_requests ADD COLUMN IF NOT EXISTS tracking_id VARCHAR(50)")
        cursor.execute("ALTER TABLE host_slots ADD COLUMN IF NOT EXISTS duration_mins INTEGER DEFAULT 60")

        # Backfill existing hosts with id <= 100 as Founding 100
        cursor.execute("SELECT COUNT(*) FROM site_settings WHERE key = 'founding_hosts_backfilled'")
        already_backfilled = cursor.fetchone()[0] > 0
        if not already_backfilled:
            cursor.execute("UPDATE hosts SET is_founding = TRUE WHERE id <= 100")
            cursor.execute("INSERT INTO site_settings (key, value) VALUES ('founding_hosts_backfilled', 'true') ON CONFLICT DO NOTHING")
        
        conn.commit()
        cursor.close()
        print("[dekhahok] Database tables ready.")
    except Exception as e:
        conn.rollback()
        print(f"[dekhahok] Database init error: {e}")
        raise
    finally:
        release_conn(conn)