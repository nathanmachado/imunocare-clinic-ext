// Copyright (c) 2026, Imunocare
frappe.ui.form.on("RNDS Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Testar Conexão"), () => {
			frappe.confirm(
				__("Autenticar no RNDS ({0}) usando o certificado configurado?", [frm.doc.ambiente]),
				() => {
					frm.call("testar_conexao")
						.then((r) => {
							frappe.show_alert({ message: r.message, indicator: "green" });
							frm.reload_doc();
						});
				}
			);
		});

		frm.add_custom_button(__("Testar envio RIA"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Testar envio de imunização (RIA) — homologação"),
				fields: [
					{ fieldname: "cns_paciente", label: __("CNS do paciente (teste)"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "codigo_imunobiologico", label: __("Código do imunobiológico (BRImunobiologico)"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "lote", label: __("Lote"), fieldtype: "Data", default: "LOTE-TESTE-001" },
					{ fieldname: "fabricante", label: __("Fabricante"), fieldtype: "Data", default: "Fabricante Teste" },
					{ fieldname: "dose_numero", label: __("Dose nº"), fieldtype: "Data", default: "1" },
					{ fieldname: "cns_profissional", label: __("CNS do profissional"), fieldtype: "Data" },
					{ fieldname: "estrategia", label: __("Estratégia de vacinação (código)"), fieldtype: "Data", default: "2" },
					{ fieldname: "grupo_atendimento", label: __("Grupo de atendimento (código)"), fieldtype: "Data" },
				],
				primary_action_label: __("Enviar ao RNDS"),
				primary_action(values) {
					frappe.call({
						method: "imunocare_clinic_ext.rnds_immunization.testar_envio_ria",
						args: values,
						freeze: true,
						freeze_message: __("Enviando ao RNDS..."),
						callback: (r) => {
							const res = r.message || {};
							const pretty = JSON.stringify(res.response || res.error, null, 2);
							frappe.msgprint({
								title: __("Resposta do RNDS (HTTP {0})", [res.status_code || "—"]),
								message: `<pre style="max-height:400px;overflow:auto">${frappe.utils.escape_html(pretty)}</pre>`,
								indicator: res.status_code && res.status_code < 300 ? "green" : "red",
							});
						},
					});
				},
			});
			d.show();
		});

		if (frm.doc.certificado_nome) {
			frm.dashboard.add_comment(
				__("Certificado: {0} · Titular: {1} · Válido até {2}", [
					frm.doc.certificado_nome,
					frm.doc.certificado_titular || "—",
					frappe.datetime.str_to_user(frm.doc.certificado_validade) || "—",
				]),
				"blue",
				true
			);
		}
	},
});
