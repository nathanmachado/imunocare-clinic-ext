"""Funções de instalação e integração com o workspace do Frappe Healthcare."""

import json
import os
import frappe


# ------------------------------------------------------------------
# Carga dos protocolos PNI
# ------------------------------------------------------------------

def load_pni_protocols() -> None:
    """Carrega protocolos PNI do fixture JSON no banco de dados."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "protocolo_de_imunizacao.json"
    )
    with open(fixture_path) as f:
        protocolos = json.load(f)

    for p in protocolos:
        nome = p["vacina_nome"]
        if frappe.db.exists("Protocolo de Imunizacao", nome):
            continue
        doc = frappe.get_doc(p)
        doc.insert(ignore_permissions=True)

    frappe.db.commit()


# ------------------------------------------------------------------
# Integração com o Workspace do Healthcare
# ------------------------------------------------------------------

_SHORTCUTS = [
    {"type": "DocType", "link_to": "Aplicacao de Vacina",      "label": "Aplicação de Vacina",       "color": "#2ecc71"},
    {"type": "DocType", "link_to": "Retorno Programado",        "label": "Retorno Programado",         "color": "#3498db"},
    {"type": "DocType", "link_to": "Protocolo de Imunizacao",   "label": "Protocolo de Imunização",    "color": "#9b59b6"},
]

_LINKS_VACINACAO = [
    # --- Card Break ---
    {"type": "Card Break", "label": "Vacinação", "is_query_report": 0},
    {"type": "Link", "link_type": "DocType", "link_to": "Aplicacao de Vacina",    "label": "Aplicação de Vacina",    "onboard": 1},
    {"type": "Link", "link_type": "DocType", "link_to": "Retorno Programado",      "label": "Retorno Programado",     "onboard": 1},
    # --- Card Break ---
    {"type": "Card Break", "label": "Configuração de Vacinação", "is_query_report": 0},
    {"type": "Link", "link_type": "DocType", "link_to": "Protocolo de Imunizacao", "label": "Protocolo de Imunização", "onboard": 1},
]


def integrate_healthcare_workspace() -> None:
    """
    Adiciona shortcuts e seção Vacinação ao Workspace do Healthcare.
    Idempotente: não duplica entradas já existentes.
    """
    if not frappe.db.exists("Workspace", "Healthcare"):
        frappe.log_error("Workspace Healthcare não encontrado.", "imunocare_clinic_ext")
        return

    ws = frappe.get_doc("Workspace", "Healthcare")

    # --- Shortcuts ---
    links_existentes = {s.link_to for s in ws.shortcuts}
    for shortcut in _SHORTCUTS:
        if shortcut["link_to"] not in links_existentes:
            ws.append("shortcuts", shortcut)

    # --- Seção de links ---
    labels_existentes = {l.label for l in ws.links if l.type == "Card Break"}
    if "Vacinação" not in labels_existentes:
        for link in _LINKS_VACINACAO:
            ws.append("links", link)

    ws.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache(doctype="Workspace")
