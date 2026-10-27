#!/usr/bin/env python3
"""
send_report_email.py
---------------------
Leest het resource-overzicht (merged_resources_live.json) en stuurt een
leesbaar HTML-rapport per e-mail via een gewone SMTP-server (Gmail,
IBM Mail/Outlook, SendGrid, etc.) - GEEN IBM Cloud API-sleutel nodig.

De HTML-opmaak volgt dezelfde IBM Carbon-huisstijl als het
Power VS resource dashboard (donkere header, IBM-blauw #0f62fe,
kaartjes met gekleurde linkerrand, Carbon-badges/chips).

BELANGRIJK - VEILIGHEID:
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

# ---- IBM Carbon kleuren - exact gelijk aan het dashboard --------------------
IBM_BLUE = "#0f62fe"
IBM_DARK = "#161616"
IBM_GRAY_10 = "#f4f4f4"
IBM_GRAY_20 = "#e0e0e0"
IBM_GRAY_70 = "#525252"
GREEN = "#198038"
GREEN_BG = "#defbe6"
RED = "#da1e28"
RED_BG = "#fff1f1"

WARNING_STATUSES = {"warning", "stopped", "failed", "error"}


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


def count_warnings(data):
    return sum(
        count for status, count in data["by_status"].items()
        if status.strip().lower() in WARNING_STATUSES
    )


def top_types(data, limit=5):
    items = sorted(data["by_type"].items(), key=lambda kv: -kv[1])
    shown = items[:limit]
    rest = items[limit:]
    rest_total = sum(c for _, c in rest)
    return shown, rest_total, len(rest)


def sorted_env_names(by_env):
    return sorted(by_env.keys(), key=lambda k: (k == "Unclassified", k))


def kpi_card(value, label, color=IBM_BLUE):
    return f"""
    <td style="width:25%; padding:16px 20px; background:#ffffff; border-left:4px solid {color};">
      <div style="font-size:28px; font-weight:600; line-height:1.1; color:{color};">{value}</div>
      <div style="font-size:12px; color:{IBM_GRAY_70}; text-transform:uppercase; letter-spacing:0.3px; margin-top:4px;">{label}</div>
    </td>
    """


def build_html_report(by_env, total_resources, generated_at):
    total_manual = sum(
        data["by_source"].get("Manual (OpenShift Console / earlier export)", 0)
        for data in by_env.values()
    )
    total_live = total_resources - total_manual
    total_warnings = sum(count_warnings(data) for data in by_env.values())

    # ---- Bovenaan: 4 grote kerncijfers in Carbon-kaartjes ----------------
    summary_cards = f"""
    <table role="presentation" style="width:100%; border-collapse:separate; border-spacing:8px 0; margin:20px 0;">
      <tr>
        {kpi_card(total_resources, "Totaal resources")}
        {kpi_card(len(by_env), "Omgevingen")}
        {kpi_card(total_warnings, "Aandachtspunten", RED if total_warnings else GREEN)}
        {kpi_card(f"{total_live} / {total_manual}", "Live&nbsp;/&nbsp;Handmatig", IBM_DARK)}
      </tr>
    </table>
    """

    # ---- Een kaart per omgeving (Carbon chip- en badge-stijl) ------------
    env_cards = []
    for env in sorted_env_names(by_env):
        data = by_env[env]
        warnings = count_warnings(data)
        shown_types, rest_total, rest_count = top_types(data)

        type_chips = "".join(
            f'<span style="display:inline-block;background:{IBM_GRAY_20};color:{IBM_GRAY_70};'
            f'border-radius:3px;padding:2px 8px;margin:2px;font-size:11px;">'
            f'{t}: {c}</span>'
            for t, c in shown_types
        )
        if rest_count:
            type_chips += (
                f'<span style="display:inline-block;background:{IBM_GRAY_20};color:{IBM_GRAY_70};'
                f'border-radius:3px;padding:2px 8px;margin:2px;font-size:11px;">'
                f'+{rest_count} andere types: {rest_total}</span>'
            )

        manual_n = data["by_source"].get("Manual (OpenShift Console / earlier export)", 0)
        live_n = data["total"] - manual_n

        if warnings:
            warning_badge = (
                f'<span style="display:inline-block;background:{RED_BG};color:{RED};border-radius:10px;'
                f'padding:3px 10px;font-size:12px;font-weight:600;margin-left:8px;">'
                f'{warnings} aandachtspunt(en)</span>'
            )
        else:
            warning_badge = (
                f'<span style="display:inline-block;background:{GREEN_BG};color:{GREEN};border-radius:10px;'
                f'padding:3px 10px;font-size:12px;font-weight:600;margin-left:8px;">Alles gezond</span>'
            )

        source_line = f"Databron: <b>{live_n}</b> live (IBM Cloud API)"
        if manual_n:
            source_line += f", <b>{manual_n}</b> uit eerdere OpenShift Console-export"

        env_cards.append(f"""
        <table role="presentation" style="width:100%; border-collapse:collapse; margin:10px 0;
               border:1px solid {IBM_GRAY_20};">
          <tr>
            <td style="padding:16px 18px; background:#ffffff;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:16px; font-weight:600; color:{IBM_DARK};">{env}</span>
                <span style="font-size:14px; color:{IBM_GRAY_70};">
                  <b>{data['total']}</b> resources {warning_badge}
                </span>
              </div>
              <div style="margin-top:8px; font-size:12px; color:{IBM_GRAY_70};">
                {source_line}
              </div>
              <div style="margin-top:10px;">{type_chips}</div>
            </td>
          </tr>
        </table>
        """)

    html = f"""<!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family:'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                 color:{IBM_DARK}; max-width:780px; margin:0 auto; background:{IBM_GRAY_10}; padding:0;">
        <div style="background:{IBM_DARK}; color:#ffffff; padding:20px 28px;">
          <div style="margin:0 0 4px; font-size:20px; font-weight:600;">IBM Power Systems &mdash; Wekelijks resource-rapport</div>
          <div style="color:#c6c6c6; font-size:13px;">Gegenereerd op {generated_at}</div>
        </div>
        <div style="padding:20px 20px 32px;">
            {summary_cards}

            <div style="font-size:16px; font-weight:600; margin:24px 0 10px; color:{IBM_DARK};">Per omgeving</div>
            {''.join(env_cards)}

            <p style="margin-top:24px;color:{IBM_GRAY_70};font-size:12px; border-top:1px solid {IBM_GRAY_20}; padding-top:12px;">
                Dit rapport is automatisch gegenereerd door het script
                <code>send_report_email.py</code> op basis van <code>merged_resources_live.json</code>
                &mdash; dezelfde data als het Power VS resource dashboard.
                "Live" = rechtstreeks uit de IBM Cloud API. "Handmatig" = overgenomen uit een
                eerdere OpenShift Console-export, nog niet automatisch gekoppeld.
            </p>
        </div>
    </body>
    </html>
    """
    return html


def build_plaintext_report(by_env, total_resources, generated_at):
    """Platte-tekst versie, voor mailclients die geen HTML tonen."""
    total_manual = sum(
        data["by_source"].get("Manual (OpenShift Console / earlier export)", 0)
        for data in by_env.values()
    )
    total_live = total_resources - total_manual
    total_warnings = sum(count_warnings(data) for data in by_env.values())

    lines = [
        "IBM Power Systems - Wekelijks resource-rapport",
        f"Gegenereerd op: {generated_at}",
        "",
        f"Totaal resources : {total_resources}",
        f"Omgevingen       : {len(by_env)}",
        f"Aandachtspunten  : {total_warnings}",
        f"Live / Handmatig : {total_live} / {total_manual}",
        "",
        "Per omgeving:",
    ]
    for env in sorted_env_names(by_env):
        data = by_env[env]
        warnings = count_warnings(data)
        lines.append(f"- {env}: {data['total']} resources ({warnings} aandachtspunt(en))")
        shown_types, rest_total, rest_count = top_types(data)
        type_str = ", ".join(f"{t}: {c}" for t, c in shown_types)
        if rest_count:
            type_str += f", +{rest_count} andere types: {rest_total}"
        lines.append(f"    types: {type_str}")
    return "\n".join(lines)


def send_email(html_body, text_body):
    missing = [
        name for name, val in [
            ("SMTP_SERVER", SMTP_SERVER),
            ("SMTP_USERNAME", SMTP_USERNAME),
            ("SMTP_PASSWORD", SMTP_PASSWORD),
            ("REPORT_RECIPIENT", REPORT_RECIPIENT),
        ] if not val
    ]
    if missing:
        print(f"FOUT: de volgende instellingen ontbreken: {', '.join(missing)}")
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = SMTP_SENDER
    msg["To"] = REPORT_RECIPIENT
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_SENDER, [REPORT_RECIPIENT], msg.as_string())

    print(f"E-mail verstuurd naar {REPORT_RECIPIENT} via {SMTP_SERVER}:{SMTP_PORT}")


def main():
    resources = load_resources(REPORT_JSON_PATH)
    by_env = summarize(resources)
    generated_at = datetime.now().strftime("%d-%m-%Y %H:%M")

    html_body = build_html_report(by_env, len(resources), generated_at)
    text_body = build_plaintext_report(by_env, len(resources), generated_at)

    print(f"Rapport opgebouwd: {len(resources)} resources in {len(by_env)} omgevingen.")

    if DRY_RUN:
        preview_path = os.path.join(
            os.path.dirname(os.path.abspath(REPORT_JSON_PATH)) or ".", "report_preview.html"
        )
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
