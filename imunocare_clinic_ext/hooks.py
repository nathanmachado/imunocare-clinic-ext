app_name = "imunocare_clinic_ext"
app_title = "Imunocare Clinic Ext"
app_publisher = "Imunocare"
app_description = "Extensão do Frappe Healthcare: calendário PNI BR e cartão de vacinas"
app_email = "tech@imunocare.com.br"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "imunocare_clinic_ext",
# 		"logo": "/assets/imunocare_clinic_ext/logo.png",
# 		"title": "Imunocare Clinic Ext",
# 		"route": "/imunocare_clinic_ext",
# 		"has_permission": "imunocare_clinic_ext.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/imunocare_clinic_ext/css/imunocare_clinic_ext.css"
# app_include_js = "/assets/imunocare_clinic_ext/js/imunocare_clinic_ext.js"

# include js, css files in header of web template
# web_include_css = "/assets/imunocare_clinic_ext/css/imunocare_clinic_ext.css"
# web_include_js = "/assets/imunocare_clinic_ext/js/imunocare_clinic_ext.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "imunocare_clinic_ext/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "imunocare_clinic_ext/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "imunocare_clinic_ext.utils.jinja_methods",
# 	"filters": "imunocare_clinic_ext.utils.jinja_filters"
# }

# Installation
# ------------

after_install = "imunocare_clinic_ext.install.after_install"
after_migrate = "imunocare_clinic_ext.install.after_migrate"

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			["dt", "in", [
				"Medication", "Therapy Plan Template", "Therapy Plan Template Detail",
				"Patient", "Drug Prescription", "Patient Appointment",
			]],
			["fieldname", "in", [
				# Medication (Fase 1)
				"imun_section", "is_vaccine", "codigo_rnds", "tipo_imunizacao",
				"imun_col_break", "via_administracao_padrao", "local_anatomico_padrao",
				"obrigatoria_pni", "pni_idade_meses_inicio",
				# Therapy Plan Template (+ Detail) (Fase 1)
				"is_pni", "versao_pni",
				"medication", "dose_numero", "intervalo_dias_min", "idade_meses_ideal",
				# Patient (Fase 2)
				"cpf", "cns",
				# Drug Prescription (Fase 2)
				"lote", "fabricante", "validade_lote",
				"local_anatomico_aplicado", "via_administracao_aplicada",
				"rnds_status", "rnds_id", "rnds_payload",
				# Patient Appointment (Fase 2)
				"imun_modalidade", "imun_application_address_display",
			]],
		],
	},
	{
		"dt": "Property Setter",
		"filters": [
			["doc_type", "=", "Patient"],
			["field_name", "=", "uid"],
			["property", "=", "hidden"],
		],
	},
]

# Uninstallation
# ------------

# before_uninstall = "imunocare_clinic_ext.uninstall.before_uninstall"
# after_uninstall = "imunocare_clinic_ext.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "imunocare_clinic_ext.utils.before_app_install"
# after_app_install = "imunocare_clinic_ext.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "imunocare_clinic_ext.utils.before_app_uninstall"
# after_app_uninstall = "imunocare_clinic_ext.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "imunocare_clinic_ext.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Patient": {
		"validate": "imunocare_clinic_ext.patient_hooks.validate",
	},
	"Patient Appointment": {
		"before_save": "imunocare_clinic_ext.appointment_hooks.before_save",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"imunocare_clinic_ext.tasks.all"
# 	],
# 	"daily": [
# 		"imunocare_clinic_ext.tasks.daily"
# 	],
# 	"hourly": [
# 		"imunocare_clinic_ext.tasks.hourly"
# 	],
# 	"weekly": [
# 		"imunocare_clinic_ext.tasks.weekly"
# 	],
# 	"monthly": [
# 		"imunocare_clinic_ext.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "imunocare_clinic_ext.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "imunocare_clinic_ext.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "imunocare_clinic_ext.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["imunocare_clinic_ext.utils.before_request"]
# after_request = ["imunocare_clinic_ext.utils.after_request"]

# Job Events
# ----------
# before_job = ["imunocare_clinic_ext.utils.before_job"]
# after_job = ["imunocare_clinic_ext.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"imunocare_clinic_ext.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

