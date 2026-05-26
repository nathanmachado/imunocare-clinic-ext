"""API das Campanhas de Vacinação Corporativa (Fase 12, ver ADR-0002).

Fluxo B2B: a empresa (Customer) contrata a vacinação dos colaboradores
(Patients); fatura-se a empresa em bloco. Reuso máximo (feedback_reuse_first):
- Customer / Price List / Item Price / Sales Order / Sales Invoice nativos;
- Patient + Patient Appointment + child ``imun_vaccines`` já existentes;
- a "cola" é o custom field ``imun_campaign`` no Patient Appointment.

Três ações, chamadas pelos botões do form (Client Script no DB):
1. ``importar_colaboradores`` — preenche o roster casando/criando Patients por CPF;
2. ``confirmar_campanha`` — gera o Sales Order (orçamento) a partir do escopo;
3. ``gerar_fatura`` — gera a Sales Invoice das doses realmente aplicadas.
"""

from __future__ import annotations

import csv
import io

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from imunocare_clinic_ext.imunocare_clinic_ext.doctype.imunocare_vaccination_campaign.imunocare_vaccination_campaign import (
	_preco_da_vacina,
)

# Doses já aplicadas/realizadas não voltam à demanda; cancelados também não.
_STATUS_FORA = ("Cancelled",)
# Sexo do roster → Gender nativo (Patient.sex). Só seta se o Gender existir.
_SEXO_GENDER = {"Masculino": "Male", "Feminino": "Female", "Outro": "Other"}


def _so_digitos(valor: str | None) -> str:
	return "".join(ch for ch in (valor or "") if ch.isdigit())


def _item_code_da_vacina(medication: str) -> str | None:
	return frappe.db.get_value(
		"Medication Linked Item",
		{"parent": medication, "parenttype": "Medication"},
		"item_code",
	)


# ---------------------------------------------------------------------------
# 1. Importação do roster (casar/criar Patient por CPF)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def importar_colaboradores(campaign: str, csv_text: str | None = None, rows: str | None = None) -> dict:
	"""Importa a lista da empresa para o roster da campanha.

	Aceita ``csv_text`` (cabeçalho: nome,cpf,nascimento,sexo,telefone,email,
	cargo,matricula) ou ``rows`` (JSON list de dicts). Para cada colaborador,
	casa o Patient pelo CPF ou cria um novo (com o mínimo de campanha — celular/
	email/nome-do-meio dispensados via ignore_mandatory, sem afetar o balcão B2C).
	"""
	doc = frappe.get_doc("Imunocare Vaccination Campaign", campaign)
	doc.check_permission("write")

	registros = _parse_rows(csv_text, rows)
	if not registros:
		frappe.throw(_("Nenhum colaborador na lista informada."))

	criados = casados = 0
	for reg in registros:
		nome = (reg.get("nome") or "").strip()
		if not nome:
			continue
		cpf = _so_digitos(reg.get("cpf"))
		patient, novo = _casar_ou_criar_patient(nome, cpf, reg, doc.empresa)
		criados += int(novo)
		casados += int(not novo)
		doc.append("colaboradores", {
			"nome": nome,
			"cpf": cpf,
			"data_nascimento": reg.get("nascimento") or reg.get("data_nascimento"),
			"sexo": (reg.get("sexo") or "").strip().title() or None,
			"telefone": reg.get("telefone"),
			"email": reg.get("email"),
			"cargo": reg.get("cargo"),
			"matricula": reg.get("matricula"),
			"patient": patient,
			"status": "Pendente",
		})

	if doc.status == "Rascunho":
		doc.status = "Lista Importada"
	doc.save()
	frappe.msgprint(
		_("Importados {0} colaboradores ({1} novos, {2} já cadastrados).").format(
			len(registros), criados, casados
		),
		indicator="green",
		alert=True,
	)
	return {"total": len(registros), "criados": criados, "casados": casados}


def _parse_rows(csv_text: str | None, rows: str | None) -> list[dict]:
	if rows:
		data = frappe.parse_json(rows)
		return data if isinstance(data, list) else []
	if not csv_text:
		return []
	# Sniff de delimitador (vírgula ou ponto-e-vírgula, comum em pt-BR/Excel).
	amostra = csv_text[:2048]
	delim = ";" if amostra.count(";") > amostra.count(",") else ","
	leitor = csv.DictReader(io.StringIO(csv_text.strip()), delimiter=delim)
	registros = []
	for linha in leitor:
		registros.append({(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()})
	return registros


def _casar_ou_criar_patient(nome: str, cpf: str, reg: dict, empresa: str | None = None) -> tuple[str | None, bool]:
	"""Retorna (patient_name, criado?). Casa por CPF; cria se não existir.

	No Patient novo, ``customer`` é setado para a empresa contratante: com
	``link_customer_to_patient`` ligado, isso faz o Healthcare vincular ao
	Customer existente em vez de criar um Customer-lixo por colaborador. Em
	pacientes já existentes (casados por CPF) o ``customer`` NÃO é tocado.
	Cuidado: ``Patient.customer`` é ``set_only_once`` (ver ADR-0002).
	"""
	if cpf:
		existente = frappe.db.get_value("Patient", {"cpf": cpf}, "name")
		if existente:
			return existente, False

	partes = nome.split()
	first = partes[0]
	last = partes[-1] if len(partes) > 1 else ""
	middle = " ".join(partes[1:-1]) if len(partes) > 2 else ""

	p = frappe.new_doc("Patient")
	p.first_name = first
	p.middle_name = middle
	p.last_name = last
	if cpf:
		p.cpf = cpf
	dob = reg.get("nascimento") or reg.get("data_nascimento")
	if dob:
		p.dob = getdate(dob)
	gender = _SEXO_GENDER.get((reg.get("sexo") or "").strip().title())
	if gender and frappe.db.exists("Gender", gender):
		p.sex = gender
	if reg.get("telefone"):
		p.mobile = reg.get("telefone")
	if reg.get("email"):
		p.email = reg.get("email")
	if empresa:
		p.customer = empresa
	# Mínimo de campanha: dispensa as obrigatoriedades do balcão B2C (celular/
	# email/nome-do-meio) que a empresa pode não enviar.
	p.flags.ignore_mandatory = True
	p.insert(ignore_permissions=True)
	return p.name, True


# ---------------------------------------------------------------------------
# 2. Confirmar campanha → Sales Order (orçamento)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def confirmar_campanha(campaign: str) -> str:
	"""Gera o Sales Order (orçamento) a partir do escopo e confirma a campanha.

	Qtd estimada por vacina = doses_por_colaborador × nº de colaboradores.
	Retorna o nome do Sales Order criado.
	"""
	doc = frappe.get_doc("Imunocare Vaccination Campaign", campaign)
	doc.check_permission("write")

	if doc.sales_order:
		frappe.throw(_("Campanha já tem orçamento: {0}.").format(doc.sales_order))
	if not doc.vacinas_ofertadas:
		frappe.throw(_("Defina ao menos uma vacina ofertada antes de confirmar."))
	n = len(doc.colaboradores or [])
	if not n:
		frappe.throw(_("Importe a lista de colaboradores antes de confirmar."))

	so = frappe.new_doc("Sales Order")
	so.customer = doc.empresa
	so.transaction_date = nowdate()
	so.delivery_date = doc.data_inicio or nowdate()
	so.selling_price_list = doc.price_list
	so.order_type = "Sales"

	for v in doc.vacinas_ofertadas:
		item_code = _item_code_da_vacina(v.medication)
		if not item_code:
			frappe.throw(_("Vacina {0} não tem item de estoque vinculado.").format(v.medication))
		so.append("items", {
			"item_code": item_code,
			"qty": (v.doses_por_colaborador or 0) * n,
			"rate": _preco_da_vacina(v.medication, doc.price_list),
			"delivery_date": doc.data_inicio or nowdate(),
		})

	so.flags.ignore_permissions = True
	so.insert()
	so.submit()

	doc.sales_order = so.name
	doc.status = "Confirmada"
	doc.save()
	frappe.msgprint(_("Orçamento {0} criado e confirmado.").format(so.name), indicator="green", alert=True)
	return so.name


# ---------------------------------------------------------------------------
# 3. Fechamento → Sales Invoice (doses realmente aplicadas)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def campanhas_a_faturar() -> int:
	"""Number Card (Custom): campanhas confirmadas/em andamento ainda não faturadas."""
	return frappe.db.count(
		"Imunocare Vaccination Campaign",
		{"status": ("in", ["Confirmada", "Em Aplicação", "Fechada"])},
	)


def doses_aplicadas(campaign: str) -> list[dict]:
	"""Doses realmente aplicadas na campanha, agregadas por vacina.

	Conta as linhas ``imun_vaccines`` dos Patient Appointments marcados com a
	campanha (status não cancelado). É a base do faturamento e do relatório.
	"""
	return frappe.db.sql(
		"""
		SELECT v.medication AS medication, COUNT(*) AS doses
		FROM `tabPatient Appointment` pa
		INNER JOIN `tabImunocare Appointment Vaccine` v
			ON v.parent = pa.name AND v.parenttype = 'Patient Appointment'
		WHERE pa.imun_campaign = %(c)s
			AND v.medication IS NOT NULL AND v.medication != ''
			AND pa.status NOT IN %(fora)s
		GROUP BY v.medication
		ORDER BY v.medication
		""",
		{"c": campaign, "fora": _STATUS_FORA},
		as_dict=True,
	)


@frappe.whitelist()
def gerar_fatura(campaign: str) -> str:
	"""Gera a Sales Invoice das doses aplicadas e fecha a campanha.

	1 linha por vacina (qtd = doses aplicadas, rate = Item Price da price_list).
	``update_stock = 0`` — a baixa de estoque ocorre na aplicação, não aqui.
	Vincula ao Sales Order (so_detail) quando há item correspondente, para o
	ERPNext atualizar o billing status do orçamento. Marca os appointments como
	faturados (ref_sales_invoice) para não aparecerem como "a pagar" na Agenda.
	"""
	doc = frappe.get_doc("Imunocare Vaccination Campaign", campaign)
	doc.check_permission("write")

	if doc.sales_invoice:
		frappe.throw(_("Campanha já faturada: {0}.").format(doc.sales_invoice))

	doses = doses_aplicadas(campaign)
	if not doses:
		frappe.throw(_("Nenhuma dose aplicada vinculada a esta campanha ainda."))

	# Mapa item_code → linha do Sales Order (para vincular billing).
	so_detail_por_item: dict[str, str] = {}
	if doc.sales_order:
		for it in frappe.get_all(
			"Sales Order Item",
			filters={"parent": doc.sales_order},
			fields=["name", "item_code"],
		):
			so_detail_por_item.setdefault(it.item_code, it.name)

	si = frappe.new_doc("Sales Invoice")
	si.customer = doc.empresa
	si.selling_price_list = doc.price_list
	si.update_stock = 0
	si.set_posting_time = 1
	si.posting_date = nowdate()

	total_doses = 0
	for d in doses:
		item_code = _item_code_da_vacina(d.medication)
		if not item_code:
			frappe.throw(_("Vacina {0} não tem item de estoque vinculado.").format(d.medication))
		linha = {
			"item_code": item_code,
			"qty": d.doses,
			"rate": _preco_da_vacina(d.medication, doc.price_list),
		}
		if item_code in so_detail_por_item:
			linha["sales_order"] = doc.sales_order
			linha["so_detail"] = so_detail_por_item[item_code]
		si.append("items", linha)
		total_doses += int(d.doses)

	si.flags.ignore_permissions = True
	si.insert()  # rascunho: o operador revisa e submete na contabilidade.

	# Marca os appointments da campanha como faturados (some o "a pagar").
	apps = frappe.get_all(
		"Patient Appointment",
		filters={"imun_campaign": campaign, "status": ("not in", _STATUS_FORA)},
		pluck="name",
	)
	for ap in apps:
		frappe.db.set_value(
			"Patient Appointment", ap,
			{"invoiced": 1, "ref_sales_invoice": si.name},
			update_modified=False,
		)

	doc.sales_invoice = si.name
	doc.total_doses_aplicadas = total_doses
	doc.valor_faturado = si.grand_total
	doc.status = "Faturada"
	doc.save()
	frappe.msgprint(
		_("Fatura {0} criada (rascunho) com {1} doses. Revise e submeta.").format(si.name, total_doses),
		indicator="green",
		alert=True,
	)
	return si.name
