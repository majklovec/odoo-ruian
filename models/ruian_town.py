from odoo import models, fields, api
from odoo.tools.translate import _


class RuianTown(models.Model):
    _name = "ruian.town"
    _description = "RUIAN Towns"
    _order = "name"

    code = fields.Integer(required=True)
    name = fields.Char(required=True)
    postal_code = fields.Char(required=True)

    _sql_constraints = [
        ("code_uniq", "UNIQUE(code)", "Town code must be unique!"),
    ]
