# St. Xavier IT Helpdesk Check-In Kiosk

A check-in kiosk for the St. Xavier High School IT Help Desk. Students scan their RFID badge, and the app automatically creates a Freshdesk support ticket.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     KIOSK PC                            │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌───────────────────┐  │
│  │   RFID   │───>│  Chrome  │───>│   Kiosk_App.exe   │  │
│  │  Reader  │    │ (Kiosk   │    │  (Flask/Waitress)  │  │
│  │          │    │  Mode)   │    │                    │  │
│  └──────────┘    └──────────┘    └─────────┬─────────┘  │
│                                            │            │
└────────────────────────────────────────────│────────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                  │
                          ▼                  ▼                  ▼
                   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
                   │  Student DB │   │  Office 365  │   │  Freshdesk  │
                   │ (PostgreSQL)│   │    (SMTP)    │   │  (Tickets)  │
                   └─────────────┘   └─────────────┘   └─────────────┘
```

**The RFID reader acts like a keyboard** — when a student scans their badge, the reader "types" the card number into the app and presses Enter. No special drivers or SDK needed.

## How It Works

1. Student walks up to the kiosk and scans their ID badge on the RFID reader
2. The app queries the school's PostgreSQL database to find the student's email and name
3. The app sends an email to Freshdesk, which automatically creates a support ticket
4. The student sees a "Welcome" message and is directed to the next available IT specialist
5. After 7 seconds, the screen resets and is ready for the next student

Outside of helpdesk hours, the kiosk automatically shows a "Closed" screen with the hours of operation. It switches back to the check-in screen when the helpdesk opens — no manual intervention needed.

## Project Structure

```
StX-IT-Kiosk/
├── app.py                      # Main application — all backend logic
├── .env.template               # Template for credentials (copy to .env)
├── .env                        # Actual credentials (NOT in repo, kiosk PC only)
├── requirements.txt            # Python dependencies
├── static/
│   ├── styles.css              # All styling — colors, sizes, animations
│   └── st_xavier_logo.png      # School/IT logo (white on transparent)
├── templates/
│   ├── check_in.html           # Main kiosk screen (scan + success + error views)
│   └── closed.html             # Shown outside helpdesk hours
└── .github/
    └── workflows/
        └── build-exe.yml       # GitHub Actions — auto-builds the Windows exe
```

## Configuration

All configuration is done via the `.env` file. The app will not start without the required credentials.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SMTP_SERVER` | SMTP server for sending emails | smtp.office365.com | |
| `SMTP_PORT` | SMTP port | 587 | |
| `SMTP_USER` | SMTP login username | — | Yes |
| `SMTP_PASSWORD` | SMTP login password | — | Yes |
| `FRESHDESK_EMAIL` | Email that auto-creates Freshdesk tickets | helpdesk@stxavier.org | |
| `DB_SERVER` | PostgreSQL database server | your-db-host.your-school.org | |
| `DB_DATABASE` | Database name | your_database | |
| `DB_USERNAME` | Database login username | — | Yes |
| `DB_PASSWORD` | Database login password | — | Yes |
| `DB_DRIVER` | ODBC driver name | {PostgreSQL Unicode(x64)} | |
| `OPEN_HOUR` | Hour helpdesk opens (24h format) | 7 | |
| `CLOSE_HOUR` | Hour helpdesk closes (24h format) | 16 | |
| `OPEN_DAYS` | Days open (0=Mon, 1=Tue, ..., 4=Fri) | 0,1,2,3,4 | |

### Helpdesk Schedule

`OPEN_HOUR`, `CLOSE_HOUR`, and `OPEN_DAYS` control two things at once: when the kiosk accepts check-ins, and the hours printed on the Closed screen. Change them in `.env` and you're done — the Closed screen text is generated from those same values, so there is no second copy to keep in sync.

Hours are 24-hour numbers and get formatted for display automatically (`7` becomes "7:00 AM", `16` becomes "4:00 PM"). The helpdesk opens at the top of `OPEN_HOUR` and closes at the top of `CLOSE_HOUR`, so with the defaults the last minute open is 3:59 PM.

Days are numbered 0=Monday through 6=Sunday, and consecutive days are collapsed into a range:

| `OPEN_DAYS` | Closed screen shows |
|-------------|---------------------|
| `0,1,2,3,4` | Monday – Friday |
| `0,1` | Monday & Tuesday |
| `0,2,4` | Monday, Wednesday, Friday |
| `0,1,2,4` | Monday – Wednesday, Friday |

The formatting is done by `format_hour()` and `format_open_days()` in `app.py`. The `closed.html` template just displays what it's handed, so schedule changes never require touching the HTML.

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

## Building a New Release

This project uses GitHub Actions to automatically build the Windows exe. The process is:

1. Make your code changes and commit them:
   ```
   git add .
   git commit -m "Description of changes"
   git push origin main
   ```
2. When you're ready to release, create a version tag and push it:
   ```
   git tag v2.4
   git push origin v2.4
   ```
3. The GitHub Actions workflow automatically:
   - Sets up a Windows environment with Python 3.10
   - Installs all dependencies
   - Builds the exe with PyInstaller
   - Creates a GitHub Release with the exe and .env.template attached
4. On the kiosk PC, download the new exe from the Releases page and replace the old one

**Key distinction:** Pushing code (`git push`) does NOT trigger a build. Only pushing a version tag (`git push origin v2.x`) triggers the build. You can push as many commits as you want and only build when you're ready.

## Making Changes

This app is simple by design — all the logic is in a handful of well-commented files. Here's where to look for common changes:

| What you want to change | Where to look |
|--------------------------|---------------|
| Colors, fonts, sizes | `static/styles.css` — see the top comment block for key values |
| Logo | Replace `static/st_xavier_logo.png` (use a dark image on transparent background) |
| Screen text or layout | `templates/check_in.html` or `templates/closed.html` |
| Helpdesk hours/schedule | `.env` file on the kiosk PC (OPEN_HOUR, CLOSE_HOUR, OPEN_DAYS) — the Closed screen text follows automatically; see [Helpdesk Schedule](#helpdesk-schedule) |
| Email/ticket behavior | `app.py` — look at the `send_email()` and `process_rfid()` functions |
| Database query | `app.py` — look at `get_user_info_from_cardnumber()` |
| Success screen duration | `templates/check_in.html` — search for `setTimeout` (currently 7000ms) |

### Using AI-Assisted Coding Tools

The easiest way to make changes to this project is to use an AI-assisted coding tool. These tools can read the entire codebase, understand how everything connects, and help you make changes confidently — even if you're not a developer.

**Recommended approach:**
1. Clone or download this repository to your computer
2. Open it in one of these tools:
   - [Claude Code](https://claude.ai/claude-code) by Anthropic (CLI or IDE extension) — point it at the project folder and describe what you want to change
   - [GitHub Copilot](https://github.com/features/copilot) — works inside VS Code
   - [Cursor](https://cursor.com) — an AI-first code editor
3. Describe what you want to change in plain English (e.g., "change the helpdesk hours to 8 AM - 3 PM" or "make the logo bigger")
4. Review the suggested changes, test locally, then commit and push

Every file in this project is thoroughly commented to help both humans and AI tools understand what each piece does and why.

## Development Setup (Running Locally)

If you want to run the app on your own machine for testing:

### Prerequisites

- Python 3.9+ installed
- PostgreSQL ODBC driver installed:
  - **Windows:** `PostgreSQL Unicode(x64)` — download from [postgresql.org](https://www.postgresql.org/ftp/odbc/versions/)
  - **macOS (Homebrew):** `brew install unixodbc psqlodbc`
- Chrome browser installed
- Network access to the school database server (must be on the correct VLAN)

### Steps

1. Clone the repository:
   ```
   git clone https://github.com/GitIdol/StX-IT-Kiosk.git
   cd StX-IT-Kiosk
   ```
2. Copy `.env.template` to `.env` and fill in credentials:
   ```
   cp .env.template .env
   ```
3. On macOS, change the DB driver in `.env`:
   ```
   DB_DRIVER={PostgreSQL Unicode}
   ```
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Run the app:
   ```
   python app.py
   ```
6. Open http://localhost:5000 in a browser (or Chrome will open automatically in kiosk mode)

**Note:** Port 5000 may be used by AirPlay on macOS. If so, either disable AirPlay Receiver in System Settings, or modify the port in `app.py`.

## Troubleshooting

**App won't start — "SMTP credentials not configured":**
The `.env` file is missing or doesn't have `SMTP_USER` and `SMTP_PASSWORD` filled in. See the Configuration section above.

**App won't start — "Database credentials not configured":**
Same as above, but for `DB_USERNAME` and `DB_PASSWORD`.

**App crashes or freezes:**
Reboot the PC. The app is configured to auto-restart on boot. Check `kiosk.log` for error details.

**Badge not recognized:**
The student's card may not be in the database, or there may be a database connection issue. Check `kiosk.log` for details.

**Email not sending:**
Check SMTP credentials in `.env`. Verify the Office 365 account is active and the password hasn't expired.

**Page shows "Closed" during business hours:**
Check that `OPEN_HOUR`, `CLOSE_HOUR`, and `OPEN_DAYS` are set correctly in the `.env` file. Remember: hours are in 24-hour format, and days use 0=Monday through 6=Sunday.

## License

Internal use only — St. Xavier High School IT Department
