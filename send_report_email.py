#!/usr/bin/env python3
"""
send_report_email.py
---------------------
Leest het resource-overzicht (merged_resources_live.json) en stuurt een
leesbaar HTML-rapport per e-mail via een gewone SMTP-server (Gmail,
IBM Mail/Outlook, SendGrid, etc.) — GEEN IBM Cloud API-sleutel nodig.

BELANGRIJK — VEILIGHEID:
Alle instelbare waarden (SMTP-server, poort, afzender, ontvanger,
gebruikersnaam, wachtwoord/app-wachtwoord) komen UITSLUITEND uit
environment variables. Er staat GEEN enkel wachtwoord of e-mailadres
hardcoded in dit bestand.
"""

import json
import os
import smtplib
import ssl
import sys
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SENDER = os.environ.get("SMTP_SENDER", SMTP_USERNAME)
REPORT_RECIPIENT = os.environ.get("REPORT_RECIPIENT", "")
EMAIL_SUBJECT = os.environ.get(
    "EMAIL_SUBJECT", "Wekelijks IBM Power VS resource-rapport"
)

DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "merged_resources_live.json"
)
REPORT_JSON_PATH = os.environ.get("REPORT_JSON_PATH", DEFAULT_JSON_PATH)

DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"


def load_resources(json_path):
    if not os.path.exists(json_path):
        print(f"FOUT: kan het databestand niet vinden: {json_path}")
        sys.exit(1)
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def summarize(resources):
    by_env = defaultdict(lambda: {
        "total": 0,
        "by_status": defaultdict(int),
        "by_type": defaultdict(int),
        "by_source": defaultdict(int),
    })

    for r in resources:
        env = r.get("Environment") or "Unclassified"
        status = r.get("PowerStatus") or r.get("Status") or "Onbekend"
        rtype = r.get("PowerResourceType") or r.get("Type") or "Onbekend type"
        source = r.get("DataSource") or "Onbekend"

        bucket = by_env[env]
        bucket["total"] += 1
        bucket["by_status"][status] += 1
        bucket["by_type"][rtype] += 1
        bucket["by_source"][source] += 1

    return by_env


def build_html_report(by_env, total_resources, generated_at):
    rows = []
    for env in sorted(by_env.keys()):
        data = by_env[env]
        status_str = ", ".join(f"{k}: {v}" for k, v in sorted(data["by_status"].items()))
        type_str = ", ".join(f"{k}: {v}" for k, v in sorted(data["by_type"].items()))
        source_str = ", ".join(f"{k}: {v}" for k, v in sorted(data["by_source"].items()))
        rows.append(
            f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">{env}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;">{data['total']}</td>
                <td style="padding:8px;border:1px solid #ddd;">{status_str}</td>
                <td style="padding:8px;border:1px solid #ddd;">{type_str}</td>
                <td style="padding:8px;border:1px solid #ddd;">{source_str}</td>
            </tr>
            """
        )

    total_manual = sum(
        data["by_source"].get("Manual (OpenShift Console / earlier export)", 0)
        for data in by_env.values()
    )
    total_live = total_resources - total_manual

    html = f"""<!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family:Arial, sans-serif; color:#222;">
        <h2>IBM Power VS &mdash; Wekelijks resource-rapport</h2>
        <p>Gegenereerd op: <b>{generated_at}</b></p>
        <p>Totaal aantal resources (alle omgevingen samen): <b>{total_resources}</b>
           &nbsp;(<b>{total_live}</b> live uit de IBM Cloud API, <b>{total_manual}</b>
           uit de eerdere OpenShift Console-export)</p>
        <table style="border-collapse:collapse; width:100%; margin-top:10px;">
            <thead>
                <tr style="background:#f0f0f0;">
                    <th style="padding:8px;border:1px solid #ddd;text-align:left;">Omgeving</th>
                    <th style="padding:8px;border:1px solid #ddd;">Aantal resources</th>
                    <th style="padding:8px;border:1px solid #ddd;text-align:left;">Status-verdeling</th>
                    <th style="padding:8px;border:1px solid #ddd;text-align:left;">Type-verdeling</th>
                    <th style="padding:8px;border:1px solid #ddd;text-align:left;">Databron (Live/Manual)</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        <p style="margin-top:20px;color:#888;font-size:12px;">
            Dit rapport is automatisch gegenereerd door het script
            send_report_email.py op basis van merged_resources_live.json.
        </p>
    </body>
    </html>
    """
    return html


def build_plaintext_report(by_env, total_resources, generated_at):
    lines = [
        "IBM Power VS - Wekelijks resource-rapport",
        f"Gegenereerd op: {generated_at}",
        f"Totaal aantal resources: {total_resources}",
        "",
    ]
    for env in sorted(by_env.keys()):
        data = by_env[env]
        lines.append(f"- {env}: {data['total']} resources")
        for status, count in sorted(data["by_status"].items()):
            lines.append(f"    status {status}: {count}")
        for source, count in sorted(data["by_source"].items()):
            lines.append(f"    databron {source}: {count}")
    return "\n".join(lines)


def send_email(html_body, text_body):
    missing = [
        name
        for name, val in [
            ("SMTP_SERVER", SMTP_SERVER),
            ("SMTP_USERNAME", SMTP_USERNAME),
            ("SMTP_PASSWORD", SMTP_PASSWORD),
            ("SMTP_SENDER", SMTP_SENDER),
            ("REPORT_RECIPIENT", REPORT_RECIPIENT),
        ]
        if not val
    ]
    if missing:
        print(
            "FOUT: de volgende verplichte environment variables ontbreken: "
            + ", ".join(missing)
        )
        print(
            "Zet deze eerst (zie de stap-voor-stap gids) en start het script opnieuw."
        )
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = SMTP_SENDER
    msg["To"] = REPORT_RECIPIENT

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_SENDER, [REPORT_RECIPIENT], msg.as_string())

    print(f"E-mail verstuurd naar {REPORT_RECIPIENT} via {SMTP_SERVER}:{SMTP_PORT}")


def main():
    resources = load_resources(REPORT_JSON_PATH)
    by_env = summarize(resources)
    total_resources = len(resources)
    generated_at = datetime.now().strftime("%d-%m-%Y %H:%M")

    html_body = build_html_report(by_env, total_resources, generated_at)
    text_body = build_plaintext_report(by_env, total_resources, generated_at)

    print(f"Rapport opgebouwd: {total_resources} resources in {len(by_env)} omgevingen.")

    if DRY_RUN:
        preview_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_preview.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html_body)
        print("DRY_RUN staat aan: er is GEEN e-mail verstuurd.")
        print(f"Een voorbeeld van het rapport is opgeslagen als: {preview_path}")
        print("\n--- Platte-tekst voorbeeld ---")
        print(text_body)
        return

    send_email(html_body, text_body)


if __name__ == "__main__":
    main()
