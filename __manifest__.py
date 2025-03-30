{
    "name": "RUIAN",
    "version": "1.0",
    "summary": "Addresses with RUIAN",
    "description": """
        Add RUIAN code
    """,
    "category": "Users",
    "author": "Michal Vondráček",
    "website": "https://www.optimal4.cz",
    "depends": ["base", "web", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/res_partner_views.xml",
        "views/ruian_views.xml",
        "views/ruian_import_log_views.xml",
    ],
    "icon": "/ruian/static/description/icon.png",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
