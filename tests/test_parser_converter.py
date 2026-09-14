import pytest

from src.retrieval.value_parser import parse_value
from src.retrieval.unit_converter import convert


def test_grams_to_kilograms():

    parsed = parse_value("4000 g")

    assert parsed["type"] == "scalar"
    assert parsed["value"] == 4000
    assert parsed["unit"] == "g"

    converted = convert(
        parsed["value"],
        parsed["unit"],
        "kg"
    )

    assert converted == pytest.approx(4)


def test_hours_to_minutes():

    parsed = parse_value("2 hours")

    assert parsed["type"] == "scalar"
    assert parsed["value"] == 2
    assert parsed["unit"] == "hours"

    converted = convert(
        parsed["value"],
        parsed["unit"],
        "minutes"
    )

    assert converted == pytest.approx(120)


def test_centimeters_to_meters():

    parsed = parse_value("100 cm")

    assert parsed["type"] == "scalar"
    assert parsed["value"] == 100
    assert parsed["unit"] == "cm"

    converted = convert(
        parsed["value"],
        parsed["unit"],
        "m"
    )

    assert converted == pytest.approx(1)


def test_unit_alias_from_parser():

    parsed = parse_value("4000 KG")

    assert parsed["type"] == "scalar"
    assert parsed["value"] == 4000
    assert parsed["unit"] == "kg"

    converted = convert(
        parsed["value"],
        parsed["unit"],
        "g"
    )

    assert converted == pytest.approx(4000000)