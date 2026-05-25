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
import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt

# Endpoints nacionais (token em ambos os ambientes; EHR só em homologação).
_AUTH = {
	"Homologação": "https://ehr-auth-hmg.saude.gov.br/api/token",
	"Produção": "https://ehr-auth.saude.gov.br/api/token",
}
_EHR_HMG = "https://ehr-services.hmg.saude.gov.br/api/fhir/r4"
# Produção: EHR Services é por UF → https://{uf}-ehr-services.saude.gov.br/...
_EHR_PROD_TMPL = "https://{uf}-ehr-services.saude.gov.br/api/fhir/r4"

# Nome do estado (pt-BR, sem acento, minúsculo) → sigla UF.
_UF_POR_NOME = {
	"acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
	"ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
	"maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
	"minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
	"pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
	"rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
	"roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
	"tocantins": "TO",
}
_SIGLAS = set(_UF_POR_NOME.values())


class RNDSSettings(Document):
	def validate(self):
		self._compose_endpoints()
		if self.certificado_upload:
			self._process_certificate()

	def _compose_endpoints(self):
		"""Detecta a UF do endereço da empresa e compõe os endpoints RNDS."""
		self.uf = self._detect_uf() or ""
		self.url_token = _AUTH.get(self.ambiente, "")
		if self.ambiente == "Homologação":
			self.url_ehr = _EHR_HMG
		elif self.uf:
			self.url_ehr = _EHR_PROD_TMPL.format(uf=self.uf.lower())
		else:
			self.url_ehr = ""
			frappe.msgprint(
				_("Não foi possível detectar a UF do endereço da empresa. "
				  "Cadastre o estado no endereço da Company para compor o endpoint de produção."),
				indicator="orange",
				alert=True,
			)

	def _detect_uf(self) -> str | None:
		"""UF (sigla) a partir do endereço primário da Company."""
		company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
		if not company:
			return None
		address_names = frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
			pluck="parent",
		)
		if not address_names:
			return None
		addresses = frappe.get_all(
			"Address",
			filters={"name": ("in", address_names)},
			fields=["state", "is_primary_address"],
			order_by="is_primary_address desc",
		)
		for addr in addresses:
			uf = _normalize_uf(addr.get("state"))
			if uf:
				return uf
		return None

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


def _normalize_uf(state: str | None) -> str | None:
	"""Converte o estado do Address (sigla ou nome, com/sem acento) na sigla UF."""
	if not state:
		return None
	raw = state.strip()
	if len(raw) == 2 and raw.upper() in _SIGLAS:
		return raw.upper()
	sem_acento = "".join(
		c for c in unicodedata.normalize("NFKD", raw.lower()) if not unicodedata.combining(c)
	)
	return _UF_POR_NOME.get(sem_acento)
