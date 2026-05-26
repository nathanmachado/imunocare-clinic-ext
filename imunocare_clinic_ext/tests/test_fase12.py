"""Testes das Campanhas de Vacinação Corporativa (Fase 12, ADR-0002)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from imunocare_clinic_ext.api.campaign import (
	_parse_rows,
	_so_digitos,
	campanhas_a_faturar,
	confirmar_campanha,
	doses_aplicadas,
	gerar_fatura,
	importar_colaboradores,
)
from imunocare_clinic_ext.install import (
	_CAMPAIGN_DOCTYPE,
	_NC_CAMPANHAS_FATURAR,
	_PRICE_LIST_EMPRESARIAL,
	install_imunization_customizations,
)
from imunocare_clinic_ext.imunocare_clinic_ext.report.fechamento_de_campanha.fechamento_de_campanha import (
	execute as fechamento_execute,
)

VACINA = "BCG"
ITEM_VACINA = "imunocare-vacina-bcg"
PRECO = 50.0


def _gera_cpf(base9: str) -> str:
	"""Gera um CPF válido (com dígitos verificadores) a partir de 9 dígitos."""
	nums = [int(d) for d in base9]
	for length in (9, 10):
		soma = sum(nums[i] * (length + 1 - i) for i in range(length))
		nums.append((soma * 10 % 11) % 10)
	return "".join(str(n) for n in nums)


CPF_MARIA = _gera_cpf("987654321")
CPF_CARLOS = _gera_cpf("123000111")
CPF_FULANO1 = _gera_cpf("100000001")
CPF_FULANO2 = _gera_cpf("100000002")
CPF_APLICA = _gera_cpf("100000003")


class TestFase12Campanha(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		# Selling Settings com grupo/território não-grupo, senão criar Patient
		# sem customer (link_customer_to_patient) quebra em create_customer.
		frappe.db.set_single_value(
			"Selling Settings",
			"customer_group",
			frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		)
		frappe.db.set_single_value(
			"Selling Settings",
			"territory",
			frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		)
		cls.empresa = _ensure_customer("ACME Testes Ltda")
		_ensure_item_price(ITEM_VACINA, _PRICE_LIST_EMPRESARIAL, PRECO)

	def _nova_campanha(self, titulo="Campanha Teste"):
		doc = frappe.new_doc(_CAMPAIGN_DOCTYPE)
		doc.titulo = titulo
		doc.empresa = self.empresa
		doc.price_list = _PRICE_LIST_EMPRESARIAL
		doc.data_inicio = nowdate()
		doc.append("vacinas_ofertadas", {"medication": VACINA, "doses_por_colaborador": 1})
		doc.insert(ignore_permissions=True)
		return doc

	# --- registro ----------------------------------------------------------

	def test_doctypes_registrados(self):
		for dt in (_CAMPAIGN_DOCTYPE, "Imunocare Campaign Colaborador", "Imunocare Campaign Vaccine"):
			self.assertTrue(frappe.db.exists("DocType", dt), f"DocType ausente: {dt}")

	def test_price_list_e_number_card(self):
		self.assertTrue(frappe.db.exists("Price List", _PRICE_LIST_EMPRESARIAL))
		self.assertTrue(frappe.db.exists("Number Card", _NC_CAMPANHAS_FATURAR))

	# --- utilidades puras --------------------------------------------------

	def test_so_digitos(self):
		self.assertEqual(_so_digitos("123.456.789-00"), "12345678900")
		self.assertEqual(_so_digitos(None), "")

	def test_parse_rows_csv_ponto_e_virgula(self):
		csv_text = "nome;cpf;nascimento\nJoao Silva;111.222.333-44;1990-01-15"
		regs = _parse_rows(csv_text, None)
		self.assertEqual(len(regs), 1)
		self.assertEqual(regs[0]["nome"], "Joao Silva")
		self.assertEqual(regs[0]["cpf"], "111.222.333-44")

	# --- importação do roster ----------------------------------------------

	def test_importar_casa_e_cria(self):
		# Paciente pré-existente casado por CPF.
		if not frappe.db.exists("Patient", {"cpf": CPF_MARIA}):
			p = frappe.new_doc("Patient")
			p.first_name = "Maria"
			p.last_name = "Existente"
			p.cpf = CPF_MARIA
			p.customer = self.empresa
			p.flags.ignore_mandatory = True
			p.insert(ignore_permissions=True)

		camp = self._nova_campanha("Import")
		csv_text = (
			"nome,cpf,nascimento,sexo\n"
			f"Maria Existente,{CPF_MARIA},1985-03-10,Feminino\n"
			f"Carlos Novo Colaborador,{CPF_CARLOS},1992-07-20,Masculino\n"
		)
		res = importar_colaboradores(camp.name, csv_text=csv_text)
		self.assertEqual(res["total"], 2)
		self.assertEqual(res["casados"], 1)
		self.assertEqual(res["criados"], 1)

		camp.reload()
		self.assertEqual(len(camp.colaboradores), 2)
		self.assertTrue(all(c.patient for c in camp.colaboradores))
		self.assertEqual(camp.status, "Lista Importada")
		# Novo colaborador vinculado à empresa (sem Customer-lixo).
		novo = frappe.db.get_value("Patient", {"cpf": CPF_CARLOS}, "customer")
		self.assertEqual(novo, self.empresa)

	# --- confirmar → Sales Order -------------------------------------------

	def test_confirmar_gera_sales_order(self):
		camp = self._nova_campanha("Confirmar")
		importar_colaboradores(
			camp.name,
			csv_text=f"nome,cpf\nFulano Um,{CPF_FULANO1}\nFulano Dois,{CPF_FULANO2}\n",
		)
		so_name = confirmar_campanha(camp.name)
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual(so.customer, self.empresa)
		self.assertEqual(len(so.items), 1)
		self.assertEqual(so.items[0].qty, 2)  # 1 dose × 2 colaboradores
		self.assertEqual(so.items[0].rate, PRECO)
		camp.reload()
		self.assertEqual(camp.status, "Confirmada")
		self.assertEqual(camp.sales_order, so_name)

	# --- aplicação + faturamento -------------------------------------------

	def test_doses_aplicadas_e_fatura(self):
		camp = self._nova_campanha("Faturar")
		importar_colaboradores(camp.name, csv_text=f"nome,cpf\nPaciente Aplica,{CPF_APLICA}\n")
		camp.reload()
		patient = camp.colaboradores[0].patient

		appt = self._make_appointment(patient, camp.name, VACINA)
		self.assertTrue(appt.name)

		doses = doses_aplicadas(camp.name)
		self.assertEqual(len(doses), 1)
		self.assertEqual(doses[0]["medication"], VACINA)
		self.assertEqual(doses[0]["doses"], 1)

		si_name = gerar_fatura(camp.name)
		si = frappe.get_doc("Sales Invoice", si_name)
		self.assertEqual(si.customer, self.empresa)
		self.assertEqual(len(si.items), 1)
		self.assertEqual(si.items[0].qty, 1)
		self.assertEqual(si.update_stock, 0)

		camp.reload()
		self.assertEqual(camp.status, "Faturada")
		self.assertEqual(camp.sales_invoice, si_name)
		self.assertEqual(camp.total_doses_aplicadas, 1)
		# Appointment marcado como faturado (some o "a pagar" na Agenda).
		self.assertEqual(frappe.db.get_value("Patient Appointment", appt.name, "ref_sales_invoice"), si_name)

	def test_campanhas_a_faturar_int(self):
		self.assertIsInstance(campanhas_a_faturar(), int)

	# --- report ------------------------------------------------------------

	def test_fechamento_execute(self):
		columns, data = fechamento_execute({})
		fieldnames = {c["fieldname"] for c in columns}
		for esperado in ("campaign", "empresa", "patient", "medication", "valor"):
			self.assertIn(esperado, fieldnames)
		self.assertIsInstance(data, list)

	# --- helper ------------------------------------------------------------

	def _make_appointment(self, patient, campaign, medication):
		"""Insere um Patient Appointment + vacina via ``db_insert`` (sem validate/
		hooks): o teste exercita a agregação e o faturamento, não a maquinaria de
		billing individual do Healthcare (item de serviço, service unit, etc.)."""
		appt = frappe.new_doc("Patient Appointment")
		appt.name = "TEST-CAMP-APPT-" + frappe.generate_hash(length=8)
		appt.flags.name_set = True
		appt.patient = patient
		appt.appointment_date = nowdate()
		appt.status = "Open"
		appt.imun_campaign = campaign
		appt.db_insert()

		vac = frappe.new_doc("Imunocare Appointment Vaccine")
		vac.parent = appt.name
		vac.parenttype = "Patient Appointment"
		vac.parentfield = "imun_vaccines"
		vac.idx = 1
		vac.medication = medication
		vac.dose_numero = 1
		vac.db_insert()
		return appt


def _ensure_customer(nome: str) -> str:
	existente = frappe.db.get_value("Customer", {"customer_name": nome}, "name")
	if existente:
		return existente
	c = frappe.new_doc("Customer")
	c.customer_name = nome
	c.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	c.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	c.customer_type = "Company"
	c.insert(ignore_permissions=True)
	return c.name


def _ensure_item_price(item_code: str, price_list: str, rate: float) -> None:
	if frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		return
	ip = frappe.new_doc("Item Price")
	ip.item_code = item_code
	ip.price_list = price_list
	ip.selling = 1
	ip.price_list_rate = rate
	ip.insert(ignore_permissions=True)
