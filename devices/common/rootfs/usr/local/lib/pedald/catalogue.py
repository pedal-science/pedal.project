"""The block templates the pedal offers, and whether this engine can play them.

docs/pedal-service.md, "The catalogue". `templates.json` is written by ljoss's
`Tools/export-templates` and is the blocks' one home. Each is checked against `engine.schema` when
the engine connects, and one that doesn't fit is listed under `refused` with the reason, rather than
offered and then refused when somebody adds it.
"""

import json
import os

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json")


def to_engine(transform, value):
    """A control's value as the engine's. An option the map doesn't have is a KeyError."""
    kind = transform["kind"]
    if kind == "direct":
        return value
    if kind == "knob_decibels":
        return (value - 5) / 5 * transform["span"]
    if kind == "knob_fraction":
        return value / 10 * transform["top"]
    if kind == "knob_attenuation":
        return transform["floor"] - value / 10 * transform["floor"]
    if kind == "multiplied":
        return value * transform["by"]
    if kind == "option":
        return transform["map"][value]
    raise ValueError(f"unknown transform {kind!r}")


def from_engine(transform, value):
    """The other way, so a knob's position comes from the engine's value and nothing else is kept."""
    kind = transform["kind"]
    if kind == "direct":
        return value
    if kind == "knob_decibels":
        return value / transform["span"] * 5 + 5
    if kind == "knob_fraction":
        return value / transform["top"] * 10
    if kind == "knob_attenuation":
        return (transform["floor"] - value) / transform["floor"] * 10
    if kind == "multiplied":
        return value / transform["by"]
    if kind == "option":
        for picked, engine_value in transform["map"].items():
            if engine_value == value:
                return picked
        raise KeyError(value)
    raise ValueError(f"unknown transform {kind!r}")


def _in_range(param, value):
    low, high = param.get("min"), param.get("max")
    if low is not None and (value < low or (value == low and param.get("min_inclusive") is False)):
        return False
    if high is not None and (value > high or (value == high and param.get("max_inclusive") is False)):
        return False
    return True


def _control_problem(control, param):
    transform = control["transform"]
    if control["kind"] == "options":
        if param.get("kind") != "option":
            return f"'{param['id']}' is not a choice on this engine"
        have = {option.get("value") for option in param.get("options") or ()}
        for option in control["options"]:
            if to_engine(transform, option) not in have:
                return f"the engine has no '{to_engine(transform, option)}' for '{param['id']}'"
        return None
    if param.get("kind") != "number":
        return f"'{param['id']}' is not a number on this engine"
    for value in (control["min"], control["default"], control["max"]):
        engine_value = to_engine(transform, value)
        if not _in_range(param, engine_value):
            return (f"{control['id']} at {value:g} is {engine_value:g} for '{param['id']}', "
                    f"outside {param.get('min')}..{param.get('max')}")
    return None


def problem(block, types):
    """Why this engine can't play a block, or None. `types` is engine.schema's nodes by id."""
    nodes = {}
    for node in block["nodes"]:
        schema = types.get(node["type"])
        if schema is None:
            return f"the engine has no type '{node['type']}'"
        params = {param["id"]: param for param in schema.get("params") or ()}
        nodes[node["slot"]] = params
        for name in list(node["fixed"]) + list(node["assets"]):
            if name not in params:
                return f"'{node['type']}' has no parameter '{name}'"
    for control in block["controls"]:
        param = nodes.get(control["slot"], {}).get(control["param"])
        if param is None:
            return f"{control['id']} goes to '{control['param']}', which the engine doesn't have"
        found = _control_problem(control, param)
        if found:
            return found
    return None


class Catalogue:
    def __init__(self, path=TEMPLATES, log=None):
        self.log = log or (lambda _message: None)
        self.blocks = []
        self.checked = False
        self.refused = {}
        self.types = {}
        try:
            with open(path, encoding="utf-8") as handle:
                self.blocks = json.load(handle)["blocks"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.log(f"no block templates: cannot read {path}: {exc}")

    def check(self, schema):
        """Judge every block against an `engine.schema` reply."""
        types = {node["id"]: node for node in schema.get("nodes") or ()}
        self.types = types
        refused = {}
        for block in self.blocks:
            found = problem(block, types)
            if found:
                refused[block["id"]] = found
                self.log(f"catalogue: refusing {block['id']}: {found}")
        self.refused = refused
        self.checked = True

    def param(self, type_id, param_id):
        """A parameter as the engine last described it, or None."""
        for param in (self.types.get(type_id) or {}).get("params") or ():
            if param.get("id") == param_id:
                return param
        return None

    def answer(self):
        """`GET /catalogue`. Before the engine has been asked, `checked` is false."""
        return {"format": 1, "checked": self.checked,
                "templates": [block for block in self.blocks if block["id"] not in self.refused],
                "refused": [{"id": block["id"], "name": block["name"],
                             "reason": self.refused[block["id"]]}
                            for block in self.blocks if block["id"] in self.refused]}
