"""Carteira de Vacinação do paciente (Fase 2).

Cruza os calendários PNI (Therapy Plan Templates is_pni=1) com as aplicações
reais do paciente (Drug Prescription via Patient Encounter) e calcula o status
de cada dose esperada.

A lógica de status é o coração da carteira; a renderização visual (página Vue
rica) fica para a Fase 9. Esta API já é consumível por Query Report, página
custom ou disparos WhatsApp (Fase 7/8).
"""

from __future__ import annotations

import frappe
from frappe.utils import date_diff, getdate, nowdate

# Tolerância antes de considerar uma dose "atrasada" (dias após a idade ideal).
ATRASO_TOLERANCIA_DIAS = 30

STATUS_APLICADA = "Aplicada"
STATUS_PENDENTE = "Pendente"
STATUS_ATRASADA = "Atrasada"
STATUS_FUTURA = "Futura"


@frappe.whitelist()
def get_vaccine_card(patient: str) -> dict:
	"""Retorna a carteira de vacinação estruturada de um paciente.

	Estrutura de retorno::

	    {
	        "patient": "HLC-PAT-0001",
	        "patient_name": "Maria",
	        "idade_meses": 7,
	        "doses": [
	            {
	                "calendario": "Calendário PNI 0-1 ano",
	                "vacina": "Hepatite B",
	                "dose_numero": 1,
	                "idade_meses_ideal": 0,
	                "status": "Aplicada",
	                "data_aplicacao": "2026-01-10",
	                "lote": "ABC123",
	            },
	            ...
	        ],
	        "resumo": {"Aplicada": 3, "Pendente": 1, "Atrasada": 1, "Futura": 2},
	    }
	"""
	patient_doc = frappe.get_doc("Patient", patient)
	idade_meses = _idade_em_meses(patient_doc.get("dob"))
	aplicadas = _aplicacoes_do_paciente(patient)

	doses = []
	resumo = {STATUS_APLICADA: 0, STATUS_PENDENTE: 0, STATUS_ATRASADA: 0, STATUS_FUTURA: 0}

	for linha in _calendario_pni():
		chave = (linha["medication"], linha["dose_numero"])
		aplicacao = aplicadas.get(chave)
		status = _status_dose(
			aplicada=bool(aplicacao),
			idade_meses=idade_meses,
			idade_meses_ideal=linha["idade_meses_ideal"],
		)
		resumo[status] += 1
		doses.append(
			{
				"calendario": linha["calendario"],
				"vacina": linha["medication"],
				"dose_numero": linha["dose_numero"],
				"idade_meses_ideal": linha["idade_meses_ideal"],
				"status": status,
				"data_aplicacao": aplicacao.get("encounter_date") if aplicacao else None,
				"lote": aplicacao.get("lote") if aplicacao else None,
			}
		)

	return {
		"patient": patient,
		"patient_name": patient_doc.get("patient_name"),
		"idade_meses": idade_meses,
		"doses": doses,
		"resumo": resumo,
	}


def _idade_em_meses(dob) -> int | None:
	if not dob:
		return None
	dias = date_diff(nowdate(), getdate(dob))
	if dias < 0:
		return None
	return dias // 30


def _calendario_pni() -> list[dict]:
	"""Linhas de todos os Therapy Plan Templates marcados como PNI.

	Cada linha tem o calendário de origem, a vacina (medication), o número da
	dose e a idade ideal. Ordenado por idade ideal para leitura cronológica.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			tpt.plan_name AS calendario,
			d.medication AS medication,
			d.dose_numero AS dose_numero,
			d.idade_meses_ideal AS idade_meses_ideal
		FROM `tabTherapy Plan Template Detail` d
		JOIN `tabTherapy Plan Template` tpt ON d.parent = tpt.name
		WHERE tpt.is_pni = 1 AND d.medication IS NOT NULL
		ORDER BY d.idade_meses_ideal, d.medication, d.dose_numero
		""",
		as_dict=True,
	)
	return rows


def _aplicacoes_do_paciente(patient: str) -> dict[tuple, dict]:
	"""Mapa (medication, dose_numero) → dados da aplicação mais recente.

	Aplicações vivem em Drug Prescription (child de Patient Encounter). Filtra
	pelo paciente do encounter e considera apenas linhas com medication setado.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			dp.medication AS medication,
			dp.dose_numero AS dose_numero,
			dp.lote AS lote,
			pe.encounter_date AS encounter_date
		FROM `tabDrug Prescription` dp
		JOIN `tabPatient Encounter` pe ON dp.parent = pe.name
		WHERE pe.patient = %(patient)s
			AND pe.docstatus < 2
			AND dp.medication IS NOT NULL
		ORDER BY pe.encounter_date
		""",
		{"patient": patient},
		as_dict=True,
	)
	aplicadas: dict[tuple, dict] = {}
	for row in rows:
		# dose_numero pode vir None em aplicação avulsa; trata como dose 1.
		chave = (row["medication"], row.get("dose_numero") or 1)
		aplicadas[chave] = row
	return aplicadas


def _status_dose(*, aplicada: bool, idade_meses: int | None, idade_meses_ideal: int | None) -> str:
	if aplicada:
		return STATUS_APLICADA
	if idade_meses is None or idade_meses_ideal is None:
		return STATUS_PENDENTE
	if idade_meses < idade_meses_ideal:
		return STATUS_FUTURA
	# Já passou da idade ideal e não foi aplicada.
	dias_de_atraso = (idade_meses - idade_meses_ideal) * 30
	if dias_de_atraso > ATRASO_TOLERANCIA_DIAS:
		return STATUS_ATRASADA
	return STATUS_PENDENTE
