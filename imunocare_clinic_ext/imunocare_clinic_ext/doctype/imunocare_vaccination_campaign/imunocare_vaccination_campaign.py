"""Controller da Campanha de Vacinação Corporativa (Fase 12, ver ADR-0002).

Mantém os totais sincronizados. A lógica pesada (importar lista, gerar Sales
Order/Sales Invoice) fica em ``imunocare_clinic_ext.api.campaign`` — chamada
pelos botões do form (Client Script no DB, sem build de assets).
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ImunocareVaccinationCampaign(Document):
	def validate(self):
		self.total_colaboradores = len(self.colaboradores or [])
		self._calcular_valor_estimado()

	def _calcular_valor_estimado(self):
		"""Estimativa = Σ (doses ofertadas × nº colaboradores × preço da dose).

		Preço vem do ``Item Price`` da ``price_list`` da campanha (reuso nativo).
		Vacina sem preço cadastrado entra como 0 (operador ajusta no orçamento).
		"""
		n = self.total_colaboradores or 0
		total = 0.0
		for v in self.vacinas_ofertadas or []:
			preco = _preco_da_vacina(v.medication, self.price_list)
			total += preco * (v.doses_por_colaborador or 0) * n
		self.valor_estimado = total


def _preco_da_vacina(medication: str | None, price_list: str | None) -> float:
	"""Preço unitário da dose: Item Price (price_list) do Item vinculado à vacina."""
	if not medication or not price_list:
		return 0.0
	item_code = frappe.db.get_value(
		"Medication Linked Item",
		{"parent": medication, "parenttype": "Medication"},
		"item_code",
	)
	if not item_code:
		return 0.0
	rate = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list, "selling": 1},
		"price_list_rate",
	)
	return float(rate or 0)
