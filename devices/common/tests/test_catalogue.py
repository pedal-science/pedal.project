"""The block templates, and the check of them against the engine's schema."""

import json
import os
import pathlib
import unittest

from pedald import catalogue

SCHEMA = json.loads((pathlib.Path(__file__).parent / "fixtures" / "engine-schema.json").read_text())


def schema():
    return json.loads(json.dumps(SCHEMA))


def node(document, type_id):
    return next(n for n in document["nodes"] if n["id"] == type_id)


def param(document, type_id, param_id):
    return next(p for p in node(document, type_id)["params"] if p["id"] == param_id)


class Templates(unittest.TestCase):
    def setUp(self):
        self.catalogue = catalogue.Catalogue()

    def block(self, block_id):
        return next(b for b in self.catalogue.blocks if b["id"] == block_id)

    def test_the_27_playable_blocks(self):
        self.assertEqual(len(self.catalogue.blocks), 27)
        self.assertEqual(len({b["id"] for b in self.catalogue.blocks}), 27)

    def test_every_block_fits_the_engine(self):
        self.catalogue.check(schema())
        answer = self.catalogue.answer()
        self.assertEqual(answer["refused"], [])
        self.assertEqual(len(answer["templates"]), 27)
        self.assertTrue(answer["checked"])

    def test_an_interface_only_knob_is_left_out(self):
        controls = {c["id"] for c in self.block("amp.cleanblack")["controls"]}
        self.assertEqual(controls, {"bass", "mid", "treble"})
        self.assertNotIn("slot", {c["id"] for c in self.block("cab.ir")["controls"]})

    def test_a_block_that_needs_a_file_says_which(self):
        self.assertEqual(self.block("amp.cleanblack")["nodes"][0]["assets"], {"model": "model"})
        self.assertEqual(self.block("cab.ir")["nodes"][0]["assets"], {"ir": "ir"})

    def test_a_range_stops_where_the_engine_stops(self):
        time = next(c for c in self.block("delay.tape")["controls"] if c["id"] == "time")
        self.assertEqual((time["min"], time["max"]), (20, 1000))

    def test_an_option_the_engine_lacks_isnt_offered(self):
        slope = next(c for c in self.block("eq.lowcut")["controls"] if c["id"] == "slope")
        self.assertEqual(slope["options"], ["12 dB", "24 dB"])

    def test_every_transform_inverts(self):
        for block in self.catalogue.blocks:
            for control in block["controls"]:
                transform = control["transform"]
                if control["kind"] == "options":
                    for option in control["options"]:
                        back = catalogue.from_engine(transform, catalogue.to_engine(transform, option))
                        self.assertEqual(back, option)
                    continue
                for value in (control["min"], control["default"], control["max"]):
                    back = catalogue.from_engine(transform, catalogue.to_engine(transform, value))
                    self.assertAlmostEqual(back, value, places=9, msg=f"{block['id']}.{control['id']}")

    def test_a_centred_tone_knob_is_flat(self):
        tone = next(c for c in self.block("amp.brit800")["controls"] if c["id"] == "mid")
        self.assertEqual(catalogue.to_engine(tone["transform"], 5), 0)


class Refusing(unittest.TestCase):
    def refused(self, document):
        found = catalogue.Catalogue()
        found.check(document)
        answer = found.answer()
        return {r["id"]: r["reason"] for r in answer["refused"]}, {t["id"] for t in answer["templates"]}

    def test_a_type_the_engine_lacks(self):
        document = schema()
        document["nodes"] = [n for n in document["nodes"] if n["id"] != "fx.eq.tilt"]
        refused, offered = self.refused(document)
        self.assertIn("no type 'fx.eq.tilt'", refused["eq.tilt"])
        self.assertNotIn("eq.tilt", offered)
        self.assertEqual(len(refused), 1)

    def test_a_parameter_the_engine_lacks(self):
        document = schema()
        tilt = node(document, "fx.eq.tilt")
        tilt["params"] = [p for p in tilt["params"] if p["id"] != "freq"]
        self.assertIn("'freq'", self.refused(document)[0]["eq.tilt"])

    def test_a_range_the_engine_narrowed(self):
        document = schema()
        param(document, "fx.delay.feedback", "feedback")["max"] = 0.5
        refused, _ = self.refused(document)
        self.assertIn("feedback", refused["delay.tape"])

    def test_an_option_the_engine_dropped(self):
        document = schema()
        slope = param(document, "fx.filter.cut", "low_slope")
        slope["options"] = [o for o in slope["options"] if o["value"] != "24"]
        self.assertIn("'24'", self.refused(document)[0]["eq.lowcut"])

    def test_an_asset_parameter_the_engine_lacks(self):
        document = schema()
        nam = node(document, "nc.nam")
        nam["params"] = [p for p in nam["params"] if p["id"] != "model"]
        self.assertEqual(len(self.refused(document)[0]), 11)

    def test_before_the_engine_is_asked_nothing_is_refused(self):
        answer = catalogue.Catalogue().answer()
        self.assertFalse(answer["checked"])
        self.assertEqual(len(answer["templates"]), 27)

    def test_no_templates_file_is_an_empty_catalogue(self):
        lines = []
        empty = catalogue.Catalogue(os.path.join(os.path.dirname(__file__), "no-such-file"), log=lines.append)
        self.assertEqual(empty.answer()["templates"], [])
        self.assertIn("no block templates", lines[0])


if __name__ == "__main__":
    unittest.main()
