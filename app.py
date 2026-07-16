# =============================================================================
# St. Xavier High School IT Helpdesk Check-In Kiosk — Main Application
# =============================================================================
#
# WHAT THIS APP DOES:
#   A student walks up to the kiosk, scans their ID badge on the RFID reader,
#   and the app automatically creates a Freshdesk support ticket. The student
#   sees a welcome message and is directed to the next available IT specialist.
#
# HOW IT WORKS:
#   1. Flask serves a full-screen web page in Chrome (kiosk mode)
#   2. The RFID reader acts like a keyboard — it "types" the card number
#      into a hidden input field and presses Enter
#   3. JavaScript sends the card number to the /process_rfid endpoint
#   4. Python looks up the student in the school's PostgreSQL database
#   5. If found, it sends an email to Freshdesk which auto-creates a ticket
#   6. The page shows a success or error message, then resets for the next scan
#
# KEY FILES:
#   app.py                  — This file. The backend server and all logic.
#   .env                    — Credentials and configuration (NOT in the repo).
#   .env.template           — A blank template showing which values are needed.
#   templates/check_in.html — The main kiosk screen (scan prompt + success/error views).
#   templates/closed.html   — Shown outside of helpdesk hours.
#   static/styles.css       — All styling for both pages.
#   static/st_xavier_logo.png — The school/IT logo displayed on all screens.
#
# RUNNING LOCALLY (for development/testing):
#   1. Copy .env.template to .env and fill in credentials
#   2. pip install -r requirements.txt
#   3. python app.py
#   4. Open http://localhost:5000 in a browser
#
# DEPLOYING TO THE KIOSK:
#   The app is packaged as a standalone Windows .exe using PyInstaller.
#   See the GitHub Actions workflow (.github/workflows/build-exe.yml) and
#   the Deployment section of README.md for full instructions.
# =============================================================================

import os
import subprocess
import platform
import threading
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pyodbc
from dotenv import load_dotenv

# Load environment variables from the .env file in the same directory.
# This is how we keep credentials out of the source code.
load_dotenv()

# Set up file-based logging. All log entries go to kiosk.log in the same
# directory as the app. This is the first place to look when troubleshooting.
logging.basicConfig(
    filename='kiosk.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize the Flask web framework.
# template_folder: where HTML files live (templates/)
# static_folder:   where CSS, images, and JS live (static/)
app = Flask(__name__, template_folder='templates', static_folder='static')

# =============================================================================
# CONFIGURATION
# =============================================================================
# All settings are loaded from the .env file. Values after the comma are
# defaults used if the .env variable is missing. Credentials (passwords,
# usernames) have no defaults — the app will refuse to start without them.
# =============================================================================

# --- Email / SMTP Settings ---
# The app sends emails to Freshdesk to create support tickets.
# It uses Office 365 SMTP (or whatever server is configured).
FRESHDESK_EMAIL = os.getenv('FRESHDESK_EMAIL', 'helpdesk@stxavier.org')  # Recipient: where tickets are created
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.office365.com')             # Mail server hostname
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))                          # Mail server port (587 = TLS)
SMTP_USER = os.getenv('SMTP_USER')                                      # Login username (REQUIRED)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')                              # Login password (REQUIRED)

# --- Database Settings ---
# The school's student database (PostgreSQL via ODBC). Used to look up
# a student's name and email from their badge card number.
DB_SERVER = os.getenv('DB_SERVER', 'your-db-host.your-school.org')                # Database server hostname
DB_DATABASE = os.getenv('DB_DATABASE', 'your_database')                       # Database name
DB_USERNAME = os.getenv('DB_USERNAME')                                   # Database login (REQUIRED)
DB_PASSWORD = os.getenv('DB_PASSWORD')                                   # Database password (REQUIRED)
DB_DRIVER = os.getenv('DB_DRIVER', '{PostgreSQL Unicode(x64)}')          # ODBC driver name (x64 for Windows)

# --- Helpdesk Schedule ---
# Controls when the kiosk shows the check-in screen vs. the "closed" screen.
# Uses 24-hour format. Days use Python's weekday numbering: 0=Mon, 4=Fri.
OPEN_HOUR = int(os.getenv('OPEN_HOUR', '7'))                            # Opens at 7:00 AM
CLOSE_HOUR = int(os.getenv('CLOSE_HOUR', '16'))                         # Closes at 4:00 PM (16:00)
OPEN_DAYS = [int(d) for d in os.getenv('OPEN_DAYS', '0,1,2,3,4').split(',')]  # Mon-Fri

# Day names indexed by Python's weekday numbering (0=Monday ... 6=Sunday).
DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_helpdesk_open():
    """
    Check if the helpdesk is currently open based on the schedule
    configured in the .env file (OPEN_HOUR, CLOSE_HOUR, OPEN_DAYS).

    Returns True if the current day and hour fall within operating hours.
    The main route (/) uses this to pick which page to show on load, and the
    /health endpoint exposes it so each kiosk page can re-check the schedule on
    its own and switch over when it changes — in both directions:
      - closed.html auto-refreshes every 60s  -> switches to check-in at opening
      - check_in.html polls /health every 60s  -> switches to closed at closing
    """
    now = datetime.now()
    current_day = now.weekday()   # 0=Monday, 6=Sunday
    current_hour = now.hour

    if current_day not in OPEN_DAYS:
        return False
    if current_hour < OPEN_HOUR or current_hour >= CLOSE_HOUR:
        return False
    return True


def format_hour(hour_24):
    """
    Turn a 24-hour number from the .env file into a readable time string
    for display on the closed page. 7 -> "7:00 AM", 16 -> "4:00 PM".
    """
    suffix = 'AM' if hour_24 < 12 else 'PM'
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12  # Midnight and noon both land on 12, not 0
    return f'{hour_12}:00 {suffix}'


def format_open_days(days):
    """
    Turn the OPEN_DAYS list into a readable string for the closed page.

    Consecutive days are collapsed into a range, so the common Mon-Fri case
    reads "Monday - Friday" rather than listing all five. Non-consecutive
    days are separated by commas.

        [0,1,2,3,4]   -> "Monday - Friday"
        [0,1]         -> "Monday & Tuesday"
        [0,2,4]       -> "Monday, Wednesday, Friday"
        [0,1,2,4]     -> "Monday - Wednesday, Friday"

    Anything outside 0-6 is ignored so a typo in .env can't crash the page.
    """
    valid_days = sorted({d for d in days if 0 <= d <= 6})
    if not valid_days:
        return 'By appointment only'

    # Walk the sorted days and group runs of consecutive numbers together.
    groups = []
    start = previous = valid_days[0]
    for day in valid_days[1:]:
        if day == previous + 1:
            previous = day
        else:
            groups.append((start, previous))
            start = previous = day
    groups.append((start, previous))

    parts = []
    for first, last in groups:
        if first == last:
            parts.append(DAY_NAMES[first])
        elif last == first + 1:
            # A two-day run reads better as "Monday & Tuesday" than a range
            parts.append(f'{DAY_NAMES[first]} & {DAY_NAMES[last]}')
        else:
            parts.append(f'{DAY_NAMES[first]} – {DAY_NAMES[last]}')  # en dash
    return ', '.join(parts)


def get_user_info_from_cardnumber(cardnumber):
    """
    Look up a student in the school database using their badge card number.

    The RFID badge stores an encoded number. This function queries the
    PostgreSQL database to find the matching student's email and first name.

    Args:
        cardnumber: The encoded number from the RFID badge (string).

    Returns:
        A dict with 'email' and 'firstname' if found, or None if not found
        or if a database error occurs.

    Note: The query uses a parameterized placeholder (?) to prevent SQL
    injection — never insert user input directly into a query string.
    """
    conn = None
    cursor = None
    try:
        # Build the ODBC connection string from .env settings
        conn_str = f'DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_DATABASE};UID={DB_USERNAME};PWD={DB_PASSWORD}'
        conn = pyodbc.connect(conn_str, timeout=10)  # 10-second timeout prevents hanging
        cursor = conn.cursor()

        # Join three tables to get the student's email and name from their card number:
        #   - report.credential: links card numbers (encodednum) to person keys
        #   - report.person: has the student's first name
        #   - report.personcontact: has the student's email address
        query = """
        SELECT report.personcontact.email AS email, report.person.firstname AS firstname
        FROM report.personcontact, report.credential, report.person
        WHERE report.person.personkey = report.credential.personkey
        AND report.credential.personkey = report.personcontact.personkey
        AND report.credential.encodednum = ?
        """

        cursor.execute(query, (cardnumber,))
        result = cursor.fetchone()

        if result:
            logger.info(f'User found: {result.email}')
            return {'email': result.email, 'firstname': result.firstname}
        else:
            logger.warning(f'Card number not found: {cardnumber}')
            return None

    except pyodbc.Error as e:
        logger.error(f'Database error: {e}')
        return None
    finally:
        # Always close database connections, even if an error occurred
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def send_email(from_email, to_email, subject, body):
    """
    Send an email to Freshdesk to create a support ticket.

    The email is sent FROM the kiosk's SMTP account, but the Reply-To header
    is set to the student's email. This way, when IT staff reply to the
    Freshdesk ticket, the reply goes to the student.

    Args:
        from_email: The student's email (used as Reply-To).
        to_email:   The Freshdesk email that auto-creates tickets.
        subject:    Email subject line (becomes the ticket title).
        body:       Email body (becomes the ticket description).

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER        # Sent from the kiosk's email account
    msg['To'] = to_email            # Sent to Freshdesk
    msg['Subject'] = subject
    msg['Reply-To'] = from_email    # Replies go to the student
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()                                    # Upgrade to encrypted connection
            server.login(SMTP_USER, SMTP_PASSWORD)               # Authenticate with SMTP server
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        logger.info(f'Email sent successfully for {from_email}')
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f'SMTP Authentication Error: {e}')
        return False
    except smtplib.SMTPException as e:
        logger.error(f'SMTP Error: {e}')
        return False
    except Exception as e:
        logger.error(f'Email Error: {e}')
        return False


def launch_chrome_kiosk():
    """
    Launch Chrome in kiosk mode (full-screen, no address bar, no controls).

    This runs in a separate thread so it doesn't block the Flask server
    from starting. The 2-second delay gives the server time to be ready
    before Chrome tries to load the page.

    Chrome kiosk mode is what makes the app look like a dedicated kiosk
    application rather than a website in a browser.
    """
    import time
    url = 'http://localhost:5000'
    time.sleep(2)  # Wait for the Flask/Waitress server to start

    try:
        if platform.system() == 'Windows':
            subprocess.run(['cmd', '/c', 'start', 'chrome', '--kiosk', url], shell=False)
        elif platform.system() == 'Darwin':      # macOS
            subprocess.run(['open', '-a', 'Google Chrome', '--args', '--kiosk', url])
        elif platform.system() == 'Linux':
            subprocess.run(['google-chrome', '--kiosk', url])
        logger.info('Chrome kiosk launched')
    except Exception as e:
        logger.error(f'Failed to launch Chrome: {e}')

# =============================================================================
# ROUTES (URL Endpoints)
# =============================================================================

@app.route('/')
def index():
    """
    Main page — the only page users ever see.

    If the helpdesk is open: shows the check-in screen (check_in.html)
    where students scan their badge.

    If the helpdesk is closed: shows the closed screen (closed.html)
    with hours of operation.

    Each page re-checks the schedule on its own, so the kiosk switches
    automatically in both directions without anyone touching it:
    closed.html auto-refreshes every 60s and flips to check-in at opening;
    check_in.html polls /health every 60s and flips to closed at closing.

    The hours shown on the closed page are generated from the schedule in
    .env, so changing OPEN_HOUR/CLOSE_HOUR/OPEN_DAYS updates the display
    automatically — there is no second copy of the hours to keep in sync.
    """
    if is_helpdesk_open():
        return render_template('check_in.html')
    else:
        return render_template(
            'closed.html',
            days_text=format_open_days(OPEN_DAYS),
            open_time=format_hour(OPEN_HOUR),
            close_time=format_hour(CLOSE_HOUR),
        )


@app.route('/process_rfid', methods=['POST'])
def process_rfid():
    """
    Process a scanned RFID badge. Called by JavaScript when a badge is scanned.

    Expects a JSON POST body: { "rfid": "card_number_here" }

    Flow:
      1. Validate that an RFID value was provided
      2. Check if the helpdesk is currently open
      3. Look up the card number in the database
      4. If found, send an email to Freshdesk to create a ticket
      5. Return success (with the student's first name) or an error message

    The frontend JavaScript handles displaying the appropriate screen
    (success or error) based on the response.
    """
    try:
        data = request.json
        rfid = data.get('rfid')

        if not rfid:
            logger.warning('No RFID provided in request')
            return jsonify({'success': False, 'message': 'No RFID provided'}), 400

        # Double-check schedule (in case someone scans right at closing time)
        if not is_helpdesk_open():
            return jsonify({'success': False, 'message': 'Helpdesk is currently closed'}), 403

        # Look up the student in the database
        user_info = get_user_info_from_cardnumber(rfid)

        if user_info:
            email = user_info['email']
            firstname = user_info['firstname']

            # Send email to Freshdesk to create a support ticket
            subject = 'Checked In At The Helpdesk Kiosk'
            body = f'{email} Has Checked In At The Helpdesk Kiosk'

            if send_email(email, FRESHDESK_EMAIL, subject, body):
                return jsonify({'success': True, 'firstname': firstname}), 200
            else:
                return jsonify({'success': False, 'message': 'Failed to send email'}), 500
        else:
            return jsonify({'success': False, 'message': 'Badge not recognized'}), 404

    except Exception as e:
        logger.error(f'Error processing RFID: {e}')
        return jsonify({'success': False, 'message': 'An error occurred'}), 500


@app.route('/health')
def health():
    """
    Health check endpoint. Hit http://localhost:5000/health to verify
    the app is running and see if the helpdesk is currently open.
    Useful for monitoring and troubleshooting.

    Also load-bearing for the UI: check_in.html polls this endpoint every
    60 seconds and reloads (switching to the closed screen) once
    'helpdesk_open' turns false. If you change this endpoint, keep the
    'helpdesk_open' field in the response or that auto-switch will break.
    """
    return jsonify({
        'status': 'healthy',
        'helpdesk_open': is_helpdesk_open(),
        'timestamp': datetime.now().isoformat()
    })

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # --- Validate required configuration before starting ---
    # The app won't work without SMTP and database credentials.
    # Fail fast with a clear error message rather than crashing later.
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error('SMTP credentials not configured. Check your .env file.')
        print('ERROR: SMTP credentials not configured. Check your .env file.')
        exit(1)

    if not DB_USERNAME or not DB_PASSWORD:
        logger.error('Database credentials not configured. Check your .env file.')
        print('ERROR: Database credentials not configured. Check your .env file.')
        exit(1)

    print('Starting St. Xavier IT Helpdesk Kiosk...')
    logger.info('Application starting')

    # --- Launch Chrome in kiosk mode in a background thread ---
    # daemon=True means this thread will automatically stop when the main app stops
    chrome_thread = threading.Thread(target=launch_chrome_kiosk, daemon=True)
    chrome_thread.start()

    # --- Start the web server ---
    # Waitress is a production-grade WSGI server (much more stable than
    # Flask's built-in dev server). It listens on all network interfaces
    # (0.0.0.0) on port 5000.
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
