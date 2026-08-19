from chemanim.cli import resolve_renderer
from chemanim.deepseek import DeepSeekClient, finalize_equation
from chemanim.spec import MoleculeSpec, SceneSpec


def test_finalize_equation_rebalances_even_when_all_formulas_are_present():
    spec = SceneSpec(
        title="甲烷燃烧",
        equation="CH4 + O2 -> CO2 + H2O",
        molecules=[
            MoleculeSpec(
                name="甲烷",
                canonical_name="methane",
                formula="CH4",
                smiles="C",
                role="reactant",
            ),
            MoleculeSpec(
                name="氧气",
                canonical_name="oxygen",
                formula="O2",
                smiles="O=O",
                role="reactant",
            ),
            MoleculeSpec(
                name="二氧化碳",
                canonical_name="carbon dioxide",
                formula="CO2",
                smiles="O=C=O",
                role="product",
            ),
            MoleculeSpec(
                name="水",
                canonical_name="water",
                formula="H2O",
                smiles="O",
                role="product",
            ),
        ],
    )

    finalize_equation(spec)

    assert spec.equation == "CH4 + 2 O2 -> CO2 + 2 H2O"


def test_scene_planning_uses_fast_non_thinking_json_request(monkeypatch):
    client = DeepSeekClient(api_key="test-key", timeout=7)
    captured = {}

    def fake_request(payload):
        captured.update(payload)
        return {
            "choices": [{"message": {"content": """{
                "title":"甲烷",
                "equation":"CH4 -> CH4",
                "molecules":[{
                    "name":"甲烷","canonical_name":"methane","formula":"CH4",
                    "charge":0,"smiles":"C","role":"reactant","show_hydrogens":false
                }]
            }"""}}]
        }

    monkeypatch.setattr(client, "_request", fake_request)
    client.generate_scene("展示甲烷", "deepseek-v4-flash")

    assert captured["response_format"] == {"type": "json_object"}
    assert captured["thinking"] == {"type": "disabled"}
    assert captured["max_tokens"] == 2000


def test_3d_auto_renderer_uses_opengl():
    assert resolve_renderer("auto", "3d") == "opengl"
    assert resolve_renderer("auto", "2d") == "cairo"
    assert resolve_renderer("cairo", "3d") == "cairo"
