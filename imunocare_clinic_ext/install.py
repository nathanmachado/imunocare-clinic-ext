"""Funções de instalação e carga de dados iniciais."""

import json
import os
import frappe


def load_pni_protocols():
    """Carrega protocolos PNI do fixture JSON no banco de dados."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
        "protocolo_de_imunizacao.json",
    )
    with open(fixture_path) as f:
        protocolos = json.load(f)

    for p in protocolos:
        nome = p["vacina_nome"]
        if frappe.db.exists("Protocolo de Imunizacao", nome):
            frappe.msgprint(f"SKIP {nome}")
            continue
        doc = frappe.get_doc(p)
        doc.insert(ignore_permissions=True)
        frappe.msgprint(f"OK {nome}")

    frappe.db.commit()
