import pytest

from src.retrieval.value_parser import parse_value
from src.retrieval.unit_converter import convert
from src.retrieval.requirement_parser import (
    classify_query,
    find_component,
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


@pytest.mark.parametrize(
    ("query", "component"),
    [
        ("Hillrom 900 Accella bed maximum patient weight at least 185 kg", None),
        ("Bed maximum patient weight at least 185 kg", "Bed"),
        ("Maximum patient weight for Bed at least 185 kg", "Bed"),
        ("Maximum lift capacity for Foot section at least 180 kg", "Foot section"),
    ],
)
def test_component_requires_clear_component_syntax(query, component):
    assert find_component(query) == component

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


def test_quoted_inch_value_with_parenthetical_metric_equivalent():
    parsed = parse_value('6" (15 cm)')

    assert parsed["type"] == "mixed"
    assert parsed["raw"] == '6" (15 cm)'
    assert parsed["parsed_value"] == {
        "type": "scalar",
        "value": 6,
        "unit": "inch",
    }
    assert parsed["description"] == "(15 cm)"


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
        "Width above 90 cm": ">",
        "Width greater than 90 cm": ">",
        "Width greater than or equal to 90 cm": ">=",
        "Width at most 90 cm": "<=",
        "Width less than 90 cm": "<",
        "Width below 90 cm": "<",
        "Width less than or equal to 90 cm": "<=",
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


def test_flow_rate_above_query_is_parsed_as_numeric_requirement():
    query = "Show products with flow rate above 100 ml/hr"
    requirement = parse_requirement(query)

    assert requirement["attribute"] == "Flow Rate"
    assert requirement["operator"] == ">"
    assert requirement["value"] == 100
    assert requirement["unit"] == "ml/hr"
    assert requirement["query_type"] == "technical"


def test_permissible_load_is_distinct_and_has_explicit_configuration_scope():
    requirement = parse_requirement(
        "Permissible load for Carbon 1200 in normal patient orientation "
        "at least 150 kg"
    )

    assert requirement["attribute"] == "Permissible Load"
    assert requirement["configuration_scope"] == {
        "configuration_terms": ["Carbon 1200"],
        "orientation": "Normal",
        "chapter": None,
        "item_numbers": [],
        "position_terms": [],
    }
    assert requirement["condition_scope"] is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "Permissible load for Carbon 1200 normal without restrictions "
            "at least 150 kg",
            {"restriction": "none"},
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "longitudinal travel level and inclination no more than 15 degrees, "
            "at least 400 kg",
            {
                "longitudinal_travel": "level",
                "inclination": {
                    "operator": "<=",
                    "value": 15.0,
                    "unit": "degrees",
                },
            },
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "tilted 20 degrees, at least 400 kg",
            {
                "inclination": {
                    "operator": "=",
                    "value": 20.0,
                    "unit": "degrees",
                },
            },
        ),
    ],
)
def test_pst_operating_condition_scope_is_parsed(query, expected):
    requirement = parse_requirement(query)

    assert requirement["condition_scope"] == expected
    assert requirement["value"] == (150 if "150 kg" in query else 400)


def test_unrecognized_pst_operating_condition_is_marked_unsupported():
    requirement = parse_requirement(
        "Permissible load for Carbon 1200 normal orientation with accessory "
        "configuration X at least 150 kg"
    )

    assert requirement["condition_scope"] == {"unsupported": True}


@pytest.mark.parametrize(
    ("condition", "condition_operator"),
    [
        ("inclination =15 degrees", "="),
        ("inclination <15 degrees", "<"),
        ("inclination <=15 degrees", "<="),
        ("inclination >15 degrees", ">"),
        ("inclination >=15 degrees", ">="),
        ("inclination less than 15 degrees", "<"),
        ("inclination no greater than 15 degrees", "<="),
        ("tilt at least 15 degrees", ">="),
        ("inclination exactly 15 degrees", "="),
    ],
)
def test_pst_inclination_comparison_operator_is_preserved(
    condition,
    condition_operator,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{condition}, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"]["operator"] == condition_operator
    assert requirement["condition_scope"]["inclination"]["value"] == 15
    assert requirement["operator"] == ">="
    assert requirement["value"] == 400
    assert requirement["unit"] == "kg"


@pytest.mark.parametrize(
    ("condition_phrase", "expected_condition"),
    [
        ("Trendelenburg position", {"position": "trendelenburg"}),
        ("unevenly loaded", {"load_distribution": "uneven"}),
        ("evenly loaded", {"load_distribution": "even"}),
        ("longitudinal travel not level", {"longitudinal_travel": "not_level"}),
        ("longitudinal travel level", {"longitudinal_travel": "level"}),
        ("non-level tabletop", {"longitudinal_travel": "not_level"}),
        ("level tabletop", {"longitudinal_travel": "level"}),
        ("at 20°", {"inclination": {"operator": "=", "value": 20.0, "unit": "degrees"}}),
        (
            "without limiting operating table functions",
            {"function_restriction": "none"},
        ),
    ],
)
def test_pst_supported_condition_phrases_are_retained(
    condition_phrase,
    expected_condition,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{condition_phrase}, at least 400 kg"
    )

    for key, value in expected_condition.items():
        assert requirement["condition_scope"][key] == value


@pytest.mark.parametrize(
    ("phrase", "expected_conditions", "expected_operator"),
    [
        (
            "inclination <=15 degrees and tilt >=20 degrees",
            [("<=", 15), (">=", 20)],
            "AND",
        ),
        (
            "inclination >=20 degrees and tilt <=15 degrees",
            [(">=", 20), ("<=", 15)],
            "AND",
        ),
        ("tilt <=15 degrees and tilt 20 degrees", [("<=", 15), ("=", 20)], "AND"),
        (
            "inclination <=15 degrees, angle 20 degrees",
            [("<=", 15), ("=", 20)],
            "AND",
        ),
        ("at 20 degrees and at most 15 degrees", [("=", 20), ("<=", 15)], "AND"),
        ("at most 15 degrees and at 20 degrees", [("<=", 15), ("=", 20)], "AND"),
        (
            "inclination 20 degrees or inclination at most 15 degrees",
            [("=", 20), ("<=", 15)],
            "OR",
        ),
        (
            "inclination 20 degrees and inclination 15 degrees or inclination 10 degrees",
            [("=", 20), ("=", 15), ("=", 10)],
            "AMBIGUOUS",
        ),
        (
            "inclination 20 degrees and/or inclination at most 15 degrees",
            [("=", 20), ("<=", 15)],
            "AMBIGUOUS",
        ),
    ],
)
def test_pst_all_inclination_conditions_and_connectors_are_retained(
    phrase,
    expected_conditions,
    expected_operator,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{phrase}, at least 400 kg"
    )
    parsed = requirement["condition_scope"]["inclination"]
    conditions = parsed.get("conditions", [parsed])

    assert [
        (condition["operator"], condition["value"])
        for condition in conditions
    ] == expected_conditions
    if len(conditions) > 1:
        assert parsed["logical_operator"] == expected_operator


def test_pst_single_unqualified_inclination_is_retained_as_equality():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "inclination 20 degrees, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"] == {
        "operator": "=",
        "value": 20.0,
        "unit": "degrees",
    }


@pytest.mark.parametrize(
    ("phrase", "expected_operator"),
    [
        ("inclination should not exceed 14 degrees", "<="),
        ("inclination must not exceed 15 degrees", "<="),
        ("inclination no more than 15 degrees", "<="),
        ("inclination at most 15 degrees", "<="),
        ("inclination at least 15 degrees", ">="),
        ("inclination greater than 15 degrees", ">"),
        ("inclination less than 15 degrees", "<"),
        ("inclination at most 15 degrees", "<="),
        ("inclination no less than 15 degrees", ">="),
        ("inclination not more than 15 degrees", "<="),
        ("inclination not less than 15 degrees", ">="),
        ("inclination exactly 15 degrees", "="),
    ],
)
def test_pst_inclination_language_operators_are_parsed_explicitly(
    phrase,
    expected_operator,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{phrase}, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"]["operator"] == expected_operator
    assert requirement["condition_scope"]["inclination"]["value"] == (
        14.0 if "14 degrees" in phrase else 15.0
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "inclination shouldn't exceed 14 degrees",
        "inclination doesn't exceed 14 degrees",
        "inclination around 14 degrees",
        "inclination no greater 14 degrees",
    ],
)
def test_pst_unsupported_inclination_operator_is_not_defaulted_to_equality(phrase):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{phrase}, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"]["operator"] is None
    assert requirement["condition_scope"]["unsupported"] is True


def test_pst_negated_angle_relation_is_not_treated_as_positive():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "not inclination at most 15 degrees, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"]["operator"] == "<="
    assert requirement["condition_scope"]["unsupported"] is True


def test_pst_unknown_slope_clause_is_retained_as_unsupported_with_angle():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "inclination at most 15 degrees and on an incline, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"]["operator"] == "<="
    assert requirement["condition_scope"]["unsupported"] is True


def test_pst_slope_clause_is_unsupported_even_with_recognized_angle():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "inclination at most 15 degrees and on a slope, at least 400 kg"
    )

    assert requirement["condition_scope"]["inclination"]["operator"] == "<="
    assert requirement["condition_scope"]["unsupported"] is True


def test_pst_conflicting_orientations_are_not_silently_collapsed():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation and "
        "inverted orientation, longitudinal travel level, inclination at "
        "most 15 degrees, evenly loaded, at least 400 kg"
    )

    assert requirement["configuration_scope"]["orientation"] == "Normal"
    assert requirement["configuration_scope"]["orientation_conflict"] is True
    assert requirement["condition_scope"]["unsupported"] is True


@pytest.mark.parametrize(
    ("phrase", "expected_conditions", "expected_operator"),
    [
        (
            "longitudinal travel level or longitudinal travel not level",
            ["level", "not_level"],
            "OR",
        ),
        (
            "longitudinal travel level and longitudinal travel not level",
            ["level", "not_level"],
            "AND",
        ),
    ],
)
def test_pst_travel_condition_alternatives_preserve_connectors(
    phrase,
    expected_conditions,
    expected_operator,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{phrase}, at least 400 kg"
    )

    assert requirement["condition_scope"]["longitudinal_travel"] == {
        "conditions": expected_conditions,
        "logical_operator": expected_operator,
    }


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("evenly loaded", "even"),
        ("evenly-loaded", "even"),
        ("uniformly loaded", "even"),
        ("not evenly loaded", "not_even"),
        ("not-evenly loaded", "not_even"),
        ("not uniformly loaded", "not_even"),
        ("unevenly loaded", "uneven"),
        ("uneven load", "uneven"),
        ("asymmetric load", "uneven"),
        ("asymmetrically loaded", "uneven"),
        ("one-sided loading", "uneven"),
        ("nonuniform load", "uneven"),
        ("non-uniform load", "uneven"),
        ("loaded unevenly", "uneven"),
    ],
)
def test_pst_load_distribution_phrases_preserve_polarity(phrase, expected):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{phrase}, at least 400 kg"
    )

    assert requirement["condition_scope"]["load_distribution"] == expected


def test_conflicting_load_distribution_phrases_are_marked_unsupported():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "evenly loaded and unevenly loaded, at least 400 kg"
    )

    assert requirement["condition_scope"]["unsupported"] is True


def test_load_distribution_or_alternatives_preserve_connector():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "evenly loaded or unevenly loaded, at least 400 kg"
    )

    assert requirement["condition_scope"]["load_distribution"] == {
        "conditions": ["even", "uneven"],
        "logical_operator": "OR",
    }


def test_position_or_alternatives_preserve_connector():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "Trendelenburg position or reverse Trendelenburg position, "
        "at least 400 kg"
    )

    assert requirement["condition_scope"]["position"] == {
        "conditions": ["trendelenburg", "reverse_trendelenburg"],
        "logical_operator": "OR",
    }
    assert "unsupported" not in requirement["condition_scope"]


@pytest.mark.parametrize(
    ("condition_phrase", "expected_polarity"),
    [
        ("longitudinal travel not level", "not_level"),
        ("non-level longitudinal travel", "not_level"),
        ("not level tabletop", "not_level"),
        ("non-level tabletop", "not_level"),
        ("travel non-level", "not_level"),
        ("travel not-level", "not_level"),
        ("not-level tabletop", "not_level"),
        ("tabletop non-level", "not_level"),
        ("tabletop must not be level", "not_level"),
        ("travel must not be level", "not_level"),
        ("travel shall not be level", "not_level"),
        ("travel is not at level", "not_level"),
        ("travel is NOT AT LEVEL", "not_level"),
        ("travel, not-level!", "not_level"),
        ("inclined travel", "not_level"),
        ("longitudinal travel level", "level"),
        ("level longitudinal travel", "level"),
        ("level tabletop", "level"),
    ],
)
def test_pst_level_condition_preserves_negation(
    condition_phrase,
    expected_polarity,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{condition_phrase}, at least 400 kg"
    )

    assert requirement["condition_scope"]["longitudinal_travel"] == expected_polarity


def test_pst_unsupported_tabletop_condition_is_marked_unsupported():
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "sloped tabletop at least 400 kg"
    )

    assert requirement["condition_scope"] == {"unsupported": True}


@pytest.mark.parametrize(
    "condition_phrase",
    [
        "supine",
        "side-lying",
        "on an incline",
        "tabletop on an incline",
    ],
)
def test_pst_unsupported_position_and_slope_conditions_fail_closed(condition_phrase):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{condition_phrase}, at least 400 kg"
    )

    assert requirement["condition_scope"]
    assert requirement["condition_scope"].get("unsupported") is True


def test_permissible_patient_weight_does_not_alias_maximum_patient_weight():
    requirement = parse_requirement(
        "Permissible patient weight for Carbon 600 inverted at least 150 kg"
    )

    assert requirement["attribute"] == "Permissible Load"
    assert requirement["attribute"] != "Maximum Patient Weight"