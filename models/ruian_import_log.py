from odoo import models, fields, api
from odoo.tools.translate import _


class RuianImportLog(models.Model):
    _name = "ruian.import.log"
    _description = "RUIAN Import Statistics"
    _order = "start_date desc"

    name = fields.Char(string="Import ID", readonly=True, index=True)
    start_date = fields.Datetime(string="Start Time", readonly=True)
    end_date = fields.Datetime(string="End Time", readonly=True)
    duration = fields.Float(string="Duration (seconds)", readonly=True)
    processed_rows = fields.Integer(string="Processed Rows", readonly=True)
    created_towns = fields.Integer(string="Created Towns", readonly=True)
    created_streets = fields.Integer(string="Created Streets", readonly=True)
    created_numbers = fields.Integer(string="Created Numbers", readonly=True)
    warnings = fields.Integer(string="Warnings", readonly=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("running", "Running"),
            ("done", "Completed"),
            ("error", "Error"),
        ],
        string="Status",
        readonly=True,
        default="draft",
    )
    error_message = fields.Text(string="Error Details", readonly=True)
    user_id = fields.Many2one("res.users", string="Executed By", readonly=True)
    file_count = fields.Integer(string="Processed Files", readonly=True)
