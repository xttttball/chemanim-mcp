from __future__ import annotations

from pathlib import Path
import re
from itertools import product

import numpy as np

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from .spec import MoleculeSpec


# Formula-only entries are limited to species with an unambiguous elementary
# structure. Isomers are resolved only by an explicit name alias below.
CURATED_BY_FORMULA: dict[tuple[str, int], str] = {
    ("H2", 0): "[H][H]",
    ("O2", 0): "O=O",
    ("O3", 0): "[O-][O+]=O",
    ("N2", 0): "N#N",
    ("H2O", 0): "O",
    ("NH3", 0): "N",
    ("CH4", 0): "C",
    ("CO", 0): "[C-]#[O+]",
    ("CO2", 0): "O=C=O",
    ("HCl", 0): "Cl",
    ("Br2", 0): "BrBr",
}

CURATED_BY_NAME: dict[str, str] = {
    "methane": "C",
    "甲烷": "C",
    "ethane": "CC",
    "乙烷": "CC",
    "ethene": "C=C",
    "ethylene": "C=C",
    "乙烯": "C=C",
    "ethyne": "C#C",
    "acetylene": "C#C",
    "乙炔": "C#C",
    "ethanol": "CCO",
    "ethyl alcohol": "CCO",
    "乙醇": "CCO",
    "dimethyl ether": "COC",
    "二甲醚": "COC",
    "methanol": "CO",
    "甲醇": "CO",
    "acetic acid": "CC(=O)O",
    "ethanoic acid": "CC(=O)O",
    "乙酸": "CC(=O)O",
    "醋酸": "CC(=O)O",
    "benzene": "c1ccccc1",
    "苯": "c1ccccc1",
    "toluene": "Cc1ccccc1",
    "methylbenzene": "Cc1ccccc1",
    "甲苯": "Cc1ccccc1",
    "benzaldehyde": "O=Cc1ccccc1",
    "苯甲醛": "O=Cc1ccccc1",
    "bromine": "BrBr",
    "溴": "BrBr",
    "溴气": "BrBr",
    "1,2-dibromoethane": "BrCCBr",
    "ethylene dibromide": "BrCCBr",
    "1,2-二溴乙烷": "BrCCBr",
    "glucose": "OCC1OC(O)C(O)C(O)C1O",
    "葡萄糖": "OCC1OC(O)C(O)C(O)C1O",
}


CURATED_IDENTITY_BY_NAME: dict[str, tuple[str, int, str]] = {
    "ethene": ("C2H4", 0, "C=C"),
    "ethylene": ("C2H4", 0, "C=C"),
    "乙烯": ("C2H4", 0, "C=C"),
    "bromine": ("Br2", 0, "BrBr"),
    "溴": ("Br2", 0, "BrBr"),
    "溴气": ("Br2", 0, "BrBr"),
    "1,2-dibromoethane": ("C2H4Br2", 0, "BrCCBr"),
    "ethylene dibromide": ("C2H4Br2", 0, "BrCCBr"),
    "1,2-二溴乙烷": ("C2H4Br2", 0, "BrCCBr"),
}


def apply_curated_identity(items: list[MoleculeSpec]) -> list[str]:
    """Replace model guesses with audited formula, charge, and SMILES data."""
    corrected: list[str] = []
    for item in items:
        names = [item.canonical_name.strip().casefold(), item.name.strip().casefold()]
        identity = next(
            (CURATED_IDENTITY_BY_NAME[name] for name in names if name in CURATED_IDENTITY_BY_NAME),
            None,
        )
        if identity is not None:
            formula, charge, smiles = identity
            if (item.formula, item.charge, item.smiles) != identity:
                item.formula = formula
                item.charge = charge
                item.smiles = smiles
                corrected.append(item.name)
            continue

        curated = next(
            (CURATED_BY_NAME[name] for name in names if name in CURATED_BY_NAME),
            None,
        )
        if curated is None:
            curated = CURATED_BY_FORMULA.get((item.formula.replace(" ", ""), item.charge))
        if curated is not None and item.smiles != curated:
            item.smiles = curated
            corrected.append(item.name)
    return corrected


def parse_molecule(item: MoleculeSpec) -> Chem.Mol:
    mol = Chem.MolFromSmiles(item.smiles)
    if mol is None:
        raise ValueError(f"{item.name} 的 SMILES 无法解析：{item.smiles}")
    if item.show_hydrogens:
        mol = Chem.AddHs(mol)
    return mol


def formula_composition(formula: str) -> dict[str, int]:
    """Parse an ordinary molecular formula, including repeated groups."""
    stack: list[dict[str, int]] = [{}]
    index = 0
    while index < len(formula):
        char = formula[index]
        if char == "(":
            stack.append({})
            index += 1
            continue
        if char == ")":
            if len(stack) == 1:
                raise ValueError(f"unmatched ')' in formula {formula}")
            index += 1
            end = index
            while end < len(formula) and formula[end].isdigit():
                end += 1
            multiplier = int(formula[index:end] or "1")
            group = stack.pop()
            for element, count in group.items():
                stack[-1][element] = stack[-1].get(element, 0) + count * multiplier
            index = end
            continue
        if char.isupper():
            end = index + 1
            if end < len(formula) and formula[end].islower():
                end += 1
            element = formula[index:end]
            number_end = end
            while number_end < len(formula) and formula[number_end].isdigit():
                number_end += 1
            count = int(formula[end:number_end] or "1")
            stack[-1][element] = stack[-1].get(element, 0) + count
            index = number_end
            continue
        raise ValueError(f"unsupported character {char!r} in formula {formula}")

    if len(stack) != 1:
        raise ValueError(f"unclosed group in formula {formula}")
    return stack[0]


def balance_equation_from_molecules(items: list[MoleculeSpec]) -> str | None:
    """Find small positive integer coefficients using elemental/charge conservation."""
    reactants = [item for item in items if item.role == "reactant"]
    products_ = [item for item in items if item.role == "product"]
    species = reactants + products_
    if not reactants or not products_ or len(species) > 6:
        return None

    compositions = [formula_composition(item.formula) for item in species]
    elements = sorted({element for comp in compositions for element in comp})
    split = len(reactants)
    best: tuple[int, ...] | None = None

    for coefficients in product(range(1, 9), repeat=len(species)):
        balanced = all(
            sum(coefficients[i] * compositions[i].get(element, 0) for i in range(split))
            == sum(
                coefficients[i] * compositions[i].get(element, 0)
                for i in range(split, len(species))
            )
            for element in elements
        )
        if not balanced:
            continue
        left_charge = sum(
            coefficients[i] * species[i].charge for i in range(split)
        )
        right_charge = sum(
            coefficients[i] * species[i].charge
            for i in range(split, len(species))
        )
        if left_charge != right_charge:
            continue
        if best is None or (sum(coefficients), coefficients) < (sum(best), best):
            best = coefficients

    if best is None:
        return None

    def side_text(start: int, end: int) -> str:
        parts = []
        for coefficient, item in zip(best[start:end], species[start:end]):
            prefix = "" if coefficient == 1 else f"{coefficient} "
            parts.append(prefix + item.formula)
        return " + ".join(parts)

    return f"{side_text(0, split)} -> {side_text(split, len(species))}"


def validate_molecules(items: list[MoleculeSpec]) -> None:
    for item in items:
        mol = parse_molecule(item)
        calculated_formula = rdMolDescriptors.CalcMolFormula(mol)
        expected = formula_composition(item.formula)
        neutral_formula = re.sub(r"[+-]\d*$", "", calculated_formula)
        calculated = formula_composition(neutral_formula)
        if expected != calculated:
            raise ValueError(
                f"{item.name} formula/SMILES mismatch: expected {item.formula}, "
                f"but {item.smiles} is {calculated_formula}"
            )
        calculated_charge = Chem.GetFormalCharge(mol)
        if item.charge != calculated_charge:
            raise ValueError(
                f"{item.name} charge/SMILES mismatch: expected {item.charge}, "
                f"but {item.smiles} has charge {calculated_charge}"
            )


def write_molecule_svg(item: MoleculeSpec, destination: Path) -> None:
    mol = parse_molecule(item)
    rdDepictor.Compute2DCoords(mol)

    drawer = rdMolDraw2D.MolDraw2DSVG(600, 420)
    options = drawer.drawOptions()
    options.addStereoAnnotation = True
    options.bondLineWidth = 2.4
    options.padding = 0.08
    options.clearBackground = False
    options.setBackgroundColour((0.0, 0.0, 0.0, 0.0))
    options.symbolColour = (0.92, 0.92, 0.92)
    options.updateAtomPalette(
        {
            1: (0.92, 0.92, 0.92),
            6: (0.92, 0.92, 0.92),
            7: (0.25, 0.55, 1.0),
            8: (1.0, 0.3, 0.3),
            9: (0.3, 0.9, 0.75),
            15: (1.0, 0.6, 0.15),
            16: (1.0, 0.85, 0.15),
            17: (0.3, 0.85, 0.35),
            35: (0.75, 0.35, 0.2),
            53: (0.65, 0.4, 0.9),
        }
    )
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(drawer.GetDrawingText(), encoding="utf-8")


def build_molecule_3d(item: MoleculeSpec) -> dict:
    """Generate a deterministic, optimized 3D ball-and-stick model."""
    base = Chem.MolFromSmiles(item.smiles)
    if base is None:
        raise ValueError(f"{item.name} 的 SMILES 无法解析：{item.smiles}")
    mol = Chem.AddHs(base)

    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = 0xC0FFEE
    status = AllChem.EmbedMolecule(mol, parameters)
    if status != 0:
        rdDepictor.Compute2DCoords(mol)
    elif mol.GetNumAtoms() > 2:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            AllChem.MMFFOptimizeMolecule(mol, maxIters=300)
        else:
            AllChem.UFFOptimizeMolecule(mol, maxIters=300)

    conformer = mol.GetConformer()
    coordinates = np.array(
        [
            [
                conformer.GetAtomPosition(index).x,
                conformer.GetAtomPosition(index).y,
                conformer.GetAtomPosition(index).z,
            ]
            for index in range(mol.GetNumAtoms())
        ],
        dtype=float,
    )
    coordinates -= coordinates.mean(axis=0)
    span = float(np.max(np.ptp(coordinates, axis=0))) if len(coordinates) > 1 else 1.0
    coordinates *= 2.2 / max(span, 0.5)

    visible_indices = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if item.show_hydrogens or atom.GetAtomicNum() != 1
    ]
    output_index = {source: target for target, source in enumerate(visible_indices)}
    atoms = [
        {
            "element": mol.GetAtomWithIdx(index).GetSymbol(),
            "position": [round(float(value), 5) for value in coordinates[index]],
        }
        for index in visible_indices
    ]
    bonds = [
        {
            "begin": output_index[bond.GetBeginAtomIdx()],
            "end": output_index[bond.GetEndAtomIdx()],
            "order": max(1, min(3, int(round(bond.GetBondTypeAsDouble())))),
        }
        for bond in mol.GetBonds()
        if bond.GetBeginAtomIdx() in output_index and bond.GetEndAtomIdx() in output_index
    ]
    return {"atoms": atoms, "bonds": bonds}


def build_assets(spec, build_dir: Path, structure_mode: str = "2d") -> dict:
    data = spec.model_dump()
    data["structure_mode"] = structure_mode
    assets_dir = build_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for index, (molecule, output) in enumerate(zip(spec.molecules, data["molecules"])):
        if structure_mode == "3d":
            output["model_3d"] = build_molecule_3d(molecule)
        else:
            relative_path = Path("assets") / f"molecule_{index}.svg"
            write_molecule_svg(molecule, build_dir / relative_path)
            output["svg"] = relative_path.as_posix()

    return data
