"""RNDS Settings — configuração segura da integração RNDS (Fase 4 / ADR-0001).

Segurança do certificado A1 (decisão 2026-05-24):
- O .pfx é enviado por um Attach **privado** e temporário. No validate, é lido,
  validado (PKCS12 + senha), criptografado (AES via encryption_key do site) no
  campo ``certificado_data`` e o File original é IMEDIATAMENTE removido.
- O .pfx nunca persiste como arquivo, nunca é acessível por URL.
- A senha fica em campo Password (criptografado em __Auth).
- O material só é descriptografado em memória, no momento do handshake mTLS.
- Acesso ao DocType restrito a System Manager.
"""

from __future__ import annotations

import base64

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt

# Endpoints oficiais por ambiente (editáveis no DocType; defaults sugeridos).
# Homologação é nacional. Em produção o token é nacional, mas o EHR Services é
# por UF — o default abaixo é o de Minas Gerais (mg-), onde a clínica opera;
# ajustar o prefixo da UF se mudar de estado.
DEFAULT_ENDPOINTS = {
	"Homologação": {
		"token": "https://ehr-auth-hmg.saude.gov.br/api/token",
		"ehr": "https://ehr-services.hmg.saude.gov.br/api/fhir/r4",
	},
	"Produção": {
		"token": "https://ehr-auth.saude.gov.br/api/token",
		"ehr": "https://mg-ehr-services.saude.gov.br/api/fhir/r4",
	},
}


class RNDSSettings(Document):
	def validate(self):
		self._apply_default_endpoints()
		if self.certificado_upload:
			self._process_certificate()

	def _apply_default_endpoints(self):
		defaults = DEFAULT_ENDPOINTS.get(self.ambiente, {})
		if not self.url_token:
			self.url_token = defaults.get("token")
		if not self.url_ehr:
			self.url_ehr = defaults.get("ehr")

	def _process_certificate(self):
		"""Lê, valida e criptografa o .pfx; remove o arquivo enviado."""
		from cryptography.hazmat.primitives.serialization import pkcs12

		file_doc = frappe.get_doc("File", {"file_url": self.certificado_upload})
		content = file_doc.get_content()  # bytes do .pfx

		senha = self.get_password("senha_certificado", raise_exception=False) or self.senha_certificado
		if not senha:
			frappe.throw(_("Informe a senha do certificado antes de enviá-lo."))

		try:
			_key, cert, _chain = pkcs12.load_key_and_certificates(content, senha.encode())
		except Exception:
			frappe.throw(_("Certificado ou senha inválidos. Verifique o arquivo .pfx e a senha."))

		if cert is None:
			frappe.throw(_("Não foi possível ler o certificado do arquivo .pfx."))

		# Metadados (não sensíveis) para exibição.
		self.certificado_titular = _subject_cn(cert)
		self.certificado_validade = cert.not_valid_after_utc.date()
		self.certificado_nome = file_doc.file_name

		# Criptografa o conteúdo (base64) com a encryption_key do site.
		self.certificado_data = encrypt(base64.b64encode(content).decode())

		# Remove o arquivo enviado — não deve persistir em disco nem por URL.
		frappe.delete_doc("File", file_doc.name, ignore_permissions=True, force=True)
		self.certificado_upload = ""

	def get_certificate_bytes(self) -> bytes:
		"""Descriptografa e retorna os bytes do .pfx (apenas em memória)."""
		if not self.certificado_data:
			frappe.throw(_("Nenhum certificado configurado no RNDS Settings."))
		return base64.b64decode(decrypt(self.certificado_data))

	@frappe.whitelist()
	def testar_conexao(self):
		"""Obtém um token via mTLS para validar certificado + endpoints."""
		from imunocare_clinic_ext.rnds_client import get_access_token

		get_access_token(force_refresh=True)
		self.db_set("ultima_conexao", frappe.utils.now_datetime())
		return _("Conexão com o RNDS estabelecida com sucesso.")


def _subject_cn(cert) -> str:
	from cryptography.x509.oid import NameOID

	try:
		return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
	except Exception:
		return ""
