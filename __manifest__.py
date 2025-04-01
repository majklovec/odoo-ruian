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
        "views/ruian_log_views.xml",
        "views/ruian_number_views.xml",
        "views/ruian_street_views.xml",
        "views/ruian_town_views.xml",
        "views/ruian_menu.xml",
    ],
    "external_dependencies": {
        "python": [
            "pyproj",
        ]
    },
    "icon": "/ruian/static/description/icon.png",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
