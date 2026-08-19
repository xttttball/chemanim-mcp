from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from manim import (
    BLUE_C,
    DOWN,
    FadeIn,
    GREEN_C,
    GRAY_B,
    LaggedStart,
    Line3D,
    linear,
    OUT,
    RIGHT,
    Rotate,
    Sphere,
    SVGMobject,
    TAU,
    Text,
    ThreeDScene,
    UP,
    VGroup,
    WHITE,
    Write,
)


ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
SPEC = json.loads((BUILD_DIR / "scene.json").read_text(encoding="utf-8"))
FONT = os.environ.get("CHEMANIM_FONT", "Microsoft YaHei")

SUBSCRIPT = str.maketrans("0123456789+-()", "₀₁₂₃₄₅₆₇₈₉₊₋₍₎")

ATOM_COLORS = {
    "H": "#F4F4F4",
    "C": "#909090",
    "N": "#3977FF",
    "O": "#F04444",
    "F": "#42D9A5",
    "P": "#FF9D2E",
    "S": "#F1D33A",
    "Cl": "#48C957",
    "Br": "#A95A3A",
    "I": "#8355B8",
}
ATOM_RADII = {"H": 0.11, "C": 0.18, "N": 0.18, "O": 0.17, "Br": 0.23, "I": 0.25}


def display_equation(value: str) -> str:
    value = value.replace("<->", "⇌").replace("->", "→")
    return " ".join(
        token if token.isdigit() else token.translate(SUBSCRIPT)
        for token in value.split()
    )


def bond_lines(start: np.ndarray, end: np.ndarray, order: int) -> VGroup:
    direction = end - start
    length = np.linalg.norm(direction)
    unit = direction / max(length, 1e-8)
    perpendicular = np.cross(unit, OUT)
    if np.linalg.norm(perpendicular) < 1e-5:
        perpendicular = np.cross(unit, UP)
    perpendicular /= max(np.linalg.norm(perpendicular), 1e-8)
    offsets = {
        1: [0.0],
        2: [-0.045, 0.045],
        3: [-0.075, 0.0, 0.075],
    }[order]
    return VGroup(
        *(
            Line3D(
                start=start + perpendicular * offset,
                end=end + perpendicular * offset,
                thickness=0.025,
                color=GRAY_B,
                resolution=2,
            ).set_stroke(width=0)
            for offset in offsets
        )
    )


def atom_sphere(element: str, position: np.ndarray) -> Sphere:
    color = ATOM_COLORS.get(element, "#D0D0D0")
    return (
        Sphere(
            center=position,
            radius=ATOM_RADII.get(element, 0.2),
            resolution=(3, 6),
        )
        .set_fill(color, opacity=1)
        .set_stroke(width=0)
    )


def molecule_model_3d(item: dict) -> VGroup:
    data = item["model_3d"]
    positions = [np.array(atom["position"], dtype=float) for atom in data["atoms"]]
    bonds = VGroup(
        *(
            bond_lines(positions[bond["begin"]], positions[bond["end"]], bond["order"])
            for bond in data["bonds"]
        )
    )
    atoms = VGroup(
        *(
            atom_sphere(atom["element"], position)
            for atom, position in zip(data["atoms"], positions)
        )
    )
    return VGroup(bonds, atoms)


def molecule_structure(item: dict):
    if SPEC.get("structure_mode", "2d") == "3d":
        return molecule_model_3d(item)
    return SVGMobject(
        str(BUILD_DIR / item["svg"]),
        height=None,
        width=None,
    )


def molecule_card(item: dict, structure) -> VGroup:
    label_color = {
        "reactant": BLUE_C,
        "product": GREEN_C,
    }.get(item["role"], WHITE)
    label = Text(item["name"], font=FONT, font_size=25, color=label_color)
    return VGroup(structure, label).arrange(DOWN, buff=0.12)


class ChemistryScene(ThreeDScene):
    def construct(self) -> None:
        title = Text(SPEC["title"], font=FONT, font_size=42).to_edge(UP)
        equation = Text(
            display_equation(SPEC["equation"]),
            font=FONT,
            font_size=42,
        ).next_to(title, DOWN, buff=0.45)
        if equation.width > 13.2:
            equation.scale_to_fit_width(13.2)

        molecule_structures = [molecule_structure(item) for item in SPEC["molecules"]]
        if SPEC.get("structure_mode", "2d") == "2d":
            common_scale = min(
                2.25 / max(structure.width for structure in molecule_structures),
                1.75 / max(structure.height for structure in molecule_structures),
            )
            for structure in molecule_structures:
                structure.scale(common_scale)
                if structure.width < 0.55:
                    structure.scale_to_fit_width(0.55)
        else:
            for structure in molecule_structures:
                structure.scale_to_fit_width(2.25)
                if structure.height > 1.75:
                    structure.scale_to_fit_height(1.75)

        cards = [
            (item, molecule_card(item, structure))
            for item, structure in zip(SPEC["molecules"], molecule_structures)
        ]
        reactants = VGroup(*(card for item, card in cards if item["role"] == "reactant"))
        products = VGroup(*(card for item, card in cards if item["role"] == "product"))
        others = VGroup(
            *(
                card
                for item, card in cards
                if item["role"] not in {"reactant", "product"}
            )
        )

        groups = []
        if len(reactants):
            reactants.arrange(RIGHT, buff=0.55)
            groups.append(reactants)
        if len(products):
            products.arrange(RIGHT, buff=0.55)
            groups.append(products)
        if len(others):
            others.arrange(RIGHT, buff=0.35)
            groups.append(others)

        structures = VGroup(*groups).arrange(RIGHT, buff=0.9)
        if structures.width > 12.2:
            structures.scale_to_fit_width(12.2)
        if structures.height > 3.5:
            structures.scale_to_fit_height(3.5)
        structures.next_to(equation, DOWN, buff=0.65)

        self.play(Write(title))
        self.play(Write(equation))
        self.play(
            LaggedStart(
                *(FadeIn(group, shift=UP * 0.18) for group in groups),
                lag_ratio=0.25,
            )
        )
        if SPEC.get("structure_mode", "2d") == "3d":
            self.add_fixed_in_frame_mobjects(
                title,
                equation,
                *(card[1] for _, card in cards),
            )
            self.play(
                *(Rotate(card[0], angle=TAU, axis=UP) for _, card in cards),
                run_time=3,
                rate_func=linear,
            )
        else:
            self.wait(2)
