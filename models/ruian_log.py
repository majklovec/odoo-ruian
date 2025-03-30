from odoo import models, fields, api
from odoo.tools.translate import _


class RuianImportLog(models.Model):
    _name = "ruian.log"
    _description = "RUIAN Import Statistics"
    _order = "start_date desc"

    name = fields.Char(string="Import ID", readonly=True, index=True)
    start_date = fields.Datetime(string="Start Time", readonly=True)
    end_date = fields.Datetime(string="End Time", readonly=True)
    rows = fields.Integer(string="Rows", readonly=True)
    towns = fields.Integer(string="Towns", readonly=True)
    streets = fields.Integer(string="Streets", readonly=True)
    numbers = fields.Integer(string="Numbers", readonly=True)
    warnings = fields.Integer(string="Warnings", readonly=True)

    duration = fields.Float(
        string="Duration (Hours)",
        compute="_compute_duration",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [("running", "Running"), ("done", "Done")],
        string="Status",
        compute="_compute_state",
        store=True,
        readonly=True,
    )

    @api.depends("start_date", "end_date")
    def _compute_duration(self):
        for log in self:
            if log.end_date and log.start_date:
                start = fields.Datetime.to_datetime(log.start_date)
                end = fields.Datetime.to_datetime(log.end_date)
                delta = end - start
                log.duration = delta.total_seconds() / 3600  # Convert seconds to hours
            else:
                log.duration = 0.0

    @api.depends("end_date")
    def _compute_state(self):
        for log in self:
            log.state = "done" if log.end_date else "running"
