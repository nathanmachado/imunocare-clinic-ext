"""Hooks de Medication (catálogo de vacinas).

Neutraliza um comportamento nativo do Healthcare: ``Medication.on_update``
(medication.py) desabilita (``disabled=1``) toda linha de ``linked_items`` que
não seja ``is_billable`` — partindo da premissa de que "todo item vinculado a
um Medication é um remédio faturável".

No nosso modelo insumo/serviço essa premissa não vale: o INSUMO é
deliberadamente NÃO-faturável (a cobrança é do item de serviço), então a cada
save do Medication o insumo era desativado — sumindo do De-Para da NF-e e
travando entrada/baixa de estoque (item ``disabled`` não transaciona).

Este hook roda DEPOIS do ``on_update`` nativo (em Frappe, os handlers de
``doc_events`` são compostos após o método do controller — ver
``Document.hook``/``compose``) e reabilita qualquer linha vinculada que seja
item de estoque. Usa ``db.set_value`` (não ``doc.save``) para não re-disparar o
``on_update`` e evitar recursão.

NÃO marcar o insumo como ``is_billable`` para "resolver": isso faria o Encounter
cobrar o insumo (cobrança dupla) e criar Item Price para ele. O insumo precisa
seguir não-faturável; só não pode ser desativado.
"""

from __future__ import annotations

import frappe


def on_update(doc, method=None) -> None:
	reativar_insumos(doc)


def reativar_insumos(doc) -> None:
	"""Reabilita linhas de ``linked_items`` que sejam itens de estoque (insumos)."""
	for row in doc.get("linked_items") or []:
		item_code = row.get("item") or row.get("item_code")
		if not item_code:
			continue
		dados = frappe.db.get_value(
			"Item", item_code, ["is_stock_item", "disabled"], as_dict=True
		)
		if dados and dados.is_stock_item and dados.disabled:
			frappe.db.set_value("Item", item_code, "disabled", 0)
