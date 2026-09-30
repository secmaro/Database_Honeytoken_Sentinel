import os
import sqlite3
import hashlib
import threading
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import config
from seed_db import seed_database
import telegram_bot

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET

def is_locked():
    """Checks if the application is currently in lockdown mode."""
    return os.path.exists(config.LOCKDOWN_FILE)

def activate_lockdown():
    """Creates the lockdown flag file to trigger lockdown mode."""
    try:
        with open(config.LOCKDOWN_FILE, 'w') as f:
            f.write(datetime.now(timezone.utc).isoformat())
        app.logger.info("Lockdown activated remotely via Telegram.")
    except Exception as e:
        app.logger.error(f"Failed to activate lockdown: {e}")

def deactivate_lockdown():
    """Removes the lockdown flag file to restore access."""
    try:
        if os.path.exists(config.LOCKDOWN_FILE):
            os.remove(config.LOCKDOWN_FILE)
        app.logger.info("Lockdown deactivated remotely via Telegram.")
    except Exception as e:
        app.logger.error(f"Failed to deactivate lockdown: {e}")

@app.route('/')
def index():
    if is_locked():
        return render_template('locked.html'), 503
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '')
    password = request.form.get('password', '')
    
    # Capture telemetry
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    is_honeytoken = False
    
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        
        hashed_password = hashlib.md5(password.encode()).hexdigest()
        
        # Check if email and password are an exact honeytoken match
        cursor.execute('SELECT id FROM honeytoken_accounts WHERE email = ? AND password_hash = ?', (email, hashed_password))
        row = cursor.fetchone()
        
        if row:
            is_honeytoken = True
            
        # Log the attempt regardless
        cursor.execute('''
        INSERT INTO login_attempts (email_used, ip_address, user_agent, timestamp, honeytoken_match)
        VALUES (?, ?, ?, ?, ?)
        ''', (email, ip, user_agent, timestamp, is_honeytoken))
        
        conn.commit()
    except Exception as e:
        app.logger.error(f"Database error during login: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            
    if is_honeytoken:
        # Confirmed honeypot interaction!
        telegram_bot.send_alert(email, ip, user_agent, timestamp)
        # Deception flash message - makes them think password was the only issue
        flash("Invalid password. Please try again.")
    else:
        # Standard generic error message
        flash("Invalid credentials.")
        
    return redirect(url_for('index'))

@app.route('/health')
def health():
    if is_locked():
        return jsonify({"status": "locked"})
    return jsonify({"status": "ok"})

def init_app():
    """Application startup initialization routine."""
    # Ensure database is seeded if missing
    seed_database()
        
    # Start telegram bot polling in the background (if tokens exist)
    telegram_bot.start_polling(activate_lockdown, deactivate_lockdown)

# Start background tasks. To prevent double-execution when using 
# Flask's debug reloader, we only initialize in the child process
# (WERKZEUG_RUN_MAIN) or when not in debug mode (e.g. gunicorn).
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    init_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
