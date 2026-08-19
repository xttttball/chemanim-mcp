import pytest
from pydantic import ValidationError

from chemanim.spec import MoleculeSpec, SceneSpec, validate_formula_references


def valid_scene(**overrides):
    data = {
        "title": "甲烷燃烧",
        "equation": "CH4 + 2 O2 -> CO2 + 2 H2O",
        "molecules": [
            {
                "name": "甲烷",
                "canonical_name": "methane",
                "formula": "CH4",
                "charge": 0,
                "smiles": "C",
                "role": "reactant",
                "show_hydrogens": True,
            }
        ],
    }
    data.update(overrides)
    return SceneSpec.model_validate(data)


def test_valid_scene():
    assert valid_scene().equation.startswith("CH4")


def test_latex_command_is_rejected():
    with pytest.raises(ValidationError):
        valid_scene(equation=r"CH4 \\input{secret}")


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        MoleculeSpec.model_validate(
            {
                "name": "水",
                "canonical_name": "water",
                "formula": "H2O",
                "charge": 0,
                "smiles": "O",
                "role": "product",
                "show_hydrogens": True,
                "python": "do_something()",
            }
        )


def test_formula_must_appear_in_equation():
    with pytest.raises(ValueError, match="not a species"):
        validate_formula_references(
            valid_scene(
            molecules=[
                {
                    "name": "乙醇",
                    "canonical_name": "ethanol",
                    "formula": "C2H6O",
                    "charge": 0,
                    "smiles": "CCO",
                    "role": "reactant",
                    "show_hydrogens": False,
                }
            ]
            )
        )
