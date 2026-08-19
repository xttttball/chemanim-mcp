from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# mhchem supports much more syntax, but this deliberately excludes backslashes,
# percent signs, and other characters that could turn model output into LaTeX code.
SAFE_EQUATION = re.compile(r"^[A-Za-z0-9+\-<>=()\[\]{}^_.,·*/\s]+$")


class MoleculeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    canonical_name: str = Field(
        min_length=1,
        max_length=100,
        description="English IUPAC or conventional chemical name used internally",
    )
    formula: str = Field(
        min_length=1,
        max_length=80,
        description="The molecular formula as written in the equation, without charge or state",
    )
    charge: int = Field(default=0, ge=-8, le=8)
    smiles: str = Field(min_length=1, max_length=300)
    role: Literal["reactant", "product", "catalyst", "other"]
    show_hydrogens: bool = False


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    equation: str = Field(min_length=1, max_length=300)
    molecules: list[MoleculeSpec] = Field(min_length=1, max_length=6)

    @field_validator("equation")
    @classmethod
    def equation_must_be_safe(cls, value: str) -> str:
        if not SAFE_EQUATION.fullmatch(value):
            raise ValueError(
                "equation contains unsupported characters or LaTeX commands"
            )
        return value.strip()

def validate_formula_references(spec: SceneSpec) -> None:
    """Check references after the curated identity catalog has corrected them."""
    for molecule in spec.molecules:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(molecule.formula)}(?![A-Za-z0-9])"
        if not re.search(pattern, spec.equation):
            raise ValueError(
                f"{molecule.name} formula {molecule.formula} is not a species in equation"
            )
