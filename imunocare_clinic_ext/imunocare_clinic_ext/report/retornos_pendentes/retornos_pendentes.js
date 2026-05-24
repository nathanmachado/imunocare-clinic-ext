// Copyright (c) 2026, Imunocare
frappe.query_reports["Retornos Pendentes"] = {
	filters: [
		{
			fieldname: "dias_antecedencia",
			label: __("Dias de antecedência"),
			fieldtype: "Int",
			default: 7,
			description: __("Inclui doses vencidas e as que vencem nos próximos N dias."),
		},
		{
			fieldname: "apenas_atrasadas",
			label: __("Apenas atrasadas"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "patient",
			label: __("Paciente"),
			fieldtype: "Link",
			options: "Patient",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "situacao" && data && data.dias_atraso > 0) {
			value = `<span style="color:var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
