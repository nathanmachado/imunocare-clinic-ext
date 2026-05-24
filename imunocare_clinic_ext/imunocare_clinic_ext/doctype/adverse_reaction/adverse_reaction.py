"""Adverse Reaction (ESAVI) — Evento Supostamente Atribuível à Vacinação/Imunização.

Registra reações adversas a aplicações (Fase 3 / ADR-0001). Sem equivalente no
Healthcare upstream — semântica própria (gravidade, desfecho, notificação ANVISA).
Aparece na timeline do paciente via Patient History Settings.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AdverseReaction(Document):
	def validate(self):
		self._warn_if_serious_not_notified()

	def _warn_if_serious_not_notified(self):
		"""Eventos graves são de notificação compulsória à ANVISA (VigiMed).

		Não bloqueia o registro (a reação precisa ser documentada de imediato),
		mas alerta o operador quando uma reação Grave ainda não foi notificada.
		"""
		if self.gravidade == "Grave" and not self.notificada_anvisa:
			frappe.msgprint(
				_(
					"Reação <b>Grave</b>: a notificação à ANVISA (VigiMed) é "
					"compulsória. Marque 'Notificada à ANVISA' assim que registrar."
				),
				title=_("Notificação compulsória"),
				indicator="orange",
			)
