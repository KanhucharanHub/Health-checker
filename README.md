# HID Controller Health Checker

![status badge](https://img.shields.io/badge/status-active-brightgreen)

A lightweight Python script that continuously pings HID controller IPs,
logs their status, and emails the operations team if a controller is offline
for more than **5 minutes** (configurable). When a controller recovers, a
recovery email is sent.

---

## 1. Project structure

```text
hid-health-checker/
├── controllers.txt       # List of controller IPs
├── hid_health_checker.py # Main script
└── README.md             # This guide
```

## 2. Prerequisites

- **Python 3.8+** (no third‑party packages needed)
- SMTP credentials for sending email alerts
- Network access to controllers on ICMP (ping) protocol

## 3. Quick start

```powershell
git clone https://example.com/hid-health-checker.git
cd hid-health-checker
python -m venv venv
venv\Scripts\Activate
# No pip install needed (stdlib only)
$env:EMAIL_HOST="smtp.gmail.com"
$env:EMAIL_PORT="465"
$env:EMAIL_USER="your_email@example.com"
$env:EMAIL_PASS="your_password (16 digit)"
$env:EMAIL_TO="drecipient@example.com"
python "d:\System Engineer Projects\hid_health_checker_project\hid_health_checker.py"
```

*Hit **Ctrl+C** to stop.*

## 4. Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--ip-file` | Path to file with IP list | `controllers.txt` |
| `--interval` | Seconds between pings | `30` |
| `--alert-after` | Seconds offline before alert | `300` |
| `--log` | Log file path | `hid_health_checker.log` |

## 5. Running as a systemd service (Ubuntu / Debian)

1. Copy the project to `/opt/hid-health`.
2. Create a **virtual environment** inside.
3. Save the unit file below as
   `/etc/systemd/system/hid-health.service`:

```ini
[Unit]
Description=HID Controller Health Checker
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/hid-health
ExecStart=/opt/hid-health/venv/bin/python hid_health_checker.py -c controllers.txt
Environment=EMAIL_HOST=smtp.example.com
Environment=EMAIL_PORT=465
Environment=EMAIL_USER=alerts@example.com
Environment=EMAIL_PASS=********
Environment=EMAIL_TO=ops-team@example.com
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

4. Enable & start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hid-health
```

Check logs with `sudo journalctl -u hid-health -f`.

## 6. Simulating offline/online events

- Use a non‑existent IP (e.g., `10.255.255.1`) in `controllers.txt`.
- Or block ICMP to a test host with a firewall rule and watch the logs.

## 7. Extending the project

- **Slack / Teams** webhook instead of email (replace `send_email`).
- **Prometheus** exporter endpoint for metrics scraping.
- Store controller metadata in SQLite or PostgreSQL.

## 8. Web Dashboard

- Visit [http://localhost:5000](http://localhost:5000) to see live controller status in your browser.
- Flask (for web dashboard): `pip install flask`

## 9. Historical Reporting

- All status changes are logged in `status_history.db` (SQLite).
- You can analyze this database for uptime reports and history.

---

© 2025 Karan. Licensed under the MIT License.
