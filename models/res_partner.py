from odoo import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    ruian_code = fields.Char("RUIAN Code")
    # ruian_coord_x = fields.Float("Coordinate X")
    # ruian_coord_y = fields.Float("Coordinate Y")
    # partner_latitude = fields.Float(string='Geo Latitude', digits=(10, 7))
    # partner_longitude = fields.Float(string='Geo Longitude', digits=(10, 7))
