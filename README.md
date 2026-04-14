# St. Xavier IT Helpdesk Check-In Kiosk

A simple check-in kiosk for the St. Xavier High School IT Help Desk. Students scan their RFID badge, and the app automatically creates a Freshdesk ticket.

## How It Works

1. Student scans their ID badge on the RFID reader
2. App queries the school database to get the student's email and name
3. App sends an email to Freshdesk, auto-creating a ticket
4. IT staff sees the ticket and can quickly add issue details

## Setup

### Prerequisites

- Windows PC with Python 3.10+
- PostgreSQL ODBC driver installed
- Chrome browser installed
- RFID badge reader (acts as keyboard input)

### Installation

1. Clone this repository
2. Copy `.env.template` to `.env` and fill in credentials:
   ```
   cp .env.template .env
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the app:
   ```
   python app.py
   ```

### Building the EXE

The app can be built as a standalone Windows executable using PyInstaller:

```
pip install pyinstaller
pyinstaller --onefile --add-data "templates;templates" --add-data "static;static" --add-data ".env;." --name Kiosk_App app.py
```

Or simply push a version tag (e.g., `v2.0`) to trigger the GitHub Actions workflow.

## Configuration

All configuration is done via the `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `SMTP_SERVER` | SMTP server for sending emails | smtp.office365.com |
| `SMTP_PORT` | SMTP port | 587 |
| `SMTP_USER` | SMTP username | - |
| `SMTP_PASSWORD` | SMTP password | - |
| `FRESHDESK_EMAIL` | Email that creates Freshdesk tickets | helpdesk@stxavier.org |
| `DB_SERVER` | Database server | your-db-host.your-school.org |
| `DB_DATABASE` | Database name | your_database |
| `DB_USERNAME` | Database username | report |
| `DB_PASSWORD` | Database password | report |
| `DB_DRIVER` | ODBC driver name | {PostgreSQL Unicode(x64)} |
| `OPEN_HOUR` | Hour helpdesk opens (24h) | 7 |
| `CLOSE_HOUR` | Hour helpdesk closes (24h) | 16 |
| `OPEN_DAYS` | Days open (0=Mon, 4=Fri) | 0,1,2,3,4 |

## Deployment

### First-Time Setup

1. Download `Kiosk_App.exe` and `.env.template` from the latest [Release](../../releases)
2. Place both files in a folder on the kiosk PC (e.g., `C:\Kiosk`)
3. Rename `.env.template` to `.env`
4. Edit `.env` and fill in the actual credentials:
   - `SMTP_USER` — the Office 365 account used to send emails (e.g., `kiosk@your-school.org`)
   - `SMTP_PASSWORD` — the password for that account
   - `DB_USERNAME` — PostgreSQL database username
   - `DB_PASSWORD` — PostgreSQL database password
5. Double-click `Kiosk_App.exe` to verify it starts (Chrome should open in kiosk mode)
6. To auto-launch on boot, add a shortcut to `Kiosk_App.exe` in the Windows Startup folder:
   - Press `Win + R`, type `shell:startup`, press Enter
   - Paste a shortcut to `Kiosk_App.exe` in that folder
7. Configure Windows kiosk mode or auto-login as needed

### Updating to a New Version

1. On the kiosk PC, go to the [Releases](../../releases) page
2. Download the latest `Kiosk_App.exe`
3. Close the running kiosk app (or reboot the PC)
4. Replace the old `Kiosk_App.exe` with the new one — keep the existing `.env` file as-is
5. Restart the PC (it will auto-launch with the new version)

### Important Notes

- The `.env` file contains credentials and is **not** included in the repository — it lives only on the kiosk PC
- The exe is self-contained — no Python or dependency installation required
- The app requires Chrome to be installed on the kiosk PC
- The PostgreSQL ODBC driver (`PostgreSQL Unicode(x64)`) must be installed on the kiosk PC
- Logs are written to `kiosk.log` in the same directory as the exe

## Troubleshooting

**App crashes or freezes:** Reboot the PC. The app is designed to auto-restart on boot.

**Badge not recognized:** The student's card may not be in the database, or there may be a database connection issue. Check `kiosk.log` for details.

**Email not sending:** Check SMTP credentials in `.env`. Verify the Office 365 account is active.

## License

Internal use only - St. Xavier High School IT Department
