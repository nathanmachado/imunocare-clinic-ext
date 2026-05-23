from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, nowdate

from imunocare_clinic_ext.api.vaccine_card import (
	STATUS_APLICADA,
	STATUS_ATRASADA,
	STATUS_FUTURA,
	get_vaccine_card,
)
from imunocare_clinic_ext.install import install_imunization_customizations

_PATIENT_MOBILE = "+5511933333333"


def _cleanup():
	for enc in frappe.get_all("Patient Encounter", filters={"patient_name": "Bebê Teste Carteira"}, pluck="name"):
		frappe.delete_doc("Patient Encounter", enc, force=True, ignore_permissions=True)
	for pat in frappe.get_all("Patient", filters={"first_name": "Bebê Teste Carteira"}, pluck="name"):
		frappe.delete_doc("Patient", pat, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestFase2CustomFields(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_patient_cns_field(self):
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Patient", "fieldname": "cns"}))

	def test_drug_prescription_fields(self):
		for fieldname in (
			"dose_numero", "lote", "fabricante", "validade_lote",
			"local_anatomico_aplicado", "via_administracao_aplicada",
			"rnds_status", "rnds_id", "rnds_payload",
		):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": "Drug Prescription", "fieldname": fieldname}),
				f"Custom Field ausente em Drug Prescription: {fieldname}",
			)

	def test_patient_appointment_fields(self):
		for fieldname in ("imun_modalidade", "imun_application_address_display"):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": "Patient Appointment", "fieldname": fieldname}),
				f"Custom Field ausente em Patient Appointment: {fieldname}",
			)


class TestCpfValidation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_cpf_field_installed(self):
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Patient", "fieldname": "cpf"}))

	def test_cns_is_read_only(self):
		ro = frappe.db.get_value("Custom Field", {"dt": "Patient", "fieldname": "cns"}, "read_only")
		self.assertEqual(ro, 1)

	def test_cns_description(self):
		desc = frappe.db.get_value("Custom Field", {"dt": "Patient", "fieldname": "cns"}, "description")
		self.assertEqual(desc, "Atualizado automaticamente")

	def test_cpf_has_no_description(self):
		desc = frappe.db.get_value("Custom Field", {"dt": "Patient", "fieldname": "cpf"}, "description")
		self.assertFalse(desc)

	def test_native_uid_is_hidden(self):
		hidden = frappe.db.get_value(
			"Property Setter",
			{"doc_type": "Patient", "field_name": "uid", "property": "hidden"},
			"value",
		)
		self.assertEqual(hidden, "1")

	def test_valid_cpf_passes_and_normalizes(self):
		from imunocare_clinic_ext.patient_hooks import validate

		# CPF válido conhecido, formatado
		doc = frappe._dict(cpf="529.982.247-25")
		validate(doc)
		self.assertEqual(doc.cpf, "52998224725")  # normalizado para dígitos

	def test_invalid_cpf_raises(self):
		from imunocare_clinic_ext.patient_hooks import validate

		for bad in ("111.111.111-11", "12345678900", "529.982.247-26", "123"):
			with self.assertRaises(frappe.ValidationError):
				validate(frappe._dict(cpf=bad))

	def test_empty_cpf_is_allowed(self):
		from imunocare_clinic_ext.patient_hooks import validate

		doc = frappe._dict(cpf=None)
		validate(doc)  # não levanta
		self.assertIsNone(doc.get("cpf"))

	def test_is_valid_cpf_helper(self):
		from imunocare_clinic_ext.patient_hooks import is_valid_cpf

		self.assertTrue(is_valid_cpf("52998224725"))
		self.assertFalse(is_valid_cpf("11111111111"))
		self.assertFalse(is_valid_cpf("529982247"))  # curto
		self.assertFalse(is_valid_cpf("5299822472a"))  # não-dígito


class TestVaccineCard(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		_cleanup()
		# Paciente de 7 meses (dob = hoje - 7 meses)
		cls.patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Bebê Teste Carteira",
				"sex": "Female",
				"dob": add_months(nowdate(), -7),
				"mobile": _PATIENT_MOBILE,
				# Evita "Cannot select a Group type Customer Group" do default inválido
				"customer_group": "Pessoa Física",
			}
		).insert(ignore_permissions=True).name

		# Aplica a 1ª dose de Hepatite B via Patient Encounter.
		# ignore_mandatory: Drug Prescription nativo exige dosage_form/period que
		# não fazem sentido pra vacina; só precisamos da linha para a carteira.
		practitioner = frappe.db.get_value("Healthcare Practitioner", {}, "name")
		cls.encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": cls.patient,
				"practitioner": practitioner,
				"encounter_date": nowdate(),
				"drug_prescription": [
					{
						"medication": "Hepatite B",
						"drug_code": "imunocare-vacina-hepatite-b",
						"dose_numero": 1,
						"lote": "LOTE-TESTE-01",
					}
				],
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def test_card_structure(self):
		card = get_vaccine_card(self.patient)
		self.assertEqual(card["patient"], self.patient)
		self.assertEqual(card["idade_meses"], 7)
		self.assertIsInstance(card["doses"], list)
		self.assertTrue(len(card["doses"]) > 0)

	def test_applied_dose_is_marked(self):
		card = get_vaccine_card(self.patient)
		hep_b_d1 = next(
			d for d in card["doses"]
			if d["vacina"] == "Hepatite B" and d["dose_numero"] == 1
		)
		self.assertEqual(hep_b_d1["status"], STATUS_APLICADA)
		self.assertEqual(hep_b_d1["lote"], "LOTE-TESTE-01")

	def test_future_dose_for_baby(self):
		"""HPV (idade ideal 108 meses) deve ser Futura para bebê de 7 meses."""
		card = get_vaccine_card(self.patient)
		hpv = next((d for d in card["doses"] if d["vacina"] == "HPV Nonavalente"), None)
		if hpv:  # só existe se calendário adolescente estiver seedado
			self.assertEqual(hpv["status"], STATUS_FUTURA)

	def test_overdue_dose(self):
		"""Meningo B dose 1 (ideal 3 meses) não aplicada em bebê de 7 meses → Atrasada.

		(7-3)*30 = 120 dias além da idade ideal, bem acima da tolerância de 30.
		"""
		card = get_vaccine_card(self.patient)
		meningo_d1 = next(
			(d for d in card["doses"]
			 if d["vacina"] == "Meningocócica B" and d["dose_numero"] == 1),
			None,
		)
		self.assertIsNotNone(meningo_d1)
		self.assertEqual(meningo_d1["status"], STATUS_ATRASADA)

	def test_resumo_counts_match_doses(self):
		card = get_vaccine_card(self.patient)
		self.assertEqual(sum(card["resumo"].values()), len(card["doses"]))


class TestAppointmentAddressHook(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_clinic_modalidade_uses_config_address(self):
		from imunocare_clinic_ext.appointment_hooks import before_save

		doc = frappe._dict(imun_modalidade="Clínica", patient=None)
		before_save(doc)
		self.assertTrue(doc.imun_application_address_display)
		# default hardcoded quando site_config não tem a chave
		expected = frappe.conf.get("imunocare_clinic_address_short") or "Imunocare - Unidade Pátio Sabiá"
		self.assertEqual(doc.imun_application_address_display, expected)

	def test_domiciliar_without_patient_address_is_empty(self):
		from imunocare_clinic_ext.appointment_hooks import before_save

		doc = frappe._dict(imun_modalidade="Domiciliar", patient=None)
		before_save(doc)
		self.assertEqual(doc.imun_application_address_display, "")
