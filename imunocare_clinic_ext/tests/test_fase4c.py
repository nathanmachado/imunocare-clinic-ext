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


class TestEnvioUsaProfissionalDaAplicacao(FrappeTestCase):
	"""O envio do RIA usa o CNS do profissional que aplicou (não um fixo)."""

	def test_ehr_post_passa_cns_do_aplicador(self):
		from unittest.mock import patch

		from imunocare_clinic_ext import rnds_client

		captured = {}

		def fake_headers(settings, extra=None, cns_solicitante=None):
			captured["cns"] = cns_solicitante
			return {"X-Authorization-Server": "Bearer T", **(extra or {})}

		class FakeSettings(dict):
			url_ehr = "https://x/api/fhir/r4"
			def get(self, k, d=None):
				return d

		with patch.object(rnds_client, "_settings", return_value=FakeSettings()), patch.object(
			rnds_client, "_ehr_auth_headers", side_effect=fake_headers
		), patch.object(rnds_client.requests, "post", return_value=object()):
			rnds_client.ehr_post("Bundle", {"x": 1}, cns_solicitante="700905964221498")

		# o CNS do aplicador chega ao montador de headers
		self.assertEqual(captured["cns"], "700905964221498")

	def test_auth_header_prioriza_cns_da_operacao(self):
		from unittest.mock import patch

		from imunocare_clinic_ext import rnds_client

		# Settings tem um profissional responsável (Larissa), mas a operação
		# informa o CNS de quem aplicou (Maria) — deve prevalecer o da operação.
		s = frappe._dict(cns_solicitante="111LARISSA", profissional_responsavel=None)
		with patch.object(rnds_client, "get_access_token", return_value="T"):
			headers = rnds_client._ehr_auth_headers(s, cns_solicitante="700905964221498")
		self.assertEqual(headers["Authorization"], "700905964221498")


class TestRndsImmunizationFields(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_cpf_no_employee_cns_no_practitioner(self):
		# CPF é do colaborador (Employee); profissional só tem CNS (read-only).
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Employee", "fieldname": "cpf"}))
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Healthcare Practitioner", "fieldname": "cns"}))
		self.assertFalse(frappe.db.exists("Custom Field", {"dt": "Healthcare Practitioner", "fieldname": "cpf"}))

	def test_employee_cpf_obrigatorio(self):
		reqd = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": "cpf"}, "reqd")
		self.assertEqual(reqd, 1)

	def test_employee_obrigatorio_no_practitioner(self):
		reqd = frappe.db.get_value(
			"Property Setter",
			{"doc_type": "Healthcare Practitioner", "field_name": "employee", "property": "reqd"},
			"value",
		)
		self.assertEqual(reqd, "1")
