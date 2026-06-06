"""Resolução dos Items vinculados a uma Medication (vacina).

Modelo de catálogo (decisão 2026-06-06): cada vacina tem DOIS Items —
- **insumo** (estocável, com lote, NÃO vendável): entra por NF-e/Purchase
  Receipt e sai por Material Issue na aplicação;
- **serviço** (não estocável, vendável, criado pelo Therapy Type): é a linha
  da Sales Invoice → NFS-e 040301 (preço cheio, insumo embutido).

Ambos podem constar em ``Medication.linked_items``. Estes helpers escolhem a
linha certa pelo ``is_stock_item`` do Item, com fallback para a primeira
linha (compatível com Medications de linha única, como o seed de testes).
"""

from __future__ import annotations

import frappe


def _linked_item_codes(medication: str) -> list[str]:
	return frappe.get_all(
		"Medication Linked Item",
		filters={"parent": medication, "parenttype": "Medication"},
		pluck="item_code",
		order_by="idx",
	)


def item_de_estoque(medication: str) -> str | None:
	"""Item INSUMO (estocável) da vacina — alvo da baixa de estoque."""
	codes = _linked_item_codes(medication)
	for code in codes:
		if frappe.db.get_value("Item", code, "is_stock_item"):
			return code
	return codes[0] if codes else None


def item_de_cobranca(medication: str) -> str | None:
	"""Item de SERVIÇO (não estocável) da vacina — linha da fatura/campanha."""
	codes = _linked_item_codes(medication)
	for code in codes:
		if not frappe.db.get_value("Item", code, "is_stock_item"):
			return code
	return codes[0] if codes else None
