import pytest

from chemanim.pubchem import morgan_similarity, verify_with_pubchem
from chemanim.spec import MoleculeSpec


def molecule(**overrides):
    data = {
        "name": "溴",
        "canonical_name": "bromine",
        "formula": "Br2",
        "charge": 0,
        "smiles": "BrBr",
        "role": "reactant",
        "show_hydrogens": False,
    }
    data.update(overrides)
    return MoleculeSpec.model_validate(data)


def test_morgan_fingerprint_is_invariant_to_smiles_order():
    assert morgan_similarity("CCO", "OCC") == pytest.approx(1.0)
    assert morgan_similarity("not-smiles", "CCO") is None


def test_pubchem_verification_preserves_formula_digits(monkeypatch):
    def fake_lookup(_name):
        return {
            "CID": 24408,
            "Title": "Bromine",
            "IUPACName": "molecular bromine",
            "MolecularFormula": "Br2",
            "SMILES": "BrBr",
            "InChIKey": "GDTBXPJZTBHREO-UHFFFAOYSA-N",
        }

    monkeypatch.setattr("chemanim.pubchem.lookup_pubchem", fake_lookup)
    item = molecule()
    report = verify_with_pubchem(item)

    assert item.formula == "Br2"
    assert item.smiles == "BrBr"
    assert report["tanimoto_similarity"] == pytest.approx(1.0)
