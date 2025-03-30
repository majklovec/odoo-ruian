from odoo import models, fields, api
from odoo.tools.translate import _


class RuianNumber(models.Model):
    _name = "ruian.number"
    _description = "RUIAN Numbers"
    _order = "name desc"

    code = fields.Integer(required=True)
    name = fields.Char(required=True)
    coord_x = fields.Float(digits=(9, 6))
    coord_y = fields.Float(digits=(9, 6))

    town_id = fields.Many2one("ruian.town", string="Town")
    street_ids = fields.Many2many("ruian.street", string="Streets")

    full_address = fields.Char(compute="_compute_full_address")

    _sql_constraints = [
        ("code_uniq", "UNIQUE(code)", "Number code must be unique!"),
    ]

    def _compute_full_address(self):
        for record in self:
            streets = ", ".join(record.street_ids.mapped("name"))
            towns = ", ".join(record.town_ids.mapped("name"))
            record.full_address = f"{record.name}, {streets}, {towns}"
