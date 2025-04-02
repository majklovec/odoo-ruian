# -*- coding: utf-8 -*-
import logging
import requests
import zipfile
import csv
from pyproj import Transformer
from io import BytesIO, TextIOWrapper
from datetime import datetime, timedelta
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RuianImport(models.Model):
    _name = "ruian.import"
    _description = "RUIAN Data Import"
    _transformer = Transformer.from_crs("EPSG:5514", "EPSG:4326", always_xy=True)

    @api.model
    def _register_hook(self):
        """Set 'running' logs to 'failed' on server restart."""
        res = super(RuianImport, self)._register_hook()
        logs = self.env["ruian.log"].search([("state", "=", "running")])
        if logs:
            logs.write({"state": "failed"})
            self.env.cr.commit()
        return res

    def _get_number_name(self, record):
        domovni = record.get("Číslo domovní", "").strip()
        orient_number = record.get("Číslo orientační", "").strip()
        orient_letter = record.get("Číslo orientační písmeno", "").strip()

        if orient_number:
            return f"{domovni}/{orient_number}{orient_letter}".strip()
        return domovni if domovni else _("Unknown")

    def _get_town_name(self, record):
        town = record.get("Název obce", "").strip()
        part = record.get("Název části obce", "").strip()

        if part and part != town:
            return f"{town} - {part}"
        return town

    def _convert_to_gps(self, x_str, y_str):
        """Convert coordinates from EPSG:5514 to EPSG:4326."""
        try:
            x, y = float(x_str), float(y_str)
            lon, lat = self._transformer.transform(x, y)
            return lat, lon
        except (ValueError, TypeError) as e:
            _logger.warning("Coordinate conversion error: %s", str(e))
            return 0.0, 0.0

    def _calculate_target_date(self):
        today = fields.Date.today()
        return (
            (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            - timedelta(days=1)
        ).strftime("%Y%m%d")

    def run_ruian_import(self):
        """Main import method with optimized memory usage."""
        _logger.info("=== Starting RUIAN import ===")
        start_time = datetime.now()
        target_date = self._calculate_target_date()

        log = self.env["ruian.log"].create(
            {
                "name": target_date,
                "state": "running",
                "start_date": fields.Datetime.now(),
            }
        )

        try:
            zip_file = self._download_zip(target_date)
            file_count = sum(
                1 for f in zip_file.infolist() if f.filename.endswith(".csv")
            )
            log.file_count = file_count

            global_stats = {
                "towns": 0,
                "towns_created": 0,
                "towns_updated": 0,
                "streets": 0,
                "streets_created": 0,
                "streets_updated": 0,
                "numbers": 0,
                "numbers_created": 0,
                "numbers_updated": 0,
                "rows": 0,
                "warnings": 0,
                "files": 0,
            }

            for zip_info in zip_file.infolist():
                if not zip_info.filename.endswith(".csv"):
                    continue

                _logger.info("Processing file: %s", zip_info.filename)
                file_start = datetime.now()

                try:
                    with zip_file.open(zip_info) as csv_file:
                        reader = csv.DictReader(
                            TextIOWrapper(csv_file, encoding="windows-1250"),
                            delimiter=";",
                        )
                        rows = list(reader)
                        self._process_csv_bulk(rows, global_stats, log)

                    duration = (datetime.now() - file_start).total_seconds()
                    _logger.info(
                        "Processed %d rows in %.2f seconds", len(rows), duration
                    )
                    global_stats["files"] += 1

                except Exception as e:
                    _logger.error(
                        "Error processing file %s: %s", zip_info.filename, str(e)
                    )
                    global_stats["warnings"] += 1
                    continue

            total_duration = (datetime.now() - start_time).total_seconds()
            log.write(
                {
                    "state": "done",
                    "end_date": fields.Datetime.now(),
                    "files": global_stats["files"],
                    "duration": total_duration,
                }
            )
            self.env.cr.commit()

            stats = (
                global_stats["files"],
                global_stats["rows"],
                global_stats["towns"],
                global_stats["towns_created"],
                global_stats["towns_updated"],
                global_stats["streets"],
                global_stats["streets_created"],
                global_stats["streets_updated"],
                global_stats["numbers"],
                global_stats["numbers_created"],
                global_stats["numbers_updated"],
                total_duration,
            )

            message_template = (
                "Import completed: "
                "%d files, %d rows, "
                "%d towns (%d created, %d updated), "
                "%d streets (%d created, %d updated, "
                "%d numbers (%d created, %d updated) in %.2f seconds"
            )

            _logger.info(message_template % stats)

        except Exception as e:
            self.env.cr.rollback()
            log.write(
                {
                    "state": "failed",
                    "end_date": fields.Datetime.now(),
                    "error_message": str(e)[:500],
                }
            )
            self.env.cr.commit()
            _logger.error("Import failed: %s", str(e))
            raise UserError(_("Import failed: %s") % str(e)) from e

        return True

    def _process_csv_bulk(self, rows, global_stats, log):
        """Process CSV rows with memory-optimized chunks."""
        # Process towns and streets first
        town_codes, town_data_map, street_names, street_town_map = (
            self._collect_geo_data(rows)
        )
        town_cache = self._process_towns(town_codes, town_data_map, global_stats)
        street_cache = self._process_streets(
            street_names, street_town_map, town_cache, global_stats
        )

        # Process numbers in memory-optimized chunks
        chunk_size = 10000
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            self._process_number_chunk(chunk, town_cache, street_cache, global_stats)

            # Commit progress every 10k rows
            if i % chunk_size == 0:
                self.env.cr.commit()
                log.write(global_stats)
                _logger.info("Committed progress after %d rows", i + chunk_size)

        # Final commit for remaining records
        self.env.cr.commit()

    def _collect_geo_data(self, rows):
        """Collect geographical data in a single pass."""
        town_codes = set()
        town_data_map = {}
        street_names = set()
        street_town_map = defaultdict(set)

        for row in rows:
            # Collect town data
            town_code_str = row.get("Kód části obce")
            if town_code_str:
                town_code = int(town_code_str)
                town_codes.add(town_code)
                if town_code not in town_data_map:
                    town_data_map[town_code] = {
                        "name": self._get_town_name(row),
                        "postal_code": row.get("PSČ", "").strip(),
                    }

            # Collect street data
            street_name = row.get("Název ulice", "").strip()
            if street_name:
                street_names.add(street_name)
                if town_code_str:
                    town_code = int(town_code_str)
                    street_town_map[street_name].add(town_code)

        return town_codes, town_data_map, street_names, street_town_map

    def _process_towns(self, town_codes, town_data_map, global_stats):
        """Process towns in bulk with created/updated counts."""
        existing_towns = self.env["ruian.town"].search(
            [("code", "in", list(town_codes))]
        )
        town_cache = {t.code: t for t in existing_towns}
        missing_town_codes = town_codes - town_cache.keys()

        created = 0
        if missing_town_codes:
            towns_to_create = []
            for code in missing_town_codes:
                data = town_data_map.get(code)
                if data:
                    towns_to_create.append(
                        {
                            "code": code,
                            "name": data["name"],
                            "postal_code": data["postal_code"],
                        }
                    )
            if towns_to_create:
                created_towns = self.env["ruian.town"].create(towns_to_create)
                created = len(created_towns)
                town_cache.update({town.code: town for town in created_towns})

        global_stats["towns_created"] += created
        global_stats["towns_updated"] += len(town_codes) - created
        global_stats["towns"] += created

        return town_cache

    def _process_streets(self, street_names, street_town_map, town_cache, global_stats):
        """Process streets with created/updated counts."""
        existing_streets = self.env["ruian.street"].search(
            [("name", "in", list(street_names))]
        )
        street_cache = {street.name: street for street in existing_streets}
        missing_streets = street_names - street_cache.keys()

        created = 0
        if missing_streets:
            created_streets = self.env["ruian.street"].create(
                [{"name": name} for name in missing_streets]
            )
            created = len(created_streets)
            street_cache.update({street.name: street for street in created_streets})

        # Track street-town relation updates
        street_updates = []
        for street_name, town_codes_in_street in street_town_map.items():
            street = street_cache.get(street_name)
            if street:
                town_ids = [
                    town_cache[tc].id for tc in town_codes_in_street if tc in town_cache
                ]
                existing_ids = set(street.town_ids.ids)
                new_ids = set(town_ids) - existing_ids
                if new_ids:
                    street_updates.append((street.id, new_ids))

        # Batch update street-town relations
        for street_id, new_town_ids in street_updates:
            street = self.env["ruian.street"].browse(street_id)
            street.write({"town_ids": [(4, tid) for tid in new_town_ids]})

        global_stats["streets_created"] += created
        global_stats["streets_updated"] += len(street_names) - created
        global_stats["streets"] += created

        return street_cache

    def _process_number_chunk(self, chunk, town_cache, street_cache, global_stats):
        """Process a chunk of number records."""
        numbers_data = []
        for row in chunk:
            code_str = row.get("Kód ADM", "").strip()
            if not code_str:
                continue

            number_data = {
                "code": int(code_str),
                "name": self._get_number_name(row),
                "lat": 0.0,
                "lon": 0.0,
                "town_id": None,
                "street_id": None,
            }

            # Resolve town
            town_code_str = row.get("Kód části obce")
            if town_code_str:
                town_code = int(town_code_str)
                number_data["town_id"] = town_cache.get(
                    town_code, self.env["ruian.town"]
                ).id

            # Resolve street
            street_name = row.get("Název ulice", "").strip()
            if street_name:
                number_data["street_id"] = street_cache.get(
                    street_name, self.env["ruian.street"]
                ).id

            # Coordinates
            x, y = row.get("Souřadnice X"), row.get("Souřadnice Y")
            if x and y:
                number_data["lat"], number_data["lon"] = self._convert_to_gps(x, y)

            numbers_data.append(number_data)

        # Process numbers in bulk
        existing_numbers = self.env["ruian.number"].search(
            [("code", "in", [n["code"] for n in numbers_data])]
        )
        existing_number_map = {num.code: num for num in existing_numbers}
        to_create = [n for n in numbers_data if n["code"] not in existing_number_map]
        to_update = [n for n in numbers_data if n["code"] in existing_number_map]

        created = 0
        if to_create:
            self.env["ruian.number"].create(to_create)
            created = len(to_create)
            global_stats["numbers"] += created

        updated = 0
        for data in to_update:
            num = existing_number_map[data["code"]]
            num.write(data)
            updated += 1

        global_stats["numbers_created"] += created
        global_stats["numbers_updated"] += updated
        global_stats["rows"] += len(chunk)

    def _download_zip(self, target_date):
        """Secure ZIP file download"""
        url = f"https://vdp.cuzk.gov.cz/vymenny_format/csv/{target_date}_OB_ADR_csv.zip"
        _logger.info("Downloading ZIP from: %s", url)

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            zip_file = zipfile.ZipFile(BytesIO(response.content))
            if corrupt := zip_file.testzip():
                raise zipfile.BadZipFile(f"Corrupt file: {corrupt}")

            _logger.info("Downloaded valid ZIP archive")
            return zip_file

        except requests.RequestException as e:
            _logger.error("Download failed: %s", str(e))
            raise UserError(_("Download failed: %s") % str(e)) from e
        except zipfile.BadZipFile as e:
            _logger.error("Invalid ZIP file: %s", str(e))
            raise UserError(_("Invalid ZIP archive")) from e
