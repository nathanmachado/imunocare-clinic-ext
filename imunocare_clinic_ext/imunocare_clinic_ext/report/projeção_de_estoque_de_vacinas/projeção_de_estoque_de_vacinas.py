"""Report Projeção de Estoque de Vacinas (Fase 11).

Cruza a demanda dos agendamentos futuros (linhas Imunocare Appointment Vaccine,
1 linha = 1 dose) com a posição do estoque nativo (Bin) e projeta o saldo de
cada vacina mês a mês. Responde diretamente à pergunta "quanto preciso repor
para os próximos meses".

Por que não usar o nativo: Stock Projected Qty / Item Shortage / Production
Plan calculam projeção, mas a demanda deles vem só de Sales Order / Material
Request / Work Order — nunca de Patient Appointment. Toda a aritmética de
estoque, porém, reusa o Bin nativo (ver feedback_reuse_first).

Colunas dinâmicas: uma por mês do horizonte (saldo projetado no fim do mês),
geradas em runtime. A renderização (vermelho p/ saldo negativo, destaque do
"Repor", largura total) fica no ``.js`` do app — sem build de assets.
"""

from __future__ import annotations

from frappe import _

from imunocare_clinic_ext.api.dashboard import projetar_estoque


def execute(filters: dict | None = None):
	filters = filters or {}
	meses = int(filters.get("meses") or 3)
	incluir = filters.get("incluir_em_pedido")
	incluir = True if incluir is None else bool(incluir)
	so_deficit = bool(filters.get("somente_com_deficit"))

	proj = projetar_estoque(meses=meses, incluir_em_pedido=incluir)
	linhas = proj["linhas"]
	if so_deficit:
		linhas = [l for l in linhas if l["repor"] > 0]

	return _columns(proj["meses"]), _data(linhas)


def _columns(rotulos_mes: list[str]) -> list[dict]:
	cols = [
		{"label": _("Vacina"), "fieldname": "medication", "fieldtype": "Link", "options": "Medication", "width": 220},
		{"label": _("Estoque"), "fieldname": "estoque", "fieldtype": "Float", "precision": "0", "width": 90},
		{"label": _("Em pedido"), "fieldname": "em_pedido", "fieldtype": "Float", "precision": "0", "width": 95},
	]
	# Uma coluna por mês: saldo projetado no fim do mês (saldo_0, saldo_1, ...).
	for i, rotulo in enumerate(rotulos_mes):
		cols.append({"label": rotulo, "fieldname": f"saldo_{i}", "fieldtype": "Float", "precision": "0", "width": 90})
	cols += [
		{"label": _("Demanda"), "fieldname": "demanda_total", "fieldtype": "Float", "precision": "0", "width": 95},
		{"label": _("Repor"), "fieldname": "repor", "fieldtype": "Float", "precision": "0", "width": 100},
	]
	return cols


def _data(linhas: list[dict]) -> list[dict]:
	out = []
	for l in linhas:
		row = {
			"medication": l["medication"],
			"estoque": l["estoque"],
			"em_pedido": l["em_pedido"],
			"demanda_total": l["demanda_total"],
			"repor": l["repor"],
		}
		for i, saldo in enumerate(l["saldos"]):
			row[f"saldo_{i}"] = saldo
		out.append(row)
	return out
