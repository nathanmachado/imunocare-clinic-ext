// Agenda de Imunização (Fase 10) — filtros, cores e botão de WhatsApp.
// Carregado em runtime pelo report view; não depende de build de assets.

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
			return `<a href="${data.whatsapp}" target="_blank" class="btn btn-xs btn-success"
				style="white-space:nowrap"><i class="fa fa-whatsapp"></i> WhatsApp</a>`;
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
			const cores = {};
			cores[__("Atrasado")] = "red";
			cores[__("Hoje")] = "blue";
			cores[__("Futuro")] = "gray";
			cores[__("Realizado")] = "green";
			cores[__("Cancelado/Falta")] = "gray";
			return `<span class="indicator-pill ${cores[data.situacao] || "gray"}">${value}</span>`;
		}

		if (column.fieldname === "alerta" && data && data.alerta) {
			return `<span style="color:var(--red-500,#e24c4c);font-weight:700">${value}</span>`;
		}

		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Calendário (dia/semana/mês)"), () => {
			frappe.set_route("List", "Patient Appointment", "Calendar");
		});
	},
};
