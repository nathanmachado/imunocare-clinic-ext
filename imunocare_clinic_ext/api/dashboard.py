"""APIs de apoio ao Dashboard de Imunização (Fase 10).

Reuso máximo do que já existe (ver feedback_reuse_first):
- estoque vem do ``Bin`` nativo (ERPNext Stock) via os ``linked_items`` do
  Medication (Healthcare) — não criamos controle de estoque próprio;
- "pago" é derivado dos campos nativos do Patient Appointment
  (``invoiced`` / ``paid_amount`` / ``ref_sales_invoice``);
- "atrasado" reusa a mesma noção operacional do report Agenda de Imunização.

Estas funções alimentam Number Cards (tipo Custom) e o Script Report, todos
armazenados no banco — sem build de assets.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_last_day, getdate, nowdate

# Abreviações de mês em pt-BR (1-indexado) para os rótulos das colunas da
# projeção de estoque.
_MESES_PT = (
	"", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
	"Jul", "Ago", "Set", "Out", "Nov", "Dez",
)

# Status do Patient Appointment que indicam atendimento já realizado.
STATUS_REALIZADO = ("Closed", "Checked Out")
# Cancelamento explícito: não é atraso (foi deliberadamente cancelado).
STATUS_CANCELADO = ("Cancelled",)
# Estados terminais que NÃO são risco de atraso (realizado ou cancelado).
# Atenção: "No Show" NÃO entra aqui — o Healthcare força todo agendamento
# vencido e não atendido para "No Show" (set_status), então "No Show" + pago
# é justamente o atendimento atrasado que já foi pago e não aconteceu.
STATUS_NAO_RISCO = STATUS_REALIZADO + STATUS_CANCELADO


def _item_codes_da_vacina(medication: str | None) -> list[str]:
	"""Itens estocáveis vinculados a um Medication (Healthcare)."""
	if not medication:
		return []
	codes = frappe.get_all(
		"Medication Linked Item",
		filters={"parent": medication, "parenttype": "Medication"},
		pluck="item_code",
	)
	return [c for c in codes if c]


def posicao_estoque(medication: str | None) -> dict:
	"""Posição de estoque de uma vacina, somada em todos os depósitos.

	Medication (Healthcare) → ``linked_items`` → Item estocável → soma do ``Bin``
	nativo. Retorna ``{"actual": <em estoque>, "ordered": <em pedido de compra>}``.
	Reusa os campos nativos do Bin — nenhum controle de estoque próprio.
	"""
	item_codes = _item_codes_da_vacina(medication)
	if not item_codes:
		return {"actual": 0.0, "ordered": 0.0}
	res = frappe.get_all(
		"Bin",
		filters={"item_code": ("in", item_codes)},
		fields=["sum(actual_qty) as actual", "sum(ordered_qty) as ordered"],
	)
	if not res:
		return {"actual": 0.0, "ordered": 0.0}
	return {"actual": float(res[0].actual or 0), "ordered": float(res[0].ordered or 0)}


def estoque_da_vacina(medication: str | None) -> float:
	"""Soma do estoque atual (Bin.actual_qty) dos itens vinculados a uma vacina."""
	return posicao_estoque(medication)["actual"]


def _vacinas_em_falta_codes() -> list[str]:
	"""Medications marcadas como vacina cujo estoque somado é <= 0."""
	vacinas = frappe.get_all(
		"Medication",
		filters={"is_vaccine": 1, "disabled": 0},
		pluck="name",
	)
	return [v for v in vacinas if estoque_da_vacina(v) <= 0]


@frappe.whitelist()
def vacinas_em_falta() -> int:
	"""Number Card (Custom): nº de vacinas ativas com estoque zerado/negativo."""
	return len(_vacinas_em_falta_codes())


@frappe.whitelist()
def atrasados_pagos() -> int:
	"""Number Card (Custom): agendamentos PAGOS, vencidos e não realizados.

	É o alerta crítico da operação: o paciente pagou pela aplicação mas o
	atendimento ficou para trás (data passada e status ainda em aberto).
	"""
	hoje = nowdate()
	rows = frappe.get_all(
		"Patient Appointment",
		filters={
			"appointment_date": ("<", hoje),
			"status": ("not in", STATUS_NAO_RISCO),
		},
		fields=["name", "invoiced", "paid_amount", "ref_sales_invoice"],
	)
	return sum(1 for r in rows if _is_pago(r))


def _is_pago(row) -> bool:
	"""Pago = faturado, ou com valor recebido, ou com fatura de venda vinculada."""
	return bool(row.get("invoiced") or (row.get("paid_amount") or 0) > 0 or row.get("ref_sales_invoice"))


# ---------------------------------------------------------------------------
# Projeção de estoque x demanda dos agendamentos (Fase 11).
# O ERPNext nativo (Stock Projected Qty / Item Shortage / Production Plan) só
# enxerga demanda de Sales Order / Material Request / Work Order — nunca de
# Patient Appointment. Aqui cruzamos os agendamentos futuros (1 linha de
# Imunocare Appointment Vaccine = 1 dose) com a posição do Bin nativo.
# ---------------------------------------------------------------------------


def _meses_horizonte(meses: int):
	"""Lista de ``(ano, mes, rotulo)`` a partir do mês corrente, ``meses`` à frente."""
	hoje = getdate(nowdate())
	ano, mes = hoje.year, hoje.month
	out = []
	for _i in range(meses):
		out.append((ano, mes, f"{_MESES_PT[mes]}/{ano % 100:02d}"))
		if mes == 12:
			ano, mes = ano + 1, 1
		else:
			mes += 1
	return out


def projetar_estoque(meses: int = 3, incluir_em_pedido: bool = True) -> dict:
	"""Projeta o saldo de cada vacina mês a mês contra a demanda dos agendamentos.

	A demanda vem das linhas ``Imunocare Appointment Vaccine`` de Patient
	Appointments com data de hoje em diante (não cancelados, não realizados) —
	cada linha conta 1 dose. O saldo inicial é o estoque atual do Bin (mais o
	que já está em pedido de compra, se ``incluir_em_pedido``), e vai sendo
	consumido a cada mês.

	Retorna ``{"meses": [rotulos], "linhas": [...]}`` — só vacinas que têm
	alguma demanda no horizonte (vacina sem agendamento não gera linha).
	"""
	meses = max(1, min(int(meses or 3), 24))
	horizonte = _meses_horizonte(meses)
	hoje = getdate(nowdate())
	fim = get_last_day(getdate(f"{horizonte[-1][0]}-{horizonte[-1][1]:02d}-01"))

	rows = frappe.db.sql(
		"""
		SELECT v.medication AS medication,
			YEAR(pa.appointment_date) AS ano,
			MONTH(pa.appointment_date) AS mes,
			COUNT(*) AS doses
		FROM `tabPatient Appointment` pa
		INNER JOIN `tabImunocare Appointment Vaccine` v
			ON v.parent = pa.name AND v.parenttype = 'Patient Appointment'
		WHERE pa.appointment_date BETWEEN %(de)s AND %(ate)s
			AND v.medication IS NOT NULL AND v.medication != ''
			AND pa.status NOT IN %(nao_demanda)s
		GROUP BY v.medication, ano, mes
		""",
		{"de": hoje, "ate": fim, "nao_demanda": STATUS_NAO_RISCO},
		as_dict=True,
	)

	demanda: dict[str, dict] = {}
	for r in rows:
		demanda.setdefault(r.medication, {})[(r.ano, r.mes)] = int(r.doses)

	linhas = []
	for med, por_mes in demanda.items():
		pos = posicao_estoque(med)
		inicial = pos["actual"] + (pos["ordered"] if incluir_em_pedido else 0.0)
		saldo = inicial
		saldos = []
		for ano, mes, _rotulo in horizonte:
			saldo -= por_mes.get((ano, mes), 0)
			saldos.append(saldo)
		demanda_total = sum(por_mes.values())
		linhas.append(
			{
				"medication": med,
				"estoque": pos["actual"],
				"em_pedido": pos["ordered"],
				"demanda_total": demanda_total,
				"saldos": saldos,
				# Repor = quanto falta para o saldo nunca ficar negativo no horizonte.
				"repor": max(0.0, -saldos[-1]),
			}
		)

	# Mais crítico primeiro (maior reposição), depois alfabético.
	linhas.sort(key=lambda x: (-x["repor"], x["medication"]))
	return {"meses": [r[2] for r in horizonte], "linhas": linhas}


@frappe.whitelist()
def vacinas_a_repor(meses: int = 3) -> int:
	"""Number Card (Custom): nº de vacinas que precisam de reposição no horizonte.

	Considera a demanda dos agendamentos contra o estoque atual + em pedido.
	"""
	return sum(1 for l in projetar_estoque(int(meses)).get("linhas", []) if l["repor"] > 0)
