-- Phase 1 Migration: Support 3 Booking Models
ALTER TABLE hosts
  ADD COLUMN IF NOT EXISTS host_type VARCHAR(20) DEFAULT 'community' CHECK (host_type IN ('community', 'artist', 'session'));

ALTER TABLE events
  ADD COLUMN IF NOT EXISTS listing_type VARCHAR(20) DEFAULT 'event' CHECK (listing_type IN ('event', 'service', 'session')),
  ADD COLUMN IF NOT EXISTS booking_model VARCHAR(20) DEFAULT 'ticketed' CHECK (booking_model IN ('ticketed', 'hire', 'session')),
  ADD COLUMN IF NOT EXISTS starting_rate INTEGER,
  ADD COLUMN IF NOT EXISTS service_area VARCHAR(200),
  ADD COLUMN IF NOT EXISTS occasion_types TEXT,
  ADD COLUMN IF NOT EXISTS portfolio_url TEXT,
  ADD COLUMN IF NOT EXISTS availability_note TEXT,
  ADD COLUMN IF NOT EXISTS session_duration_mins INTEGER,
  ADD COLUMN IF NOT EXISTS max_per_session INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS advance_notice_hours INTEGER DEFAULT 24;

CREATE TABLE IF NOT EXISTS host_slots (
  id          SERIAL PRIMARY KEY,
  host_id     INTEGER REFERENCES hosts(id),
  event_id    INTEGER REFERENCES events(id),
  slot_date   DATE      NOT NULL,
  slot_time   TIME      NOT NULL,
  is_booked   BOOLEAN   DEFAULT FALSE,
  booking_id  INTEGER,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (event_id, slot_date, slot_time)
);

CREATE TABLE IF NOT EXISTS hire_requests (
  id              SERIAL PRIMARY KEY,
  host_id         INTEGER REFERENCES hosts(id),
  event_id        INTEGER REFERENCES events(id),
  client_name     VARCHAR(200) NOT NULL,
  client_email    VARCHAR(200) NOT NULL,
  client_phone    VARCHAR(20),
  occasion_type   VARCHAR(200),
  event_date      DATE,
  event_location  VARCHAR(300),
  guest_count     INTEGER,
  message         TEXT,
  budget_range    VARCHAR(100),
  status          VARCHAR(50) DEFAULT 'pending',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Data backfill logic (Defaulting older records)
UPDATE events
SET listing_type  = COALESCE(listing_type, 'event'),
    booking_model = COALESCE(booking_model, 'ticketed')
WHERE listing_type IS NULL OR booking_model IS NULL;

-- Note: DO NOT drop package_tier yet! We drop it in Phase 6.
