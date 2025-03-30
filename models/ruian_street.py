from odoo import models, fields, api
from odoo.tools.translate import _


class RuianStreet(models.Model):
    _name = "ruian.street"
    _description = "RUIAN Streets"
    _order = "name"

    name = fields.Char(required=True)

    town_ids = fields.Many2many("ruian.town", string="Associated Towns")
    number_ids = fields.Many2many("ruian.number", string="House Numbers")

    _sql_constraints = [
        ("name_uniq", "UNIQUE(name)", "Street name must be unique!"),
    ]
