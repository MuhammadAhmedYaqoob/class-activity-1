# ngrok http --url=parrot-sacred-wildcat.ngrok-free.app 5000

import os
import threading
from flask import Flask, request
from dotenv import load_dotenv
import openai
import gspread
import requests
from google.oauth2 import service_account
from utils import fetch_wp_file, chat_with_gpt, send_message

load_dotenv()
# Configuration parameters from environment variables
INSTANCE_ID = os.getenv('INSTANCE_ID')
API_TOKEN = os.getenv('API_TOKEN')
APPROVED_FILE = os.getenv('APPROVED_FILE')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
openai.api_key = os.getenv('OPENAI_API_KEY')

# Google Sheets setup
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = service_account.Credentials.from_service_account_file(
    'zeus-registration-form-0250d4aaef74.json', scopes=scope
)

client = gspread.authorize(creds)

# Initialize the main sheet
sheet_id = '1C1kOnjbB5E7IUZ3SMViGGE9-rLRldDg3dO5Xc3hjEhE'
sheet = client.open_by_key(sheet_id)
worksheet1 = sheet.get_worksheet(0)  # Main worksheet

app = Flask(__name__)

# Global set to track processed message IDs (to prevent duplicates)
processed_message_ids = set()

# Active sessions dictionary to manage per-chat timers, locks, and conversation history
active_sessions = {}
active_sessions_lock = threading.Lock()


@app.route(f"/instance/{INSTANCE_ID}", methods=["POST", "GET"])
def instance_webhook():
    if request.method == "GET":
        challenge = request.args.get("hub.challenge")
        token = request.args.get("hub.verify_token")
        if token == VERIFY_TOKEN:
            print("Webhook verified successfully.")
            return challenge, 200
        else:
            print("Webhook verification failed.")
            return "Verification token mismatch", 403

    data = request.json

    message_data = data.get("data", {}).get("message", {})
    message_id = message_data.get("id", {}).get("_serialized")
    chat_id = message_data.get("from")
    message_body = message_data.get("body")
    has_media = message_data.get("hasMedia", False)

    if not (chat_id and message_id):
        print("Missing required data in webhook payload.")
        return "Invalid data", 400

    # Check for duplicate messages
    if message_id in processed_message_ids:
        print(f"Duplicate message received: {message_id}")
        return "OK", 200
    processed_message_ids.add(message_id)

    print(f"Processing new message: {message_id} from {chat_id}")

    # **Check if the message contains media**
    with open(APPROVED_FILE, "r") as f:
            approved_numbers = [line.strip() for line in f.readlines()]

    if has_media and chat_id in approved_numbers:

        reply_text = """I'm sorry, but I couldn't understand your message. Could you please type it clearly and resend it?

 _Replied by_  *ZEUS AI BOT* ✨"""
        send_message(chat_id, reply_text)
        print(f"Sent media rejection message to {chat_id}")
        return "OK", 200

    # **Process text messages normally**
    threading.Thread(target=process_message, args=(chat_id, message_body)).start()
    return "OK", 200


def cleanup_session(chat_id):
    """Cleanup session data for a chat after 2 minutes of inactivity."""
    with active_sessions_lock:
        if chat_id in active_sessions:
            del active_sessions[chat_id]
            print(f"Session cleaned up for chat {chat_id}")


def process_message(chat_id, message_body):
    """Process incoming messages with authorization checks, external message fetching, pause conditions, and AI response generation."""
    # Read approved numbers
    try:
        with open(APPROVED_FILE, "r") as f:
            approved_numbers = [line.strip() for line in f.readlines()]
    except Exception as e:
        print(f"Error reading approved numbers file: {e}")
        approved_numbers = []

    # Fetch numbers from "Ignore Contacts" column (already includes @c.us)
    try:
        ignore_contacts = worksheet1.col_values(worksheet1.find("Ignore Contacts").col)
        ignore_contacts = [num.strip() + "@c.us" for num in ignore_contacts if num.strip()]
    except Exception as e:
        print(f"Error reading ignore contacts: {e}")
        ignore_contacts = []

    # Normalize chat ID for comparison (remove '+' and check suffixes)
    normalized_chat_id = chat_id.lstrip('+').replace('@c.us', '')
    is_authorized = any(
        norm_id == normalized_chat_id 
        for norm_id in [num.replace('+', '').replace('@c.us', '') for num in approved_numbers]
    )

    if not is_authorized:
        print(f"Unauthorized chat ID: {chat_id}")
        return

    if chat_id in ignore_contacts:
        print(f"Ignoring chat ID: {chat_id}")
        return

    # Retrieve or create session for the chat
    with active_sessions_lock:
        session = active_sessions.get(chat_id)
        if not session:
            session = {
                'lock': threading.Lock(),
                'timer': None,
                'history': [],
                'paused': False
            }
            active_sessions[chat_id] = session
        else:
            if session.get('paused'):
                print(f"Ignoring message from {chat_id} as session is paused.")
                return

        # Manage timer based on session state
        if not session['paused']:
            if session.get('timer'):
                session['timer'].cancel()
            # Reset to 2 minutes for active sessions
            session['timer'] = threading.Timer(120, cleanup_session, args=(chat_id,))
            session['timer'].start()

    # Check for 'hii' in previous bot messages on every incoming message
    WA_API_URL = f"https://waapi.app/api/v1/instances/{INSTANCE_ID}/client/action/fetch-messages"
    headers = {"Authorization": f"Bearer {API_TOKEN}", "Accept": "application/json", "Content-Type": "application/json"}
    payload = {
            "chatId": chat_id,
            "limit": 1,
            "fromMe": True
    }        
    try:
        response = requests.post(WA_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            messages = response.json().get("data", {}).get("data", [])
            for msg in messages:
                body = msg.get("message", {}).get("body", "").strip()
                if body == "Hii":
                    with active_sessions_lock:
                        session['paused'] = True
                        if session.get('timer'):
                            session['timer'].cancel()
                        # Set 5-minute timer for paused session
                        session['timer'] = threading.Timer(300, cleanup_session, args=(chat_id,))
                        session['timer'].start()
                        print(f"Session {chat_id} paused due to 'Hii' detection.")
                        reply_text = """Admin has joined the chat. 

_Replied by_  *ZEUS AI BOT* ✨"""
                        send_message(chat_id, reply_text)

                    return
    except Exception as e:
        print(f"Error fetching messages: {e}")

    # Proceed with normal processing if not paused
    with session['lock']:
        session['history'].append(f"User: {message_body}")
        conversation_context = "\n".join(session['history'])

    external_context = fetch_wp_file()
    combined_context = f"{conversation_context}\n{external_context}" if external_context else conversation_context

    ai_response = chat_with_gpt(message_body, combined_context)

    with session['lock']:
        session['history'].append(f"Bot: {ai_response}")

    send_message(chat_id, ai_response)
    print(f"Sent reply to chat {chat_id}")

if __name__ == '__main__':
    app.run("127.0.0.1", port=80, debug=False)

