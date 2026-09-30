import requests
import threading
import time
import logging
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_base_url():
    """Returns the base URL for the Telegram Bot API."""
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}"

def send_alert(email, ip, user_agent, timestamp):
    """
    Sends a richly formatted alert message to the configured Telegram chat.
    """
    if not config.BOT_TOKEN or not config.CHAT_ID:
        logger.warning("Telegram bot token or chat ID not configured. Skipping alert.")
        return False
        
    url = f"{get_base_url()}/sendMessage"
    
    message = f"""🚨 <b>HONEYTOKEN ALERT</b> 🚨

📧 <b>Email Used:</b> {email}
🌐 <b>Attacker IP:</b> {ip}
🖥️ <b>User-Agent:</b> {user_agent}
🕐 <b>Timestamp:</b> {timestamp}

⚠️ A honeytoken credential was used on the login page.
This is a confirmed unauthorized access attempt."""

    payload = {
        "chat_id": config.CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "🔒 Lock Login Page",
                    "callback_data": "lock_login"
                }
            ]]
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False

def _polling_worker(lockdown_callback, unlock_callback=None):
    """
    Background worker that uses long-polling to wait for callbacks from the Telegram bot.
    """
    if not config.BOT_TOKEN or not config.CHAT_ID:
        logger.warning("Telegram bot token or chat ID not configured. Polling will not start.")
        return

    # Delete webhook to ensure getUpdates works without conflict
    try:
        requests.get(f"{get_base_url()}/deleteWebhook", timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to delete webhook: {e}")
        
    offset = 0
    url = f"{get_base_url()}/getUpdates"
    
    logger.info("Started Telegram polling thread.")
    
    while True:
        try:
            payload = {"offset": offset, "timeout": 30}
            response = requests.get(url, params=payload, timeout=40)
            
            if response.status_code != 200:
                time.sleep(5)
                continue
                
            data = response.json()
            
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                
                if "callback_query" in update:
                    cq = update["callback_query"]
                    cq_id = cq["id"]
                    data_payload = cq.get("data", "")
                    
                    message = cq.get("message", {})
                    chat = message.get("chat", {})
                    chat_id = str(chat.get("id", ""))
                    
                    # Only process callbacks from the configured CHAT_ID
                    if chat_id != str(config.CHAT_ID):
                        # Still answer query to stop spinner for the unauthorized user
                        requests.post(f"{get_base_url()}/answerCallbackQuery", json={"callback_query_id": cq_id}, timeout=5)
                        continue
                        
                    if data_payload.startswith("lock_login"):
                        # 1. Answer callback query to dismiss spinner
                        requests.post(f"{get_base_url()}/answerCallbackQuery", json={
                            "callback_query_id": cq_id,
                            "text": "Locking down the application..."
                        }, timeout=5)
                        
                        # 2. Edit original message to remove button and add status
                        msg_id = message.get("message_id")
                        requests.post(f"{get_base_url()}/editMessageText", json={
                            "chat_id": chat_id,
                            "message_id": msg_id,
                            "text": message.get("text", "") + "\n\n✅ Login page has been LOCKED."
                        }, timeout=5)
                        
                        # 3. Call the lockdown callback to trigger the kill switch
                        lockdown_callback()
                        
                        # 4. Send confirmation message
                        requests.post(f"{get_base_url()}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": "🔒 The application is now in LOCKDOWN mode. Access is blocked.",
                            "reply_markup": {
                                "inline_keyboard": [[
                                    {
                                        "text": "🔓 Unlock Login Page",
                                        "callback_data": "unlock_login"
                                    }
                                ]]
                            }
                        }, timeout=5)
                        
                    elif data_payload.startswith("unlock_login"):
                        # 1. Answer callback
                        requests.post(f"{get_base_url()}/answerCallbackQuery", json={
                            "callback_query_id": cq_id,
                            "text": "Unlocking the application..."
                        }, timeout=5)
                        
                        # 2. Edit original message to remove button
                        msg_id = message.get("message_id")
                        requests.post(f"{get_base_url()}/editMessageText", json={
                            "chat_id": chat_id,
                            "message_id": msg_id,
                            "text": message.get("text", "") + "\n\n✅ Login page has been UNLOCKED."
                        }, timeout=5)
                        
                        # 3. Call unlock callback
                        if unlock_callback:
                            unlock_callback()
                            
                        # 4. Confirmation
                        requests.post(f"{get_base_url()}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": "🔓 The application is now UNLOCKED. Access is restored."
                        }, timeout=5)
                        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in polling loop: {e}")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error in polling loop: {e}")
            time.sleep(5)

def start_polling(lockdown_callback, unlock_callback=None):
    """
    Starts the Telegram bot long-polling in a background daemon thread.
    """
    thread = threading.Thread(target=_polling_worker, args=(lockdown_callback, unlock_callback), daemon=True)
    thread.start()
