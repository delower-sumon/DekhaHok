-- ============================================================
-- DekhaHok — Local MySQL Setup
-- Run this once: mysql -u root -p < mysql_local_setup.sql
-- ============================================================

-- 1. Create database
CREATE DATABASE IF NOT EXISTS dekhahok
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 2. Create a dedicated user (safer than using root)
CREATE USER IF NOT EXISTS 'dekhahok_user'@'localhost'
    IDENTIFIED BY 'dekhahok_local_pass';

GRANT ALL PRIVILEGES ON dekhahok.* TO 'dekhahok_user'@'localhost';
FLUSH PRIVILEGES;

-- 3. Switch to the database
USE dekhahok;

-- 4. Tables (same as database.py schema — here for reference/manual reset)

CREATE TABLE IF NOT EXISTS bookings (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    tracking_id       VARCHAR(12)  NOT NULL UNIQUE,
    name              VARCHAR(120) NOT NULL,
    phone             VARCHAR(20)  NOT NULL,
    email             VARCHAR(120),
    age               TINYINT,
    group_size        TINYINT      NOT NULL,
    preferred_date    DATE         NOT NULL,
    preferred_time    TIME         NOT NULL DEFAULT "17:00:00",
    venue_type        ENUM('restaurant','public_place') NOT NULL,
    conversation_style TEXT,
    preferred_people   TEXT,
    fee_amount        DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    payment_status    ENUM('unpaid','paid') NOT NULL DEFAULT 'unpaid',
    booking_status    ENUM('processing','confirmed','completed') NOT NULL DEFAULT 'processing',
    assigned_group_id INT,
    admin_notes       TEXT,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meetup_groups (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    group_code   VARCHAR(16) NOT NULL UNIQUE,
    venue_name   VARCHAR(200) NOT NULL,
    meet_date    DATE         NOT NULL,
    meet_time    TIME         NOT NULL,
    group_size   TINYINT      NOT NULL,
    status       ENUM('open','confirmed','completed') NOT NULL DEFAULT 'open',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS group_members (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    group_id   INT NOT NULL,
    booking_id INT NOT NULL,
    UNIQUE KEY uq_booking (booking_id),
    FOREIGN KEY (group_id)   REFERENCES meetup_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)      ON DELETE CASCADE
);

-- ============================================================
-- Optional: insert a test booking to verify everything works
-- ============================================================
-- INSERT INTO bookings
--     (tracking_id, name, phone, email, age, group_size, preferred_date, venue_type, fee_amount)
-- VALUES
--     ('DH-TEST0001', 'Test User', '01711000000', 'test@test.com', 25, 2, CURDATE() + INTERVAL 2 DAY, 'restaurant', 499.00);

SELECT 'Setup complete. Tables created in dekhahok database.' AS status;
