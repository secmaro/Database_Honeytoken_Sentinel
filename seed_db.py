import sqlite3
import hashlib
import json
import random
import os
import secrets
from datetime import datetime, timedelta
import config

def hash_password(password):
    """Returns the MD5 hash of the given password string."""
    return hashlib.md5(password.encode()).hexdigest()

def generate_random_timestamp(start_date, end_date):
    """Generates a random timestamp during business hours within the date range."""
    while True:
        time_between_dates = end_date - start_date
        days_between_dates = time_between_dates.days
        random_number_of_days = random.randrange(days_between_dates)
        random_date = start_date + timedelta(days=random_number_of_days)
        
        # Add random hours between 9 and 17 (business hours)
        random_hours = random.randint(9, 16)
        random_minutes = random.randint(0, 59)
        random_seconds = random.randint(0, 59)
        
        random_date = random_date.replace(hour=random_hours, minute=random_minutes, second=random_seconds)
        
        # 0-4 are Monday to Friday
        if random_date.weekday() < 5:
            return random_date.strftime("%Y-%m-%d %H:%M:%S")

def seed_database():
    """Seeds the SQLite database with decoy accounts and fake login history."""
    random.seed(42) # fixed seed for reproducibility
    
    db_path = config.DATABASE_PATH
    
    # Ensure directory exists if path has one
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS honeytoken_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        permissions TEXT,
        created_at TEXT,
        last_login TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_used TEXT,
        ip_address TEXT,
        user_agent TEXT,
        timestamp TEXT,
        honeytoken_match BOOLEAN
    )
    ''')

    columns = {row[1] for row in cursor.execute('PRAGMA table_info(login_attempts)')}
    if 'password_used' in columns:
        cursor.execute('UPDATE login_attempts SET password_used = NULL')
    conn.commit()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS login_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        login_time TEXT,
        ip_address TEXT,
        success BOOLEAN,
        FOREIGN KEY (account_id) REFERENCES honeytoken_accounts(id)
    )
    ''')
    
    # Check if already seeded
    cursor.execute('SELECT COUNT(*) FROM honeytoken_accounts')
    if cursor.fetchone()[0] > 0:
        print("Database is already seeded.")
        conn.close()
        return

    now = datetime.now()
    six_months_ago = now - timedelta(days=180)
    two_weeks_ago = now - timedelta(days=14)

    accounts = [
        {
            "email": "mohamed_support@example.com",
            "password": secrets.token_urlsafe(16),
            "role": "Support",
            "permissions": ["view_tickets", "reply_tickets"]
        },
        {
            "email": "omar.khalil@example.com",
            "password": secrets.token_urlsafe(16),
            "role": "Administrator",
            "permissions": ["full_access", "manage_users", "system_config", "audit_logs"]
        },
        {
            "email": "backup@example.com",
            "password": secrets.token_urlsafe(16),
            "role": "Backup Operator",
            "permissions": ["run_backups", "view_backup_logs"]
        }
    ]

    internal_ips = ["192.168.1.45", "10.0.0.12", "192.168.1.101", "10.0.0.55", "192.168.1.200"]

    for acc in accounts:
        created_at = six_months_ago.strftime("%Y-%m-%d %H:%M:%S")
        last_login = two_weeks_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
        INSERT INTO honeytoken_accounts (email, password_hash, role, permissions, created_at, last_login)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (acc["email"], hash_password(acc["password"]), acc["role"], json.dumps(acc["permissions"]), created_at, last_login))
        
        account_id = cursor.lastrowid
        
        # Generate 5-8 fake login entries per account over the past 2 weeks
        num_logins = random.randint(5, 8)
        for _ in range(num_logins):
            login_time = generate_random_timestamp(two_weeks_ago, now)
            ip = random.choice(internal_ips)
            # Most should be success=True
            success = random.choices([True, False], weights=[0.85, 0.15])[0]
            
            cursor.execute('''
            INSERT INTO login_history (account_id, login_time, ip_address, success)
            VALUES (?, ?, ?, ?)
            ''', (account_id, login_time, ip, success))

    conn.commit()
    conn.close()
    
    print(f"[OK] Database seeded successfully at {db_path} with {len(accounts)} accounts.")

if __name__ == "__main__":
    seed_database()
