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
