#!/usr/bin/env python3
"""HID Controller Health Checker

Continuously pings a list of controller IP addresses and logs whether they are
online or offline. Sends an email alert if any controller remains offline for
longer than a specified threshold (default 5 minutes). A recovery email is sent
when the controller comes back online.

Usage:
    python hid_health_checker.py -c controllers.txt -i 30 -t 300

Environment variables required for email:
    EMAIL_HOST : SMTP server host
    EMAIL_PORT : SMTP server port (465 for SSL)
    EMAIL_USER : SMTP username / from-address
    EMAIL_PASS : SMTP password
    EMAIL_TO   : Comma‑separated list of recipients

Author: Kanhu Charan
"""
import argparse
import datetime
import logging
import os
import platform
import subprocess
import sys
import time
import ssl
import smtplib
from flask import Flask, render_template_string
import threading
import sqlite3


def ping(host: str) -> bool:
    """Return True if host responds to a single ping packet."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    cmd = ["ping", param, "1", host]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def send_email(subject: str, body: str, cfg: dict) -> None:
    """Send an email using the supplied SMTP configuration."""
    message = f"Subject: {subject}\n\n{body}"
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(cfg["EMAIL_HOST"], cfg["EMAIL_PORT"], context=context) as server:
        server.login(cfg["EMAIL_USER"], cfg["EMAIL_PASS"])
        server.sendmail(cfg["EMAIL_USER"], cfg["EMAIL_TO"].split(","), message)


def load_ips(path: str) -> list[str]:
    """Read IP addresses from a file, ignoring comments and blank lines."""
    with open(path, "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]


def get_email_cfg() -> dict:
    """Fetch SMTP settings from environment variables."""
    keys = ["EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", "EMAIL_PASS", "EMAIL_TO"]
    cfg = {k: os.getenv(k) for k in keys}
    if None in cfg.values():
        missing = ", ".join(k for k, v in cfg.items() if v is None)
        raise EnvironmentError(f"Missing environment variables: {missing}")
    cfg["EMAIL_PORT"] = int(cfg["EMAIL_PORT"])
    return cfg


# Global status dict for web dashboard
controller_status = {}

# HTML template for dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>HID Controller Status</title>
    <style>
        table { border-collapse: collapse; }
        th, td { border: 1px solid #ccc; padding: 8px; }
        .online { color: green; }
        .offline { color: red; }
    </style>
</head>
<body>
    <h2>HID Controller Status</h2>
    <table>
        <tr><th>IP Address</th><th>Status</th><th>Last Change (UTC)</th></tr>
        {% for ip, info in status.items() %}
        <tr>
            <td>{{ ip }}</td>
            <td class="{{ 'online' if info['online'] else 'offline' }}">
                {{ 'ONLINE' if info['online'] else 'OFFLINE' }}
            </td>
            <td>{{ info['changed'] }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""


def run_dashboard():
    app = Flask(__name__)

    @app.route("/")
    def dashboard():
        return render_template_string(DASHBOARD_HTML, status=controller_status)

    app.run(port=5000, debug=False, use_reloader=False)


# Start dashboard in a background thread
def start_dashboard():
    t = threading.Thread(target=run_dashboard, daemon=True)
    t.start()


def init_db(db_path="status_history.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            status TEXT,
            changed TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def log_status_change(ip, status, changed, db_path="status_history.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "INSERT INTO status_history (ip, status, changed) VALUES (?, ?, ?)",
        (ip, status, changed)
    )
    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="HID Controller Health Checker")
    parser.add_argument(
        "-c",
        "--ip-file",
        default="controllers.txt",
        help="Path to text file containing IP addresses one per line.",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=30,
        help="Ping interval in seconds (default: 30)",
    )
    parser.add_argument(
        "-t",
        "--alert-after",
        type=int,
        default=300,
        help="Seconds a controller must be offline before alert (default: 300 = 5 min)",
    )
    parser.add_argument(
        "-l",
        "--log",
        default="hid_health_checker.log",
        help="Log file path (default: hid_health_checker.log)",
    )
    args = parser.parse_args()
    init_db()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(args.log), logging.StreamHandler(sys.stdout)],
    )

    ips = load_ips(args.ip_file)
    if not ips:
        logging.error("No IP addresses found – exiting.")
        sys.exit(1)

    email_cfg = get_email_cfg()

    status = {
        ip: {"online": None, "changed": datetime.datetime.now(datetime.UTC), "alerted": False}
        for ip in ips
    }

    logging.info(
        "Monitoring %d controllers every %d s; alert after %d s offline.",
        len(ips),
        args.interval,
        args.alert_after,
    )

    # Initialize the database
    init_db()

    # Start the dashboard
    start_dashboard()

    try:
        while True:
            for ip in ips:
                online = ping(ip)
                s = status[ip]

                # First observation
                if s["online"] is None:
                    s["online"] = online
                    s["changed"] = datetime.datetime.utcnow()

                # State change
                elif online != s["online"]:
                    s["online"] = online
                    s["changed"] = datetime.datetime.now(datetime.UTC)
                    s["alerted"] = False
                    state = "ONLINE" if online else "OFFLINE"
                    logging.warning("%s changed state to %s", ip, state)
                    controller_status[ip] = dict(s)
                    log_status_change(ip, state, s["changed"].isoformat())

                # Update the global status for the dashboard
                controller_status[ip] = s

                # Log the status change to the database
                log_status_change(ip, "ONLINE" if online else "OFFLINE", s["changed"])

                # Handle alerts
                if not online:
                    offline_seconds = (datetime.datetime.utcnow() - s["changed"]).total_seconds()
                    if offline_seconds >= args.alert_after and not s["alerted"]:
                        subj = f"[ALERT] Controller {ip} offline"
                        body = (
                            f"Controller {ip} has been unreachable for {int(offline_seconds)} seconds."
                        )
                        try:
                            send_email(subj, body, email_cfg)
                            logging.error("Alert email sent for %s", ip)
                            s["alerted"] = True
                        except Exception as exc:
                            logging.error("Failed to send alert email: %s", exc)
                else:
                    # Send recovery if previously alerted
                    if s["alerted"]:
                        subj = f"[RECOVERED] Controller {ip} back online"
                        body = f"Controller {ip} is reachable again at {datetime.datetime.utcnow():%Y-%m-%d %H:%M:%S UTC}."
                        try:
                            send_email(subj, body, email_cfg)
                            logging.info("Recovery email sent for %s", ip)
                        except Exception as exc:
                            logging.error("Failed to send recovery email: %s", exc)
                        s["alerted"] = False

            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info("Received CTRL+C – exiting.")
    except Exception as exc:
        logging.exception("Unhandled exception: %s", exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
