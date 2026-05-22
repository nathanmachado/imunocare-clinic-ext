from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from imunocare_clinic_ext.data.pni_2026 import CALENDARIOS, VACINAS
from imunocare_clinic_ext.install import install_imunization_customizations


class TestImunizationSetup(FrappeTestCase):
	"""Valida instalação idempotente dos custom fields + seed PNI 2026."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_custom_fields_installed_in_medication(self):
		for fieldname in (
			"is_vaccine",
			"codigo_rnds",
			"tipo_imunizacao",
			"via_administracao_padrao",
			"local_anatomico_padrao",
			"obrigatoria_pni",
			"pni_idade_meses_inicio",
		):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": "Medication", "fieldname": fieldname}),
				f"Custom Field ausente em Medication: {fieldname}",
			)

	def test_custom_fields_installed_in_therapy_plan_template(self):
		for dt, fieldname in (
			("Therapy Plan Template", "is_pni"),
			("Therapy Plan Template", "versao_pni"),
			("Therapy Plan Template Detail", "medication"),
			("Therapy Plan Template Detail", "dose_numero"),
			("Therapy Plan Template Detail", "intervalo_dias_min"),
			("Therapy Plan Template Detail", "idade_meses_ideal"),
		):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}),
				f"Custom Field ausente em {dt}: {fieldname}",
			)

	def test_seed_creates_item_group_and_items(self):
		self.assertTrue(frappe.db.exists("Item Group", "Vacinas"))
		for vacina in VACINAS:
			self.assertTrue(
				frappe.db.exists("Item", vacina["code"]),
				f"Item ausente: {vacina['code']}",
			)

	def test_seed_creates_medications_as_vaccines(self):
		for vacina in VACINAS:
			med = frappe.get_doc("Medication", vacina["medication_name"])
			self.assertEqual(med.is_vaccine, 1)
			self.assertEqual(med.codigo_rnds, vacina["codigo_rnds"])
			self.assertEqual(med.tipo_imunizacao, vacina["tipo_imunizacao"])
			self.assertEqual(med.via_administracao_padrao, vacina["via_administracao_padrao"])
			self.assertEqual(med.local_anatomico_padrao, vacina["local_anatomico_padrao"])
			self.assertEqual(med.obrigatoria_pni, vacina["obrigatoria_pni"])
			# Linked Item populated
			self.assertEqual(len(med.linked_items), 1)
			self.assertEqual(med.linked_items[0].item_code, vacina["code"])

	def test_seed_creates_therapy_types_per_vaccine(self):
		for vacina in VACINAS:
			name = f"Aplicação - {vacina['medication_name']}"
			self.assertTrue(
				frappe.db.exists("Therapy Type", name),
				f"Therapy Type ausente: {name}",
			)

	def test_seed_creates_pni_therapy_plan_templates(self):
		for calendario in CALENDARIOS:
			tpl = frappe.get_doc("Therapy Plan Template", calendario["template_name"])
			self.assertEqual(tpl.is_pni, 1)
			self.assertEqual(tpl.versao_pni, calendario["versao_pni"])
			self.assertEqual(len(tpl.therapy_types), len(calendario["doses"]))
			# Doses na ordem certa
			for got, expected in zip(tpl.therapy_types, calendario["doses"]):
				self.assertEqual(got.medication, expected["medication_name"])
				self.assertEqual(got.dose_numero, expected["dose"])
				self.assertEqual(got.intervalo_dias_min, expected["intervalo_dias"])
				self.assertEqual(got.idade_meses_ideal, expected["idade_meses"])

	def test_query_vacinas_obrigatorias_pni(self):
		"""Query suportada pela ADR: 'todas vacinas obrigatórias PNI'."""
		nomes = frappe.get_all(
			"Medication",
			filters={"is_vaccine": 1, "obrigatoria_pni": 1},
			pluck="name",
		)
		self.assertIn("BCG", nomes)
		self.assertIn("Hepatite B", nomes)
		self.assertIn("Influenza Tetravalente", nomes)
		self.assertNotIn("Meningocócica B", nomes)  # particular
		self.assertNotIn("HPV Nonavalente", nomes)  # particular

	def test_install_is_idempotent(self):
		"""Re-rodar install_imunization_customizations não deve criar duplicatas."""
		install_imunization_customizations()
		install_imunization_customizations()
		for vacina in VACINAS:
			self.assertEqual(
				frappe.db.count("Item", {"item_code": vacina["code"]}),
				1,
				f"Item duplicado: {vacina['code']}",
			)
		for calendario in CALENDARIOS:
			self.assertEqual(
				frappe.db.count("Therapy Plan Template", {"name": calendario["template_name"]}),
				1,
				f"Therapy Plan Template duplicado: {calendario['template_name']}",
			)
