# DekhaHok — Local Development & Testing Guide
# Windows / Linux / macOS  |  Python 3.10+  |  MySQL 8.x

# ════════════════════════════════════════════════════════════
# STEP 1 — Install MySQL (skip if already installed)
# ════════════════════════════════════════════════════════════

# Windows:
#   Download MySQL Installer from https://dev.mysql.com/downloads/installer/
#   Choose "Developer Default" → install → set a root password you remember

# Ubuntu/Debian:
#   sudo apt update && sudo apt install mysql-server -y
#   sudo mysql_secure_installation

# macOS (Homebrew):
#   brew install mysql
#   brew services start mysql
#   mysql_secure_installation


# ════════════════════════════════════════════════════════════
# STEP 2 — Create the database
# ════════════════════════════════════════════════════════════

# Open your MySQL shell:
#   Windows:  Open "MySQL Command Line Client" from Start Menu
#   Linux/Mac: mysql -u root -p

# Then run the setup file:
#   mysql -u root -p < mysql_local_setup.sql

# Or paste this manually inside the MySQL shell:
#
#   CREATE DATABASE dekhahok CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
#   CREATE USER 'dekhahok_user'@'localhost' IDENTIFIED BY 'dekhahok_local_pass';
#   GRANT ALL PRIVILEGES ON dekhahok.* TO 'dekhahok_user'@'localhost';
#   FLUSH PRIVILEGES;
#
# The tables will be created automatically when FastAPI starts (init_db).


# ════════════════════════════════════════════════════════════
# STEP 3 — Project setup
# ════════════════════════════════════════════════════════════

# Your folder structure should look like this:
#
#   dekhahok/
#   ├── main.py
#   ├── database.py
#   ├── models.py
#   ├── requirements.txt
#   ├── .env                  ← you create this from .env.example
#   ├── admin/
#   │   └── index.html
#   └── static/
#       └── DekhaHok.html

# 1. Open a terminal/command prompt in the dekhahok/ folder

# 2. Create and activate virtual environment:
#
#   Windows:
#     python -m venv venv
#     venv\Scripts\activate
#
#   Linux/macOS:
#     python3 -m venv venv
#     source venv/bin/activate
#
#   You should see (venv) at the start of your terminal prompt.

# 3. Install dependencies:
#     pip install -r requirements.txt

# 4. Create your .env file:
#     Copy .env.example → .env  and fill in your values:
#
#   DB_HOST=localhost
#   DB_PORT=3306
#   DB_NAME=dekhahok
#   DB_USER=dekhahok_user
#   DB_PASSWORD=dekhahok_local_pass
#   ADMIN_SECRET_KEY=pick-any-long-string-here-for-local-testing


# ════════════════════════════════════════════════════════════
# STEP 4 — Run the server
# ════════════════════════════════════════════════════════════

#   uvicorn main:app --reload
#
#   You should see:
#     INFO:     Started server process
#     [dekhahok] Database tables ready.
#     INFO:     Uvicorn running on http://127.0.0.1:8000

# --reload means the server restarts automatically every time
# you save any .py file. No need to restart manually during dev.


# ════════════════════════════════════════════════════════════
# STEP 5 — Test the URLs
# ════════════════════════════════════════════════════════════

# Open these in your browser:
#
#   http://localhost:8000/
#     → DekhaHok frontend (your HTML)
#
#   http://localhost:8000/docs
#     → Interactive API docs (Swagger UI)
#     → Test every endpoint here without writing any code
#
#   http://localhost:8000/admin
#     → Admin dashboard
#     → Login with the ADMIN_SECRET_KEY from your .env


# ════════════════════════════════════════════════════════════
# STEP 6 — End-to-end test checklist
# ════════════════════════════════════════════════════════════

# Run through these in order:

# [ ] 1. Open http://localhost:8000/
#        → Page loads, date buttons show the coming Friday & Saturday with dates
#        → Friday 5PM is pre-selected

# [ ] 2. Fill in the booking form:
#        Name: Test User
#        Phone: 01711000000
#        Email: test@test.com (optional)
#        Age: 25 (optional)
#        Group size: 2
#        Select any date slot
#        Venue: Public Place
#        Click "Complete Reservation"
#
#        → Spinner shows, then success modal appears
#        → Modal shows a tracking ID like DH-XXXXXXXX
#        → Copy/note the tracking ID

# [ ] 3. Verify in MySQL:
#        mysql -u dekhahok_user -p dekhahok
#        SELECT * FROM bookings;
#        → Should see your test booking with status='processing'

# [ ] 4. Test tracking:
#        Scroll down to "বুকিং ট্র্যাক করুন"
#        Paste the tracking ID → Click "চেক করুন"
#        → Shows status: প্রক্রিয়াধীন (processing)

# [ ] 5. Test API docs:
#        Open http://localhost:8000/docs
#        Try GET /api/bookings/track/{tracking_id}
#        → Returns booking data as JSON

# [ ] 6. Test admin dashboard:
#        Open http://localhost:8000/admin
#        Enter your ADMIN_SECRET_KEY → login
#        → Should see the booking you submitted in "Bookings" tab
#        → Try marking payment as "paid" → Save
#        → Try creating a group (Groups tab → Create Group)
#        → Assign your test booking to the group
#        → Check tracking again → status should now show "confirmed"


# ════════════════════════════════════════════════════════════
# COMMON ERRORS & FIXES
# ════════════════════════════════════════════════════════════

# Error: "Can't connect to MySQL server"
# Fix:   Make sure MySQL service is running.
#        Windows:  Open Services → MySQL80 → Start
#        Linux:    sudo systemctl start mysql
#        macOS:    brew services start mysql

# Error: "Access denied for user 'dekhahok_user'"
# Fix:   Re-run mysql_local_setup.sql, or in MySQL shell:
#        ALTER USER 'dekhahok_user'@'localhost' IDENTIFIED BY 'dekhahok_local_pass';
#        FLUSH PRIVILEGES;

# Error: "ModuleNotFoundError: No module named 'fastapi'"
# Fix:   Your venv isn't activated.
#        Windows: venv\Scripts\activate
#        Linux:   source venv/bin/activate

# Error: Phone validation fails on test
# Fix:   Use a real BD format: 01711000000 or 01911000000
#        The validator requires 01X-XXXXXXXX (11 digits, starts with 013-019)

# Error: "422 Unprocessable Entity" from API
# Fix:   Open http://localhost:8000/docs and check the exact error detail.
#        Usually a missing required field or wrong data type.

# Error: Admin login fails
# Fix:   Make sure ADMIN_SECRET_KEY in .env has no extra spaces/quotes.
#        Copy it exactly into the admin login field.


# ════════════════════════════════════════════════════════════
# USEFUL COMMANDS DURING DEVELOPMENT
# ════════════════════════════════════════════════════════════

# Restart server (if not using --reload):
#   Ctrl+C → uvicorn main:app --reload

# Wipe all test data and start fresh:
#   mysql -u dekhahok_user -p dekhahok
#   TRUNCATE TABLE group_members;
#   TRUNCATE TABLE meetup_groups;
#   TRUNCATE TABLE bookings;

# View all bookings in terminal:
#   mysql -u dekhahok_user -p dekhahok -e "SELECT tracking_id, name, booking_status FROM bookings;"

# Check server logs:
#   The terminal running uvicorn shows every request in real time.
#   Look for lines like:  POST /api/bookings  201
#                         GET  /api/bookings/track/DH-XXXX  200
