from src.retrieval.evaluator import evaluate_requirement
from src.retrieval.requirement_parser import parse_requirement


def test_grams_to_kilograms_pass():

    requirement = parse_requirement(
        "Weight should be at most 5 kg"
    )

    result = evaluate_requirement(
        requirement,
        "4000 g"
    )

    assert result == "PASS"


def test_grams_to_kilograms_fail():

    requirement = parse_requirement(
        "Weight should be at most 3 kg"
    )

    result = evaluate_requirement(
        requirement,
        "4000 g"
    )

    assert result == "FAIL"


def test_minutes_to_hours_pass():

    requirement = parse_requirement(
        "Battery backup must be at least 3 hours"
    )

    result = evaluate_requirement(
        requirement,
        "180 minutes"
    )

    assert result == "PASS"


def test_minutes_to_hours_fail():

    requirement = parse_requirement(
        "Battery backup must be at least 4 hours"
    )

    result = evaluate_requirement(
        requirement,
        "180 minutes"
    )

    assert result == "FAIL"


def test_incompatible_units():

    requirement = parse_requirement(
        "Weight should be at most 5 kg"
    )

    result = evaluate_requirement(
        requirement,
        "4 hours"
    )

    assert result == "UNKNOWN"


def test_all_comparison_operators_keep_inclusive_and_exclusive_boundaries():
    cases = [
        ("Width >= 90 cm", "PASS"),
        ("Width > 90 cm", "FAIL"),
        ("Width <= 90 cm", "PASS"),
        ("Width < 90 cm", "FAIL"),
        ("Width = 90 cm", "PASS"),
    ]
    for query, expected in cases:
        assert evaluate_requirement(parse_requirement(query), "90 cm", "Width") == expected


def test_natural_language_operator_boundaries_are_evaluated_correctly():
    queries = [
        ("Width at least 90 cm", "PASS"),
        ("Width more than 90 cm", "FAIL"),
        ("Width at most 90 cm", "PASS"),
        ("Width less than 90 cm", "FAIL"),
        ("Width exactly 90 cm", "PASS"),
    ]
    for query, expected in queries:
        assert evaluate_requirement(parse_requirement(query), "90 cm", "Width") == expected


def test_missing_requirement_unit_does_not_compare_against_a_unitful_value():
    requirement = {
        "attribute": "Weight",
        "operator": "<=",
        "value": 5,
        "unit": None,
    }
    assert evaluate_requirement(requirement, "4 kg", "Weight") == "UNKNOWN"
    assert evaluate_requirement(requirement, "4", "Weight") == "UNKNOWN"


def test_range_compliance_requires_every_permitted_value_to_satisfy_requirement():
    cases = [
        (">=", 50, "50 mm to 100 mm", "PASS"),
        (">=", 80, "50 mm to 100 mm", "UNKNOWN"),
        (">=", 101, "50 mm to 100 mm", "FAIL"),
        ("<=", 100, "50 mm to 100 mm", "PASS"),
        ("<=", 80, "50 mm to 100 mm", "UNKNOWN"),
        ("<=", 49, "50 mm to 100 mm", "FAIL"),
        (">", 50, "50 mm to 100 mm", "UNKNOWN"),
        ("<", 100, "50 mm to 100 mm", "UNKNOWN"),
    ]
    for operator, value, product_range, expected in cases:
        requirement = {
            "attribute": "Width",
            "operator": operator,
            "value": value,
            "unit": "mm",
        }
        assert evaluate_requirement(requirement, product_range, "Width") == expected


def test_recognized_angle_and_rate_units_are_evaluable_in_same_unit():
    assert evaluate_requirement(
        {"attribute": "Angle", "operator": ">=", "value": 10, "unit": "°"},
        "10°",
        "Angle",
    ) == "PASS"


def test_unknown_unit_is_not_assumed_convertible_even_when_spellings_match():
    assert evaluate_requirement(
        {"attribute": "Flow Rate", "operator": "=", "value": 5, "unit": "ml/hr"},
        "5 ml/hr",
        "Flow Rate",
    ) == "UNKNOWN"
    assert evaluate_requirement(
        {"attribute": "Heart Rate", "operator": "=", "value": 70, "unit": "bpm"},
        "70 bpm",
        "Heart Rate",
    ) == "PASS"
    assert evaluate_requirement(
        {"attribute": "Sampling Rate", "operator": "=", "value": 500, "unit": "samples/sec"},
        "500 Samples / Sec",
        "Sampling Rate",
    ) == "PASS"
    assert evaluate_requirement(
        {"attribute": "Heart Rate", "operator": "=", "value": 70, "unit": "bpm"},
        "70 samples/sec",
        "Heart Rate",
    ) == "UNKNOWN"