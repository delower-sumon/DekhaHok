# DekhaHok 🤝

A minimal and professional seat booking and meetup management platform. DekhaHok facilitates group formation and venue assignment for social meetups.

## 🚀 Key Features

- **Seat Booking**: Simple interface for users to request bookings with group preferences.
- **Real-time Tracking**: Users can track their booking status using a unique Tracking ID.
- **Admin Dashboard**: Comprehensive management system to organize bookings, create groups, and assign venues.
- **Location Integration**: Matches users based on current and preferred meeting locations.
- **Mobile Responsive**: Fully optimized for a seamless experience on all devices.

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL (configured via `psycopg2`)
- **Frontend**: Vanilla HTML / CSS / JavaScript
- **Environment**: Managed via `python-dotenv`

## 🏁 Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL/MySQL database

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd DekhaHok_v1
   ```

2. **Set up virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration**:
   Create a `.env` file from `.env.example`:
   ```env
   DATABASE_URL=your_database_url
   ADMIN_SECRET_KEY=your_secure_key
   ```

5. **Run the application**:
   ```bash
   uvicorn main:app --reload
   ```

## 📁 Project Structure

- `main.py`: Core FastAPI application and API routes.
- `models.py`: Pydantic schemas for data validation.
- `database.py`: Database connection and initialization logic.
- `static/`: Frontend assets (HTML, CSS, JS).
- `admin/`: Admin panel interface.

## 📄 License

This project is proprietary. All rights reserved.
