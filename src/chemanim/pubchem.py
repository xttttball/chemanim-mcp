from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator, rdMolDescriptors

from .spec import MoleculeSpec


PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
MORGAN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


class PubChemLookupError(RuntimeError):
    pass


def morgan_similarity(left_smiles: str, right_smiles: str) -> float | None:
    left = Chem.MolFromSmiles(left_smiles)
    right = Chem.MolFromSmiles(right_smiles)
    if left is None or right is None:
        return None
    return float(
        DataStructs.TanimotoSimilarity(
            MORGAN.GetFingerprint(left), MORGAN.GetFingerprint(right)
        )
    )


def lookup_pubchem(name: str, base_url: str = PUBCHEM_BASE_URL) -> dict:
    properties = "Title,IUPACName,MolecularFormula,SMILES,ConnectivitySMILES,InChIKey"
    url = (
        f"{base_url}/compound/name/{quote(name, safe='')}/property/"
        f"{properties}/JSON"
    )
    request = Request(url, headers={"User-Agent": "chemanim/0.2"})
    try:
        with urlopen(request, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))["PropertyTable"][
                "Properties"
            ]
    except HTTPError as exc:
        raise PubChemLookupError(f"PubChem HTTP {exc.code} for {name}") from exc
    except (URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise PubChemLookupError(f"PubChem lookup failed for {name}: {exc}") from exc
    if not rows:
        raise PubChemLookupError(f"PubChem returned no compound for {name}")
    return rows[0]


def verify_with_pubchem(item: MoleculeSpec) -> dict:
    record = lookup_pubchem(item.canonical_name)
    verified_smiles = record.get("SMILES")
    if not verified_smiles:
        raise PubChemLookupError(
            f"PubChem returned no isomeric SMILES for {item.canonical_name}"
        )
    verified_mol = Chem.MolFromSmiles(verified_smiles)
    if verified_mol is None:
        raise PubChemLookupError(
            f"PubChem returned invalid SMILES for {item.canonical_name}"
        )

    candidate_smiles = item.smiles
    similarity = morgan_similarity(candidate_smiles, verified_smiles)
    item.smiles = Chem.MolToSmiles(verified_mol, isomericSmiles=True)
    calculated_formula = rdMolDescriptors.CalcMolFormula(verified_mol)
    item.formula = re.sub(r"[+-]\d*$", "", calculated_formula)
    item.charge = Chem.GetFormalCharge(verified_mol)

    return {
        "name": item.name,
        "query": item.canonical_name,
        "pubchem_cid": record.get("CID"),
        "pubchem_title": record.get("Title"),
        "pubchem_iupac_name": record.get("IUPACName"),
        "inchi_key": record.get("InChIKey"),
        "candidate_smiles": candidate_smiles,
        "verified_smiles": item.smiles,
        "morgan_radius": 2,
        "morgan_bits": 2048,
        "tanimoto_similarity": None if similarity is None else round(similarity, 6),
        "source": "PubChem PUG REST",
    }


def verify_scene_with_pubchem(items: list[MoleculeSpec]) -> list[dict]:
    reports = []
    for item in items:
        try:
            report = verify_with_pubchem(item)
            similarity = report["tanimoto_similarity"]
            status = "无法计算" if similarity is None else f"{similarity:.3f}"
            print(f"[PubChem] {item.name}: CID {report['pubchem_cid']}, Morgan Tanimoto={status}")
            reports.append(report)
        except PubChemLookupError as exc:
            print(f"[PubChem] {item.name}: 查询失败，保留并本地校验模型结构（{exc}）")
            reports.append(
                {
                    "name": item.name,
                    "query": item.canonical_name,
                    "source": "DeepSeek + local RDKit fallback",
                    "error": str(exc),
                }
            )
    return reports
