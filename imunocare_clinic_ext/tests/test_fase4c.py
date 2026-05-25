from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from imunocare_clinic_ext.install import install_imunization_customizations
from imunocare_clinic_ext.rnds_immunization import (
	SYS_CNS,
	SYS_CPF,
	SYS_IMUNOBIOLOGICO,
	build_immunization_bundle,
)


def _base_data(**over):
	data = {
		"patient_id_system": SYS_CNS,
		"patient_id_value": "700508547440008",
		"cnes": "1234567",
		"imunobiologico": "86",
		"occurrence": "2026-05-24T10:00:00",
		"lote": "LOTE-XA-2345",
		"fabricante": "Butantan",
		"dose_numero": 1,
		"profissional_cns": "980016287974410",
		"estrategia": "2",
	}
	data.update(over)
	return data


class TestImmunizationBundle(FrappeTestCase):
	def test_bundle_is_document_with_two_entries(self):
		bundle = build_immunization_bundle(_base_data())
		self.assertEqual(bundle["resourceType"], "Bundle")
		self.assertEqual(bundle["type"], "document")
		types = [e["resource"]["resourceType"] for e in bundle["entry"]]
		self.assertIn("Composition", types)
		self.assertIn("Immunization", types)

	def _immunization(self, bundle):
		return next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Immunization")

	def test_vaccine_code_and_status(self):
		imm = self._immunization(build_immunization_bundle(_base_data()))
		self.assertEqual(imm["status"], "completed")
		coding = imm["vaccineCode"]["coding"][0]
		self.assertEqual(coding["system"], SYS_IMUNOBIOLOGICO)
		self.assertEqual(coding["code"], "86")

	def test_patient_identifier_and_lot(self):
		imm = self._immunization(build_immunization_bundle(_base_data()))
		self.assertEqual(imm["patient"]["identifier"]["value"], "700508547440008")
		self.assertEqual(imm["lotNumber"], "LOTE-XA-2345")
		self.assertEqual(imm["protocolApplied"][0]["doseNumberString"], "1")

	def test_manufacturer_and_performer(self):
		imm = self._immunization(build_immunization_bundle(_base_data()))
		self.assertEqual(imm["manufacturer"]["display"], "Butantan")
		self.assertEqual(imm["performer"][0]["actor"]["identifier"]["value"], "980016287974410")

	def test_estrategia_extension(self):
		imm = self._immunization(build_immunization_bundle(_base_data()))
		ext_codes = [
			e["valueCodeableConcept"]["coding"][0]["code"]
			for e in imm["extension"]
			if "valueCodeableConcept" in e
		]
		self.assertIn("2", ext_codes)

	def test_composition_references_immunization(self):
		bundle = build_immunization_bundle(_base_data())
		comp = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Composition")
		imm_entry = next(e for e in bundle["entry"] if e["resource"]["resourceType"] == "Immunization")
		self.assertEqual(comp["section"][0]["entry"][0]["reference"], imm_entry["fullUrl"])

	def test_cpf_fallback_identifier(self):
		imm = self._immunization(build_immunization_bundle(_base_data(patient_id_system=SYS_CPF, patient_id_value="52998224725")))
		self.assertEqual(imm["patient"]["identifier"]["system"], SYS_CPF)


class TestRndsImmunizationFields(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_practitioner_cns_field(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", {"dt": "Healthcare Practitioner", "fieldname": "cns"})
		)
