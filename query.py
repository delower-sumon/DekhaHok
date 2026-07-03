import sqlite3

def run():
    conn = sqlite3.connect('dekhahok.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, status FROM events")
    print("ALL EVENTS:")
    for row in cursor.fetchall():
        print(row)
        
    cursor.execute("SELECT id, booking_status, payment_status, fee_amount FROM bookings")
    print("ALL BOOKINGS:")
    for row in cursor.fetchall():
        print(row)
    
if __name__ == '__main__':
    run()
