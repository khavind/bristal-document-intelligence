import pytest

from src.retrieval.value_parser import parse_value
from src.retrieval.unit_converter import convert
from src.retrieval.requirement_parser import (
    classify_query,
    find_value_and_unit,
    parse_requirement,
)


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


def test_parser_normalizes_spaced_and_compound_units():

    parsed = parse_value("1-1000 ml / hr")
    assert parsed["type"] == "range"
    assert parsed["unit"] == "ml/hr"

    parsed = parse_value("500 Samples / Sec")
    assert parsed["type"] == "scalar"
    assert parsed["unit"] == "samples/sec"

    parsed = parse_value("10 to 40 °C")
    assert parsed["type"] == "range"
    assert parsed["unit"] == "°C"

def test_two_dimension_value():
    parsed = parse_value("372 mm x 311 mm")

    assert parsed["type"] == "compound"
    assert parsed["values"] == [372, 311]
    assert parsed["unit"] == "mm"
    assert parsed["separator"] == "x"


def test_three_dimension_value():
    parsed = parse_value("916 mm x 527 mm x 25 mm")

    assert parsed["type"] == "compound"
    assert parsed["values"] == [916, 527, 25]
    assert parsed["unit"] == "mm"
    assert parsed["separator"] == "x"


def test_paired_angle_value():
    parsed = parse_value("45°/45°")

    assert parsed["type"] == "paired"
    assert parsed["values"] == [45, 45]
    assert parsed["unit"] == "°"
    assert parsed["separator"] == "/"


def test_paired_angle_values_with_spaces():
    parsed = parse_value("30° / 30°")

    assert parsed["type"] == "paired"
    assert parsed["values"] == [30, 30]
    assert parsed["unit"] == "°"
    assert parsed["separator"] == "/"

def test_multiple_values_with_slash():
    parsed = parse_value("25/50 mm/sec")

    assert parsed["type"] == "multiple"
    assert parsed["values"] == [25, 50]
    assert parsed["unit"] == "mm/sec"


def test_symbolic_operators_preserve_operator_and_query_classification():
    expected = {
        ">=": ">=",
        ">": ">",
        "<=": "<=",
        "<": "<",
        "=": "=",
    }
    for symbol, operator in expected.items():
        requirement = parse_requirement(f"Width {symbol} 90 cm")
        assert requirement["operator"] == operator
        assert requirement["query_type"] == "technical"


def test_natural_language_operators_preserve_operator():
    cases = {
        "Width at least 90 cm": ">=",
        "Width more than 90 cm": ">",
        "Width at most 90 cm": "<=",
        "Width less than 90 cm": "<",
        "Width exactly 90 cm": "=",
        "Width equal to 90 cm": "=",
    }
    for query, operator in cases.items():
        assert parse_requirement(query)["operator"] == operator


@pytest.mark.parametrize(
    ("operator_text", "operator"),
    [
        (">=", ">="),
        (">", ">"),
        ("<=", "<="),
        ("<", "<"),
        ("=", "="),
        ("at least", ">="),
        ("more than", ">"),
        ("at most", "<="),
        ("less than", "<"),
        ("exactly", "="),
    ],
)
def test_comparison_value_is_parsed_after_operator_not_from_model_number(
    operator_text, operator
):
    requirement = parse_requirement(
        f"Hillrom 900 Accella bed safe working load {operator_text} 200 kg"
    )
    assert requirement["attribute"] == "Safe Working Load"
    assert requirement["operator"] == operator
    assert requirement["value"] == 200
    assert requirement["unit"] == "kg"


def test_short_unit_symbols_require_word_boundaries():
    assert find_value_and_unit("at least 5 months") == (5.0, None)
    assert find_value_and_unit("at least 5 mammals") == (5.0, None)
    assert find_value_and_unit("at least 5 m") == (5.0, "m")
    assert find_value_and_unit("at least 5 meters") == (5.0, "m")
    assert find_value_and_unit("at least 5 mm") == (5.0, "mm")


def test_symbolic_comparisons_do_not_match_inside_other_tokens():
    assert classify_query("The width is < 90 cm") == "technical"
    assert classify_query("The table supports Trendelenburg") == "capability"