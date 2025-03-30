from odoo import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    ruian_code = fields.Char("RUIAN Code")
    ruian_coord_x = fields.Float("Coordinate X")
    ruian_coord_y = fields.Float("Coordinate Y")
