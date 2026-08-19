import pytest

from chemanim.chemistry import (
    apply_curated_identity,
    balance_equation_from_molecules,
    build_molecule_3d,
    formula_composition,
    validate_molecules,
    write_molecule_svg,
)
from chemanim.spec import MoleculeSpec


def molecule(**overrides):
    data = {
        "name": "甲烷",
        "canonical_name": "methane",
        "formula": "CH4",
        "charge": 0,
        "smiles": "C",
        "role": "reactant",
        "show_hydrogens": True,
    }
    data.update(overrides)
    return MoleculeSpec.model_validate(data)


def test_formula_parser_handles_condensed_and_groups():
    assert formula_composition("CH3COOH") == {"C": 2, "H": 4, "O": 2}
    assert formula_composition("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}


def test_formula_smiles_mismatch_is_rejected():
    with pytest.raises(ValueError, match="mismatch"):
        validate_molecules([molecule(smiles="C(C)(C)C")])


def test_valid_formula_and_smiles_pass():
    validate_molecules([molecule()])


def test_ionic_formula_and_charge_pass():
    validate_molecules(
        [
            molecule(
                name="铵根",
                formula="NH4",
                charge=1,
                smiles="[NH4+]",
            )
        ]
    )


def test_curated_catalog_corrects_common_model_hallucination():
    item = molecule(smiles="C(C)(C)C")
    assert apply_curated_identity([item]) == ["甲烷"]
    assert item.smiles == "C"
    validate_molecules([item])


def test_name_catalog_disambiguates_isomers():
    item = molecule(
        name="乙醇",
        canonical_name="ethanol",
        formula="C2H6O",
        smiles="COC",
        show_hydrogens=False,
    )
    apply_curated_identity([item])
    assert item.smiles == "CCO"


def test_svg_has_transparent_background(tmp_path):
    destination = tmp_path / "methane.svg"
    write_molecule_svg(molecule(), destination)
    assert "<rect" not in destination.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "formula", "bad_smiles", "expected"),
    [
        ("甲苯", "C7H8", "c1ccccc1", "Cc1ccccc1"),
        ("苯甲醛", "C7H6O", "c1ccc(C=O)c1", "O=Cc1ccccc1"),
    ],
)
def test_aromatic_catalog_corrections(name, formula, bad_smiles, expected):
    item = molecule(
        name=name,
        canonical_name={"甲苯": "toluene", "苯甲醛": "benzaldehyde"}[name],
        formula=formula,
        smiles=bad_smiles,
        show_hydrogens=False,
    )
    apply_curated_identity([item])
    assert item.smiles == expected
    validate_molecules([item])


def test_curated_identity_corrects_ethene_formula_and_smiles():
    item = molecule(
        name="乙烯",
        canonical_name="ethene",
        formula="C2H2",
        smiles="C#C",
        show_hydrogens=False,
    )
    assert apply_curated_identity([item]) == ["乙烯"]
    assert (item.formula, item.charge, item.smiles) == ("C2H4", 0, "C=C")
    validate_molecules([item])


def test_balances_ethene_bromine_addition():
    items = [
        MoleculeSpec(
            name="乙烯",
            canonical_name="ethene",
            formula="C2H4",
            charge=0,
            smiles="C=C",
            role="reactant",
        ),
        MoleculeSpec(
            name="溴",
            canonical_name="bromine",
            formula="Br2",
            charge=0,
            smiles="BrBr",
            role="reactant",
        ),
        MoleculeSpec(
            name="1,2-二溴乙烷",
            canonical_name="1,2-dibromoethane",
            formula="C2H4Br2",
            charge=0,
            smiles="BrCCBr",
            role="product",
        ),
    ]
    assert balance_equation_from_molecules(items) == "C2H4 + Br2 -> C2H4Br2"


def test_balances_methane_combustion():
    items = [
        MoleculeSpec(
            name="甲烷",
            canonical_name="methane",
            formula="CH4",
            charge=0,
            smiles="C",
            role="reactant",
        ),
        MoleculeSpec(
            name="氧气",
            canonical_name="oxygen",
            formula="O2",
            charge=0,
            smiles="O=O",
            role="reactant",
        ),
        MoleculeSpec(
            name="二氧化碳",
            canonical_name="carbon dioxide",
            formula="CO2",
            charge=0,
            smiles="O=C=O",
            role="product",
        ),
        MoleculeSpec(
            name="水",
            canonical_name="water",
            formula="H2O",
            charge=0,
            smiles="O",
            role="product",
        ),
    ]
    assert balance_equation_from_molecules(items) == "CH4 + 2 O2 -> CO2 + 2 H2O"


def test_builds_methane_3d_model_with_explicit_hydrogens():
    model = build_molecule_3d(molecule())
    assert [atom["element"] for atom in model["atoms"]].count("C") == 1
    assert [atom["element"] for atom in model["atoms"]].count("H") == 4
    assert len(model["bonds"]) == 4


def test_3d_model_omits_hydrogens_when_not_requested():
    model = build_molecule_3d(molecule(show_hydrogens=False))
    assert [atom["element"] for atom in model["atoms"]] == ["C"]
    assert model["bonds"] == []
