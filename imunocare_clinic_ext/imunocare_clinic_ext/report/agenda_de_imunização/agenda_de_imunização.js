// Agenda de Imunização (Fase 10) — filtros, cores, WhatsApp→CRM e largura total.
// Carregado em runtime pelo report view; não depende de build de assets.

// Abre (ou cria, no clique) o Lead do paciente no CRM e navega até a conversa.
function imunocare_abrir_lead_crm(patient) {
	if (!patient) return;
	frappe.dom.freeze(__("Abrindo conversa no CRM..."));
	frappe.call({
		method: "imunocare_crm_custom.api.patient.lead_do_paciente",
		args: { patient },
		callback: (r) => {
			frappe.dom.unfreeze();
			if (r.message) {
				window.open(`/crm/leads/${r.message}`, "_blank");
			}
		},
		error: () => frappe.dom.unfreeze(),
	});
}

frappe.query_reports["Agenda de Imunização"] = {
	filters: [
		{
			fieldname: "periodo",
			label: __("Período"),
			fieldtype: "Select",
			options: ["Hoje", "Esta semana", "Este mês", "Personalizado"].join("\n"),
			default: "Esta semana",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("De"),
			fieldtype: "Date",
			depends_on: "eval:doc.periodo == 'Personalizado'",
		},
		{
			fieldname: "to_date",
			label: __("Até"),
			fieldtype: "Date",
			depends_on: "eval:doc.periodo == 'Personalizado'",
		},
		{
			fieldname: "modalidade",
			label: __("Modalidade"),
			fieldtype: "Select",
			options: ["", "Clínica", "Domiciliar"].join("\n"),
		},
		{
			fieldname: "patient",
			label: __("Paciente"),
			fieldtype: "Link",
			options: "Patient",
		},
		{
			fieldname: "somente_pagos_atrasados",
			label: __("Só pagos e atrasados ⚠"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "whatsapp" && data && data.whatsapp) {
			// data.whatsapp carrega o paciente; o clique resolve o Lead no CRM.
			const p = frappe.utils.escape_html(data.whatsapp);
			return `<button type="button" class="btn btn-xs btn-success imun-wa-crm"
				data-patient="${p}" style="white-space:nowrap">
				<i class="fa fa-whatsapp"></i> WhatsApp</button>`;
		}

		if (column.fieldname === "estoque" && data && data.estoque != null) {
			const cor = data.estoque <= 0 ? "red" : data.estoque <= 5 ? "orange" : "green";
			return `<span style="color:var(--text-on-${cor === 'green' ? 'green' : cor}, ${cor});font-weight:600">${value}</span>`;
		}

		if (column.fieldname === "pago" && data) {
			const cor = data.pago === __("Pago") ? "green" : "orange";
			return `<span class="indicator-pill ${cor}">${value}</span>`;
		}

		if (column.fieldname === "situacao" && data) {
			// "Pago e atrasado" é o alerta crítico: ⚠ + vermelho, dobrado aqui
			// (em vez de uma coluna Alerta separada que ficava quase sempre vazia).
			if (data.pago_atrasado) {
				return `<span class="indicator-pill red" title="${__("Pago e atrasado")}"
					style="font-weight:700">⚠ ${value}</span>`;
			}
			const cores = {};
			cores[__("Atrasado")] = "red";
			cores[__("Hoje")] = "blue";
			cores[__("Futuro")] = "gray";
			cores[__("Realizado")] = "green";
			cores[__("Cancelado")] = "gray";
			return `<span class="indicator-pill ${cores[data.situacao] || "gray"}">${value}</span>`;
		}

		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Calendário (dia/semana/mês)"), () => {
			frappe.set_route("List", "Patient Appointment", "Calendar");
		});

		// Largura total (mesma classe do toggle nativo do Frappe). Removida ao
		// sair da rota do report para não vazar para outras páginas.
		if (!document.body.classList.contains("full-width")) {
			document.body.classList.add("full-width");
			report._imun_added_fullwidth = true;
		}
		frappe.router.on("change", function _imun_restore() {
			if ((frappe.get_route_str() || "").indexOf("Agenda de Imuniza") === -1) {
				if (report._imun_added_fullwidth) {
					document.body.classList.remove("full-width");
				}
			}
		});

		// Botão WhatsApp → abre o Lead do paciente no CRM (delegação: sobrevive
		// ao re-render do datatable a cada refresh/filtro).
		$(report.page.wrapper)
			.off("click.imunwa")
			.on("click.imunwa", ".imun-wa-crm", function () {
				imunocare_abrir_lead_crm($(this).data("patient"));
			});
	},

	// Faz a tabela preencher a altura disponível mesmo com poucas linhas.
	after_datatable_render(datatable) {
		const $sc = $(datatable.wrapper).find(".dt-scrollable");
		if ($sc.length) $sc.css("min-height", "calc(100vh - 230px)");
	},
};
