from copy import deepcopy

import pytest

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


def test_component_mismatch_and_unspecified_component_are_unknown():
    bed_requirement = parse_requirement(
        "Maximum Lift Capacity for Bed at least 200 kg"
    )
    wrong_component = {
        "attribute": "Maximum Lift Capacity",
        "component": "Foot section",
        "raw_value": "500 lbs",
    }
    assert evaluate_requirement(
        bed_requirement,
        "500 lbs",
        candidate=wrong_component,
    ) == "UNKNOWN"

    generic_requirement = parse_requirement(
        "Maximum Lift Capacity at least 200 kg"
    )
    component_evidence = {
        "attribute": "Maximum Lift Capacity",
        "component": "Bed",
        "raw_value": "500 lbs",
    }
    assert evaluate_requirement(
        generic_requirement,
        "500 lbs",
        candidate=component_evidence,
    ) == "UNKNOWN"


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


def test_recognized_flow_unit_is_comparable_and_other_units_keep_existing_behavior():
    assert evaluate_requirement(
        {"attribute": "Flow Rate", "operator": "=", "value": 5, "unit": "ml/hr"},
        "5 ml/hr",
        "Flow Rate",
    ) == "PASS"
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


def test_repeated_scalar_evaluation_does_not_mutate_source_parsed_value():
    candidate = {
        "attribute": "Safe Working Load",
        "raw_value": "250 lb",
        "parsed_value": {"type": "scalar", "value": 250.0, "unit": "lb"},
    }
    original = deepcopy(candidate)
    requirement = {
        "attribute": "Safe Working Load",
        "operator": ">=",
        "value": 100,
        "unit": "kg",
    }

    assert evaluate_requirement(requirement, "", candidate=candidate) == "PASS"
    assert evaluate_requirement(requirement, "", candidate=candidate) == "PASS"
    assert candidate == original


def test_repeated_range_evaluation_does_not_mutate_source_parsed_value():
    candidate = {
        "attribute": "Width",
        "raw_value": "250 to 300 inches",
        "parsed_value": {
            "type": "range",
            "min": 250.0,
            "max": 300.0,
            "unit": "inch",
        },
    }
    original = deepcopy(candidate)
    requirement = {
        "attribute": "Width",
        "operator": ">=",
        "value": 100,
        "unit": "cm",
    }

    assert evaluate_requirement(requirement, "", candidate=candidate) == "PASS"
    assert evaluate_requirement(requirement, "", candidate=candidate) == "PASS"
    assert candidate == original


def test_flow_rate_comparison_preserves_exclusive_boundary_and_converts_units():
    requirement = parse_requirement("Flow rate above 100 ml/hr")

    assert evaluate_requirement(requirement, "100 ml/hr", "Flow Rate") == "FAIL"
    assert evaluate_requirement(requirement, "100.1 ml/hr", "Flow Rate") == "PASS"
    assert evaluate_requirement(requirement, "0.101 l/hr", "Flow Rate") == "PASS"
    assert evaluate_requirement(requirement, "100 V", "Flow Rate") == "UNKNOWN"


def test_malformed_numeric_threshold_does_not_become_a_comparable_requirement():
    requirement = parse_requirement("Flow rate above many ml/hr")
    assert requirement["operator"] == ">"
    assert requirement["value"] is None


def _pst_condition_candidate():
    qualification = (
        "The maximum patient weight applies for an evenly loaded operating "
        "tabletop (surface load). The longitudinal travel of the operating "
        "tabletop must be in the level position. Patient weights up to 454 kg "
        "are permitted with inclination no more than 15 degrees."
    )
    scope = {
        "chapter": "5.11.2 (1)",
        "orientation": "Normal",
        "conditions": qualification,
    }
    return {
        "attribute": "Permissible Load",
        "raw_value": "454 kg / 1000 lbs",
        "scope": scope,
        "source": {
            "scope": scope,
            "qualification_sources": [{"page": 45, "evidence": qualification}],
        },
    }


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ("inclination <=15 degrees and tilt >=20 degrees", "FAIL"),
        ("inclination >=20 degrees and tilt <=15 degrees", "FAIL"),
        ("tilt <=15 degrees and tilt 20 degrees", "FAIL"),
        ("inclination <=15 degrees, angle 20 degrees", "FAIL"),
        ("at 20 degrees and at most 15 degrees", "FAIL"),
        ("at most 15 degrees and at 20 degrees", "FAIL"),
        ("inclination at least 15 degrees", "UNKNOWN"),
        ("inclination at most 15 degrees", "PASS"),
        ("inclination exactly 15 degrees", "PASS"),
        ("inclination 20 degrees", "FAIL"),
        ("inclination 20 degrees or inclination at most 15 degrees", "PASS"),
        (
            "inclination 20 degrees and inclination 15 degrees or inclination 10 degrees",
            "UNKNOWN",
        ),
        (
            "inclination 20 degrees and/or inclination at most 15 degrees",
            "UNKNOWN",
        ),
    ],
)
def test_pst_multiple_and_single_inclination_conditions_evaluate_all_expressions(
    conditions,
    expected,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{conditions}, at least 400 kg"
    )

    assert evaluate_requirement(
        requirement,
        "",
        candidate=_pst_condition_candidate(),
    ) == expected


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ("evenly loaded", "PASS"),
        ("evenly-loaded", "PASS"),
        ("uniformly loaded", "PASS"),
        ("not evenly loaded", "FAIL"),
        ("not-evenly loaded", "FAIL"),
        ("not uniformly loaded", "FAIL"),
        ("unevenly loaded", "FAIL"),
        ("uneven load", "FAIL"),
        ("asymmetric load", "FAIL"),
        ("asymmetrically loaded", "FAIL"),
        ("one-sided loading", "FAIL"),
        ("nonuniform load", "FAIL"),
        ("non-uniform load", "FAIL"),
        ("loaded unevenly", "FAIL"),
        ("radially loaded", "UNKNOWN"),
    ],
)
def test_pst_load_distribution_polarity_is_evaluated_against_source(
    conditions,
    expected,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{conditions}, at least 400 kg"
    )

    assert evaluate_requirement(
        requirement,
        "",
        candidate=_pst_condition_candidate(),
    ) == expected


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("inclination should not exceed 14 degrees", "UNKNOWN"),
        ("inclination must not exceed 15 degrees", "PASS"),
        ("inclination no more than 15 degrees", "PASS"),
        ("inclination at most 15 degrees", "PASS"),
        ("inclination at least 15 degrees", "UNKNOWN"),
        ("inclination not more than 15 degrees", "PASS"),
        ("inclination not less than 15 degrees", "UNKNOWN"),
        ("inclination greater than 15 degrees", "FAIL"),
        ("inclination less than 15 degrees", "UNKNOWN"),
        ("inclination less than 20 degrees", "PASS"),
        ("inclination exactly 15 degrees", "PASS"),
        ("not inclination at most 15 degrees", "UNKNOWN"),
        ("inclination at most 15 degrees and on an incline", "UNKNOWN"),
        ("inclination at most 15 degrees and on a slope", "UNKNOWN"),
    ],
)
def test_pst_angle_operators_and_unsupported_clauses_fail_closed(
    condition,
    expected,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{condition}, at least 400 kg"
    )

    assert evaluate_requirement(
        requirement,
        "",
        candidate=_pst_condition_candidate(),
    ) == expected


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            "longitudinal travel level or longitudinal travel not level",
            "PASS",
        ),
        (
            "longitudinal travel level and longitudinal travel not level",
            "FAIL",
        ),
    ],
)
def test_pst_travel_alternatives_are_evaluated_against_source(
    condition,
    expected,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{condition}, at least 400 kg"
    )

    assert evaluate_requirement(
        requirement,
        "",
        candidate=_pst_condition_candidate(),
    ) == expected


def test_pst_conflicting_source_travel_qualifications_return_unknown():
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {
            "page": 46,
            "evidence": "The longitudinal travel must not be level.",
        }
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "longitudinal travel level, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "UNKNOWN"


def test_pst_conflicting_source_angle_limits_return_unknown():
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {
            "page": 47,
            "evidence": "The operating tabletop inclination is limited to 20 degrees.",
        }
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "inclination at most 15 degrees, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "UNKNOWN"


@pytest.mark.parametrize(
    "evidence",
    [
        "The maximum inclination is 20 degrees.",
        "Inclination up to 20 degrees is permitted.",
        "Inclination must not exceed 20 degrees.",
        "Inclination is limited to 20 degrees.",
    ],
)
def test_pst_source_angle_limit_variants_detect_conflicting_evidence(evidence):
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {"page": 47, "evidence": evidence}
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "inclination at most 15 degrees, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "UNKNOWN"


@pytest.mark.parametrize(
    "evidence",
    [
        "The maximum patient weight applies to a not evenly loaded tabletop.",
        "The maximum patient weight applies to a not-evenly loaded tabletop.",
        "The maximum patient weight applies to a not, under stated conditions, "
        "evenly loaded tabletop.",
    ],
)
def test_pst_negated_source_loading_does_not_override_positive_evidence(evidence):
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {"page": 47, "evidence": evidence}
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "evenly loaded, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "UNKNOWN"


def test_pst_negated_uneven_source_loading_preserves_its_polarity():
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {
            "page": 47,
            "evidence": "The maximum patient weight does not apply to an unevenly "
            "loaded tabletop.",
        }
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "evenly loaded, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "PASS"


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ("evenly loaded or unevenly loaded", "PASS"),
        ("evenly loaded and unevenly loaded", "UNKNOWN"),
    ],
)
def test_pst_load_distribution_connectors_are_evaluated_safely(
    conditions,
    expected,
):
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        f"{conditions}, at least 400 kg"
    )

    assert evaluate_requirement(
        requirement,
        "",
        candidate=_pst_condition_candidate(),
    ) == expected


def test_pst_position_or_alternative_passes_when_source_supports_one_option():
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {
            "page": 47,
            "evidence": "Trendelenburg positioning is available.",
        }
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "Trendelenburg position or reverse Trendelenburg position, "
        "at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "PASS"


def test_pst_conflicting_source_load_distributions_return_unknown():
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {
            "page": 47,
            "evidence": "The permissible load applies to an unevenly loaded tabletop.",
        }
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "evenly loaded, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "UNKNOWN"


def test_pst_positive_and_negated_loading_in_one_qualification_conflict():
    candidate = _pst_condition_candidate()
    candidate["source"]["qualification_sources"].append(
        {
            "page": 47,
            "evidence": "The load is not evenly loaded in one condition and evenly "
            "loaded in another condition.",
        }
    )
    requirement = parse_requirement(
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "evenly loaded, at least 400 kg"
    )

    assert evaluate_requirement(requirement, "", candidate=candidate) == "UNKNOWN"