"""
build_dashboard_attachment.py
------------------------------
Bouwt de VOLLEDIGE interactieve HTML-dashboard-tool (met tabbladen,
zoekfilters, dropdowns, CSV-export-knoppen) als één zelfstandig
HTML-bestand, door de bestaande shell-onderdelen en databronnen
samen te voegen. Dit is exact dezelfde tool als het eerder
afgeleverde artifact / power_environment_management_tool_LIVE_DEMO.html.

Wordt gebruikt door send_report_email.py om als e-mailbijlage mee
te sturen (in plaats van alleen een statische samenvatting in de
mail-body).
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _read(path):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return f.read()


def _read_json(path):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return json.load(f)


def build_dashboard_html():
    """Retourneert de volledige, doorklikbare dashboard-HTML als string."""
    merged = _read_json("merged_resources_live.json")
    ocp = _read_json("ocp_environments.json")
    lpar = _read_json("lpar_servers.json")
    actions = _read_json("action_items_live.json")

    data_json = json.dumps(merged, ensure_ascii=False)
    ocp_json = json.dumps(ocp, ensure_ascii=False)
    lpar_json = json.dumps(lpar, ensure_ascii=False)
    actions_json = json.dumps(actions, ensure_ascii=False)

    part1 = _read("shell_part1.html")  # <head> + <style> + start <body>
    part2 = _read("shell_part2.html")  # tab-navigatie + tabel-structuur HTML
    part3 = _read("shell_part3.html")  # <script> met rendering/filter-logica + </body></html>

    # part3 bevat de placeholder-regel "/* DATA_PLACEHOLDER */" die we
    # vervangen door de echte globale variabelen die het script verwacht:
    # RESOURCES, OCP_CLUSTERS, LPAR_SERVERS, ACTIONS.
    data_block = (
        f"const RESOURCES = {data_json};\n"
        f"const OCP_CLUSTERS = {ocp_json};\n"
        f"const LPAR_SERVERS = {lpar_json};\n"
        f"const ACTIONS = {actions_json};\n"
    )
    part3 = part3.replace("/* DATA_PLACEHOLDER */", data_block, 1)

    return part1 + part2 + part3


def write_dashboard_html(output_path):
    html = build_dashboard_html()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path, len(html)


if __name__ == "__main__":
    out_path, size = write_dashboard_html(os.path.join(BASE_DIR, "dashboard_attachment_preview.html"))
    print(f"Dashboard-HTML opgebouwd: {size} bytes -> {out_path}")
