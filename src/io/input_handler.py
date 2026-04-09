import json
from pathlib import Path

from src.database.db_query import get_section, get_material, get_design_standard
from src.models.section import Section
from src.models.material import Material
from src.models.design_standard import DesignStandard
from src.models.beam import Beam
from src.models.column import Column
from src.models.storey import Storey
from src.models.building import Building


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


def load_module1_input(filename="input_module1.json"):
    filepath = DATA_DIR / filename
    with open(filepath, "r") as f:
        data = json.load(f)
    return data


def build_building_from_module1(data):
    design = DesignStandard(*get_design_standard(data["design_standard"]))

    storeys = []

    for s in data["storeys"]:
        beam_section_data = get_section(s["beam_section"])
        column_section_data = get_section(s["column_section"])

        if beam_section_data is None:
            raise ValueError(f"Beam section not found: {s['beam_section']}")
        if column_section_data is None:
            raise ValueError(f"Column section not found: {s['column_section']}")

        beam_section = Section(*beam_section_data)
        beam_material = Material(*get_material(s["beam_grade"]))

        column_section = Section(*column_section_data)
        column_material = Material(*get_material(s["column_grade"]))

        beam = Beam(beam_section, beam_material, length=data["span"], storey=s["level"])
        col_left = Column(column_section, column_material, length=s["height"], storey=s["level"])
        col_right = Column(column_section, column_material, length=s["height"], storey=s["level"])

        storey = Storey(
            level=s["level"],
            height=s["height"],
            dead_load=s["dead_load"],
            live_load=s["live_load"],
            beam=beam,
            column_left=col_left,
            column_right=col_right
        )

        storeys.append(storey)

    building = Building(
        num_storeys=data["num_storeys"],
        span=data["span"],
        storeys=storeys
    )

    return building, design