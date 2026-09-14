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