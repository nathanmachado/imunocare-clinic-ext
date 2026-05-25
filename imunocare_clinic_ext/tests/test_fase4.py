from __future__ import annotations

import base64
import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


def _gerar_pfx(senha: str) -> bytes:
	"""Gera um .pfx auto-assinado de teste (não é um cert ICP-Brasil real)."""
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import rsa
	from cryptography.hazmat.primitives.serialization import pkcs12
	from cryptography.x509.oid import NameOID

	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IMUNOCARE TESTE:12345678000199")])
	now = datetime.datetime.now(datetime.timezone.utc)
	cert = (
		x509.CertificateBuilder()
		.subject_name(name)
		.issuer_name(name)
		.public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(now)
		.not_valid_after(now + datetime.timedelta(days=365))
		.sign(key, hashes.SHA256())
	)
	return pkcs12.serialize_key_and_certificates(
		b"teste", key, cert, None, serialization.BestAvailableEncryption(senha.encode())
	)


def _set_certificate(settings, pfx_bytes: bytes, senha: str):
	file_doc = frappe.get_doc(
		{"doctype": "File", "file_name": "cert_teste.pfx", "is_private": 1, "content": pfx_bytes}
	).insert(ignore_permissions=True)
	settings.certificado_upload = file_doc.file_url
	settings.senha_certificado = senha
	settings.cnes = "1234567"
	settings.save(ignore_permissions=True)
	return file_doc


class TestRNDSSettings(FrappeTestCase):
	def setUp(self):
		self.settings = frappe.get_single("RNDS Settings")
		self.settings.certificado_data = ""
		self.settings.certificado_upload = ""
		self.settings.ambiente = "Homologação"
		self.settings.cnes = "1234567"
		self.settings.url_token = ""
		self.settings.url_ehr = ""
		self.settings.save(ignore_permissions=True)

	def test_doctype_is_single(self):
		self.assertTrue(frappe.get_meta("RNDS Settings").issingle)

	def test_homologacao_endpoints_composed(self):
		self.settings.ambiente = "Homologação"
		self.settings.save(ignore_permissions=True)
		self.assertEqual(self.settings.url_token, "https://ehr-auth-hmg.saude.gov.br/api/token")
		self.assertEqual(self.settings.url_ehr, "https://ehr-services.hmg.saude.gov.br/api/fhir/r4")

	def test_normalize_uf(self):
		from imunocare_clinic_ext.imunocare_clinic_ext.doctype.rnds_settings.rnds_settings import (
			_normalize_uf,
		)

		self.assertEqual(_normalize_uf("Minas Gerais"), "MG")
		self.assertEqual(_normalize_uf("MG"), "MG")
		self.assertEqual(_normalize_uf("são paulo"), "SP")
		self.assertEqual(_normalize_uf("sp"), "SP")
		self.assertEqual(_normalize_uf("Distrito Federal"), "DF")
		self.assertIsNone(_normalize_uf(None))
		self.assertIsNone(_normalize_uf("Xanadu"))

	def test_producao_ehr_por_uf(self):
		from unittest.mock import patch

		with patch.object(type(self.settings), "_detect_uf", return_value="MG"):
			self.settings.ambiente = "Produção"
			self.settings.save(ignore_permissions=True)
		self.assertEqual(self.settings.uf, "MG")
		self.assertEqual(self.settings.url_token, "https://ehr-auth.saude.gov.br/api/token")
		self.assertEqual(self.settings.url_ehr, "https://mg-ehr-services.saude.gov.br/api/fhir/r4")
		# volta para homologação para não afetar outros testes
		with patch.object(type(self.settings), "_detect_uf", return_value="MG"):
			self.settings.ambiente = "Homologação"
			self.settings.save(ignore_permissions=True)

	def test_certificate_encrypted_and_file_removed(self):
		senha = "minhasenha123"
		pfx = _gerar_pfx(senha)
		file_doc = _set_certificate(self.settings, pfx, senha)

		self.settings.reload()
		# certificado_data preenchido e NÃO é o base64 puro (está criptografado)
		self.assertTrue(self.settings.certificado_data)
		self.assertNotEqual(self.settings.certificado_data, base64.b64encode(pfx).decode())
		# upload limpo e arquivo removido (não persiste em disco / por URL)
		self.assertFalse(self.settings.certificado_upload)
		self.assertFalse(frappe.db.exists("File", file_doc.name))
		# metadados extraídos
		self.assertIn("IMUNOCARE TESTE", self.settings.certificado_titular)
		self.assertTrue(self.settings.certificado_validade)

	def test_get_certificate_bytes_roundtrip(self):
		senha = "outrasenha456"
		pfx = _gerar_pfx(senha)
		_set_certificate(self.settings, pfx, senha)
		self.settings.reload()
		recuperado = self.settings.get_certificate_bytes()
		self.assertEqual(recuperado, pfx)

	def test_wrong_password_raises(self):
		pfx = _gerar_pfx("senhacorreta")
		file_doc = frappe.get_doc(
			{"doctype": "File", "file_name": "c.pfx", "is_private": 1, "content": pfx}
		).insert(ignore_permissions=True)
		self.settings.certificado_upload = file_doc.file_url
		self.settings.senha_certificado = "senhaerrada"
		self.settings.cnes = "1234567"
		with self.assertRaises(frappe.ValidationError):
			self.settings.save(ignore_permissions=True)


class TestRNDSClientToken(FrappeTestCase):
	def setUp(self):
		self.settings = frappe.get_single("RNDS Settings")
		senha = "tok123"
		_set_certificate(self.settings, _gerar_pfx(senha), senha)
		self.settings.url_token = "https://ehr-auth-hmg.saude.gov.br/api/token"
		self.settings.save(ignore_permissions=True)
		frappe.cache().delete_value("rnds_access_token")

	def test_token_fetched_and_cached(self):
		from imunocare_clinic_ext import rnds_client

		class FakeResp:
			headers = {"X-Authorization-Server": "Bearer TESTE-TOKEN-123"}
			def raise_for_status(self):
				pass

		with patch.object(rnds_client, "pkcs12_get", return_value=FakeResp()) as mock_get:
			token = rnds_client.get_access_token(force_refresh=True)
			self.assertEqual(token, "TESTE-TOKEN-123")
			# .pfx passado como bytes em memória (nunca arquivo)
			_, kwargs = mock_get.call_args
			self.assertIsInstance(kwargs["pkcs12_data"], bytes)
			self.assertEqual(kwargs["pkcs12_password"], "tok123")

		# Segunda chamada vem do cache (sem nova requisição).
		with patch.object(rnds_client, "pkcs12_get") as mock_get2:
			token2 = rnds_client.get_access_token()
			self.assertEqual(token2, "TESTE-TOKEN-123")
			mock_get2.assert_not_called()


class TestResolveCns(FrappeTestCase):
	def _fake_bundle(self, cns):
		return {
			"resourceType": "Bundle",
			"entry": [
				{
					"resource": {
						"resourceType": "Patient",
						"identifier": [
							{"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf", "value": "52998224725"},
							{"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns", "value": cns},
						],
					}
				}
			],
		}

	def test_resolve_cns_found(self):
		from imunocare_clinic_ext import rnds_client

		class FakeResp:
			def __init__(self, data):
				self._data = data
			def raise_for_status(self):
				pass
			def json(self):
				return self._data

		with patch.object(rnds_client, "ehr_get", return_value=FakeResp(self._fake_bundle("700508547440008"))) as mock:
			cns = rnds_client.resolve_cns("529.982.247-25")
			self.assertEqual(cns, "700508547440008")
			# query montada com o NamingSystem de CPF e CPF normalizado
			_, kwargs = mock.call_args
			self.assertIn("52998224725", kwargs["params"]["identifier"])
			self.assertIn("NamingSystem/cpf", kwargs["params"]["identifier"])

	def test_resolve_cns_not_found(self):
		from imunocare_clinic_ext import rnds_client

		class FakeResp:
			def raise_for_status(self):
				pass
			def json(self):
				return {"resourceType": "Bundle", "entry": []}

		with patch.object(rnds_client, "ehr_get", return_value=FakeResp()):
			self.assertIsNone(rnds_client.resolve_cns("52998224725"))

	def test_resolve_cns_invalid_cpf_no_call(self):
		from imunocare_clinic_ext import rnds_client

		with patch.object(rnds_client, "ehr_get") as mock:
			self.assertIsNone(rnds_client.resolve_cns("123"))
			mock.assert_not_called()
