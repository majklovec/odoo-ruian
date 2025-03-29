# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class RuianController(http.Controller):
    @http.route("/ruian/suggest", type="json", auth="user")
    def suggest(self, query, stage, street_id=None):
        if stage == "street":
            return self._suggest_streets(query)
        elif stage == "number_town":
            return self._suggest_numbers_towns(query, street_id)
        return []

    def _suggest_streets(self, query):
        streets = request.env["ruian.street"].search(
            [("name", "ilike", query)], limit=10
        )
        return [
            {"type": "street", "payload": {"id": street.id, "name": street.name}}
            for street in streets
        ]

    def _suggest_numbers_towns(self, query, street_id):
        street = request.env["ruian.street"].browse(int(street_id))
        numbers = request.env["ruian.number"].search(
            [("name", "ilike", query), ("street_ids", "in", [street.id])], limit=50
        )
        return [
            {
                "type": "number_town",
                "payload": {
                    "id": num.id,
                    "number": num.name,
                    "name": num.town_id.name,
                    "zip": num.town_id.postal_code,
                },
            }
            for num in numbers
        ]
