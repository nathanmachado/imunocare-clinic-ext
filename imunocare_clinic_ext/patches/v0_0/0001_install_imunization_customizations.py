"""Patch v0.0 / 0001 — instala customizations do domínio de imunização (Fase 1 / ADR-0001).

Idempotente. Cobertura explícita pra sites que migrarem antes do
``after_migrate`` rodar (raro mas possível em sites com app instalado
manualmente antes desse hook existir).
"""

from imunocare_clinic_ext.install import install_imunization_customizations


def execute():
	install_imunization_customizations()
