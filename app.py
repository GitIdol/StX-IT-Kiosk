# St. Xavier High School IT Helpdesk Check-In Kiosk
# --------------------------------------------------
# This app allows students to check in by scanning their ID badge.
# It queries the school database for their info and creates a Freshdesk ticket.

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

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    filename='kiosk.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# =============================================================================
# CONFIGURATION (loaded from .env file)
# =============================================================================

# Email/SMTP settings
FRESHDESK_EMAIL = os.getenv('FRESHDESK_EMAIL', 'helpdesk@stxavier.org')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.office365.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')

# Database settings
DB_SERVER = os.getenv('DB_SERVER', 'your-db-host.your-school.org')
DB_DATABASE = os.getenv('DB_DATABASE', 'your_database')
DB_USERNAME = os.getenv('DB_USERNAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_DRIVER = os.getenv('DB_DRIVER', '{PostgreSQL Unicode(x64)}')

# Schedule settings (24-hour format)
OPEN_HOUR = int(os.getenv('OPEN_HOUR', '7'))    # 7 AM
CLOSE_HOUR = int(os.getenv('CLOSE_HOUR', '16'))  # 4 PM (16:00)
# Days open: 0=Monday, 1=Tuesday, ..., 4=Friday (weekdays by default)
OPEN_DAYS = [int(d) for d in os.getenv('OPEN_DAYS', '0,1,2,3,4').split(',')]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_helpdesk_open():
    """Check if the helpdesk is currently open based on schedule."""
    now = datetime.now()
    current_day = now.weekday()  # 0=Monday, 6=Sunday
    current_hour = now.hour

    if current_day not in OPEN_DAYS:
        return False
    if current_hour < OPEN_HOUR or current_hour >= CLOSE_HOUR:
        return False
    return True


def get_user_info_from_cardnumber(cardnumber):
    """Fetch email and first name from database using the card number."""
    conn = None
    cursor = None
    try:
        conn_str = f'DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_DATABASE};UID={DB_USERNAME};PWD={DB_PASSWORD}'
        conn = pyodbc.connect(conn_str, timeout=10)
        cursor = conn.cursor()

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
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def send_email(from_email, to_email, subject, body):
    """Send email to Freshdesk to create a ticket."""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Reply-To'] = from_email
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
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
    """Launch Chrome in kiosk mode pointing to the app."""
    import time
    url = 'http://localhost:5000'
    time.sleep(2)  # Wait for Flask to start

    try:
        if platform.system() == 'Windows':
            subprocess.run(['cmd', '/c', 'start', 'chrome', '--kiosk', url], shell=False)
        elif platform.system() == 'Darwin':
            subprocess.run(['open', '-a', 'Google Chrome', '--args', '--kiosk', url])
        elif platform.system() == 'Linux':
            subprocess.run(['google-chrome', '--kiosk', url])
        logger.info('Chrome kiosk launched')
    except Exception as e:
        logger.error(f'Failed to launch Chrome: {e}')

# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    """Render the check-in page or closed message based on schedule."""
    if is_helpdesk_open():
        return render_template('check_in.html')
    else:
        return render_template('closed.html')


@app.route('/process_rfid', methods=['POST'])
def process_rfid():
    """Process the scanned RFID badge."""
    try:
        data = request.json
        rfid = data.get('rfid')

        if not rfid:
            logger.warning('No RFID provided in request')
            return jsonify({'success': False, 'message': 'No RFID provided'}), 400

        # Check if helpdesk is open
        if not is_helpdesk_open():
            return jsonify({'success': False, 'message': 'Helpdesk is currently closed'}), 403

        user_info = get_user_info_from_cardnumber(rfid)

        if user_info:
            email = user_info['email']
            firstname = user_info['firstname']

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
    """Health check endpoint for monitoring."""
    return jsonify({
        'status': 'healthy',
        'helpdesk_open': is_helpdesk_open(),
        'timestamp': datetime.now().isoformat()
    })

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # Validate required config
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

    # Start Chrome in kiosk mode (in a separate thread)
    chrome_thread = threading.Thread(target=launch_chrome_kiosk, daemon=True)
    chrome_thread.start()

    # Run the Flask app with waitress (production server)
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
