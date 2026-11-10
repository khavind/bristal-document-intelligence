# from value_parser import parse_value
# from unit_converter import convert
import re
from copy import deepcopy

from src.retrieval.requirement_parser import (
    attributes_equivalent,
    normalize_component,
)
from src.retrieval.value_parser import parse_value
from src.retrieval.unit_converter import convert


def evaluate_condition_compatibility(requirement, candidate):
    """Evaluate explicit operating conditions against qualified source evidence."""
    requested = requirement.get("condition_scope")
    candidate_source = (
        candidate.get("source") if isinstance(candidate, dict) else None
    )
    candidate_scope = (
        candidate.get("scope") if isinstance(candidate, dict) else None
    )
    if not isinstance(candidate_scope, dict) and isinstance(candidate_source, dict):
        candidate_scope = candidate_source.get("scope")
    if _has_position_dependent_capacity_qualification(
        candidate,
        candidate_scope,
        candidate_source,
    ):
        requested_position = (
            requested.get("position") if isinstance(requested, dict) else None
        )
        if not requested_position:
            return (
                "UNKNOWN",
                "The source qualifies maximum weight capacity by patient "
                "position, but the requirement does not specify a position.",
            )
        if not _source_supports_position_specific_capacity(
            candidate,
            candidate_scope,
            candidate_source,
            requested_position,
        ):
            return (
                "UNKNOWN",
                "The source does not establish a maximum weight capacity for "
                "the requested patient position.",
            )

    if not requested:
        original_query = str(requirement.get("original_query") or "")
        if re.search(
            r"\b(?:trendelenburg|position|tilt\w*|inclination|inclined|angle|"
            r"travel|restriction\w*|restricted|unrestricted|limiting|limited|"
            r"function\w*|operation|loaded|loading|accessor(?:y|ies)|"
            r"evenly|unevenly|degrees?|deg|incline|slope|supine|prone|"
            r"lithotomy|jackknife|fowler)\b|"
            r"\bside[\s-]*lying\b|\blateral\s+decubitus\b|"
            r"\b\d+(?:\.\d+)?\s*(?:degrees?|deg|°|�)\b|"
            r"\bat\s+\d+(?:\.\d+)?\s*(?:degrees?|deg|°|�)\b|"
            r"\b(?:flat|horizontal|level|non[- ]level|sloped|tilted|vertical)\b"
            r".{0,35}\b(?:operating\s+)?tabletop\b|"
            r"\b(?:operating\s+)?tabletop\b.{0,35}"
            r"\b(?:flat|horizontal|level|non[- ]level|sloped|tilted|vertical)\b",
            original_query,
            re.IGNORECASE,
        ):
            return (
                "UNKNOWN",
                "The requirement contains an operating condition that was not "
                "parsed into a supported condition scope.",
            )
        return "PASS", None

    source = candidate.get("source") if isinstance(candidate, dict) else None
    scope = (
        candidate.get("scope")
        if isinstance(candidate, dict)
        else None
    )
    if not isinstance(scope, dict) and isinstance(source, dict):
        scope = source.get("scope")
    if not isinstance(scope, dict):
        return "UNKNOWN", "The requested operating conditions have no scoped source evidence."
    if requested.get("unsupported"):
        return (
            "UNKNOWN",
            "The requested operating condition is not recognized well enough "
            "to compare with the source.",
        )

    source_conditions = [str(scope.get("conditions") or "")]
    qualification_sources = (
        source.get("qualification_sources", [])
        if isinstance(source, dict)
        else []
    )
    if isinstance(qualification_sources, list):
        source_conditions.extend(
            str(item.get("evidence") or "")
            for item in qualification_sources
            if isinstance(item, dict)
        )
    condition_text = " ".join(source_conditions).casefold()
    restriction_text = re.sub(
        r"\bwithout\s+(?:limiting|restricting)\s+(?:the\s+)?"
        r"(?:operating\s+table\s+)?functions?\b",
        "",
        condition_text,
    )
    condition_indicates_restriction = bool(
        re.search(
            r"\b(?:restricted|restriction|restrictions|limited|limitation|"
            r"limitations|limiting)\b|"
            r"\bmust be in the level position\b|"
            r"\bmust not be tilted beyond\b|"
            r"\bstops? automatically at\b",
            restriction_text,
        )
    )
    outcomes = []

    requested_restriction = requested.get("restriction")
    source_restriction = str(scope.get("restriction") or "").strip().casefold()
    if requested_restriction == "none":
        if source_restriction in {"yes", "true", "restricted"}:
            outcomes.append(
                ("FAIL", "The source explicitly indicates that a restriction applies.")
            )
        elif condition_indicates_restriction:
            outcomes.append(
                ("FAIL", "The source wording explicitly describes an operating restriction.")
            )
        elif source_restriction in {"none", "no", "false", "unrestricted"}:
            outcomes.append(
                ("PASS", "The source explicitly indicates no table restriction.")
            )
        else:
            outcomes.append(
                ("UNKNOWN", "The source does not establish whether restrictions apply.")
            )

    if requested.get("function_restriction") == "none":
        source_limits_functions = (
            source_restriction in {"yes", "true", "restricted"}
            or condition_indicates_restriction
        )
        source_explicitly_allows_functions = bool(
            re.search(
                r"\bwithout\s+limiting\s+(?:the\s+)?"
                r"(?:operating\s+table\s+)?functions?\b|"
                r"\bfunctions?\b.{0,80}\bwithout\s+limiting\b",
                condition_text,
            )
        )
        if source_limits_functions:
            outcomes.append(
                ("FAIL", "The source qualifies operation with a restriction.")
            )
        elif source_explicitly_allows_functions:
            outcomes.append(
                ("PASS", "The source explicitly states that table functions are not limited.")
            )
        else:
            outcomes.append(
                ("UNKNOWN", "The source does not establish unrestricted function operation.")
            )

    if requested.get("travel_restriction") == "none":
        travel_is_restricted = bool(
            re.search(
                r"\b(?:longitudinal\s+)?travel\b.{0,100}"
                r"\b(?:restricted|limited|restriction|limitation)\b|"
                r"\b(?:restricted|limited)\b.{0,100}\btravel\b",
                condition_text,
            )
        )
        if travel_is_restricted:
            outcomes.append(
                ("FAIL", "The source explicitly restricts tabletop travel.")
            )
        elif source_restriction in {"none", "no", "false", "unrestricted"}:
            outcomes.append(
                ("PASS", "The source explicitly indicates no applicable restriction.")
            )
        else:
            outcomes.append(
                ("UNKNOWN", "The source does not establish whether tabletop travel is restricted.")
            )

    requested_travel = requested.get("longitudinal_travel")
    if requested_travel:
        source_requires_level = bool(
            re.search(
                r"\blongitudinal\s+travel\b.{0,80}\b(?:must|has)\b.{0,30}"
                r"\blevel\b|\btravel\b.{0,40}\bmust\b.{0,30}\blevel\b",
                condition_text,
            )
        )
        source_requires_non_level = bool(
            re.search(
                r"\b(?:longitudinal\s+)?travel\b.{0,50}"
                r"\b(?:must not be level|must be inclined|not level)\b",
                condition_text,
            )
        )
        if source_requires_level and source_requires_non_level:
            outcomes.append(
                (
                    "UNKNOWN",
                    "The source contains conflicting longitudinal-travel qualifications.",
                )
            )
        elif not source_requires_level and not source_requires_non_level:
            outcomes.append(
                ("UNKNOWN", "The source does not establish the requested travel condition.")
            )
        else:
            if isinstance(requested_travel, dict):
                requested_travels = requested_travel.get("conditions")
                logical_operator = requested_travel.get("logical_operator", "AND")
            else:
                requested_travels = None
                logical_operator = "AND"
            if not isinstance(requested_travels, list):
                requested_travels = [requested_travel]
                logical_operator = "AND"
            source_travel = "level" if source_requires_level else "not_level"
            travel_outcomes = [
                (
                    "PASS" if condition == source_travel else "FAIL",
                    (
                        f"The source requires {source_travel.replace('_', ' ')} "
                        "longitudinal travel."
                        if condition == source_travel
                        else "The requested travel condition contradicts the source qualification."
                    ),
                )
                for condition in requested_travels
            ]
            outcomes.append(
                (
                    _combine_condition_statuses(
                        [status for status, _ in travel_outcomes],
                        logical_operator,
                    ),
                    " ".join(reason for _, reason in travel_outcomes),
                )
            )

    requested_distribution = requested.get("load_distribution")
    if requested_distribution:
        distribution_evidence = _source_load_distribution_evidence(source_conditions)
        requested_distributions = (
            requested_distribution.get("conditions")
            if isinstance(requested_distribution, dict)
            else None
        )
        distribution_operator = (
            requested_distribution.get("logical_operator", "AND")
            if isinstance(requested_distribution, dict)
            else "AND"
        )
        if not isinstance(requested_distributions, list):
            requested_distributions = [requested_distribution]
            distribution_operator = "AND"
        if distribution_evidence["conflicting"] or distribution_evidence["unsupported"]:
            outcomes.append(
                (
                    "UNKNOWN",
                    "The source contains conflicting, ambiguous, or unsupported "
                    "load-distribution qualifications.",
                )
            )
        else:
            distribution_outcomes = []
            for distribution in requested_distributions:
                source_even = "even" in distribution_evidence["states"]
                source_not_even = "not_even" in distribution_evidence["states"]
                source_uneven = "uneven" in distribution_evidence["states"]
                source_not_uneven = "not_uneven" in distribution_evidence["states"]
                if distribution in {"uneven", "not_even"} and source_even:
                    distribution_outcomes.append(
                        ("FAIL", "The source requires an evenly loaded tabletop.")
                    )
                elif distribution in {"even", "not_uneven"} and (
                    source_uneven or source_not_even
                ):
                    distribution_outcomes.append(
                        ("FAIL", "The source contradicts the requested even load distribution.")
                    )
                elif distribution in {"even", "not_uneven"} and (
                    source_even or source_not_uneven
                ):
                    distribution_outcomes.append(
                        ("PASS", "The source requires an evenly loaded tabletop.")
                    )
                elif distribution in {"uneven", "not_even"} and source_uneven:
                    distribution_outcomes.append(
                        ("PASS", "The source supports the requested uneven load distribution.")
                    )
                elif distribution == "not_even" and source_not_even:
                    distribution_outcomes.append(
                        ("PASS", "The source explicitly excludes an evenly loaded tabletop.")
                    )
                elif distribution == "not_uneven" and source_not_uneven:
                    distribution_outcomes.append(
                        ("PASS", "The source explicitly excludes uneven loading.")
                    )
                else:
                    distribution_outcomes.append(
                        ("UNKNOWN", "The source does not establish the requested load distribution.")
                    )
            outcomes.append(
                (
                    _combine_condition_statuses(
                        [status for status, _ in distribution_outcomes],
                        distribution_operator,
                    ),
                    " ".join(reason for _, reason in distribution_outcomes),
                )
            )

    requested_position = requested.get("position")
    if requested_position:
        source_has_reverse_trendelenburg = bool(
            re.search(r"\breverse\s+trendelenburg\b", condition_text)
        )
        source_without_reverse = re.sub(
            r"\breverse\s+trendelenburg\b",
            "",
            condition_text,
        )
        source_has_trendelenburg = bool(
            re.search(r"\btrendelenburg\b", source_without_reverse)
        )
        source_positions = {
            position
            for position, present in (
                ("trendelenburg", source_has_trendelenburg),
                ("reverse_trendelenburg", source_has_reverse_trendelenburg),
            )
            if present
        }
        requested_positions = (
            requested_position.get("conditions")
            if isinstance(requested_position, dict)
            else None
        )
        position_operator = (
            requested_position.get("logical_operator", "AND")
            if isinstance(requested_position, dict)
            else "AND"
        )
        if not isinstance(requested_positions, list):
            requested_positions = [requested_position]
            position_operator = "AND"
        if len(source_positions) > 1:
            outcomes.append(
                (
                    "UNKNOWN",
                    "The source contains conflicting operating-position qualifications.",
                )
            )
        else:
            source_position = next(iter(source_positions), None)
            position_outcomes = [
                (
                    "PASS"
                    if requested == source_position
                    else "FAIL"
                    if source_position
                    else "UNKNOWN",
                    (
                        "The source explicitly supports the requested table position."
                        if requested == source_position
                        else "The source explicitly describes a different table position."
                        if source_position
                        else "The source does not establish the requested operating position."
                    ),
                )
                for requested in requested_positions
            ]
            outcomes.append(
                (
                    _combine_condition_statuses(
                        [status for status, _ in position_outcomes],
                        position_operator,
                    ),
                    " ".join(reason for _, reason in position_outcomes),
                )
            )

    requested_inclination = requested.get("inclination")
    if isinstance(requested_inclination, dict):
        requested_inclinations = requested_inclination.get("conditions")
        logical_operator = requested_inclination.get("logical_operator", "AND")
        if not isinstance(requested_inclinations, list):
            requested_inclinations = [requested_inclination]
            logical_operator = "AND"
        source_limits, unsupported_source_angle = _source_maximum_inclinations(
            source_conditions
        )
        source_limit_values = set(source_limits)
        if unsupported_source_angle:
            outcomes.append(
                (
                    "UNKNOWN",
                    "The source contains an angle qualification that cannot be "
                    "interpreted safely.",
                )
            )
        elif not source_limits:
            outcomes.append(
                ("UNKNOWN", "The source does not establish a maximum inclination.")
            )
        elif len(source_limit_values) > 1:
            outcomes.append(
                (
                    "UNKNOWN",
                    "The source contains conflicting maximum-inclination qualifications.",
                )
            )
        elif logical_operator == "AMBIGUOUS":
            outcomes.append(
                (
                    "UNKNOWN",
                    "The relationship between requested inclination conditions is ambiguous.",
                )
            )
        else:
            maximum = next(iter(source_limit_values))
            angle_outcomes = [
                _evaluate_inclination_against_maximum(condition, maximum)
                for condition in requested_inclinations
            ]
            outcomes.append(
                (
                    _combine_condition_statuses(
                        [status for status, _ in angle_outcomes],
                        logical_operator,
                    ),
                    " ".join(reason for _, reason in angle_outcomes),
                )
            )

    failures = [reason for status, reason in outcomes if status == "FAIL"]
    if failures:
        return "FAIL", " ".join(failures)
    unknowns = [reason for status, reason in outcomes if status == "UNKNOWN"]
    if unknowns:
        return "UNKNOWN", " ".join(unknowns)
    return "PASS", " ".join(reason for _, reason in outcomes)


def _has_position_dependent_capacity_qualification(candidate, scope, source):
    if not isinstance(candidate, dict) or not attributes_equivalent(
        candidate.get("attribute"),
        "Max. weight capacity",
    ):
        return False
    restriction = str((scope or {}).get("restriction") or "").casefold()
    if restriction in {"position-dependent", "position dependent"}:
        return True
    evidence = [str((scope or {}).get("conditions") or "")]
    if isinstance(source, dict):
        evidence.append(str(source.get("evidence") or ""))
        qualifications = source.get("qualification_sources") or []
        if isinstance(qualifications, list):
            evidence.extend(
                str(item.get("evidence") or "")
                for item in qualifications
                if isinstance(item, dict)
            )
    return any(
        re.search(
            r"\bwith restrictions?,\s*depending on (?:the )?position "
            r"of (?:the )?patient\b",
            text,
            re.IGNORECASE,
        )
        for text in evidence
    )


def _source_supports_position_specific_capacity(
    candidate,
    scope,
    source,
    requested_position,
):
    if isinstance(requested_position, dict):
        positions = requested_position.get("conditions")
        logical_operator = requested_position.get("logical_operator", "AND")
    else:
        positions = None
        logical_operator = "AND"
    if not isinstance(positions, list):
        positions = [requested_position]
    if not positions or any(not isinstance(position, str) for position in positions):
        return False

    evidence = [str((scope or {}).get("conditions") or "")]
    if isinstance(source, dict):
        evidence.append(str(source.get("evidence") or ""))
        qualifications = source.get("qualification_sources") or []
        if isinstance(qualifications, list):
            evidence.extend(
                str(item.get("evidence") or "")
                for item in qualifications
                if isinstance(item, dict)
            )

    candidate_value = candidate.get("parsed_value") or parse_value(
        candidate.get("raw_value") or ""
    )
    if (
        candidate_value.get("type") == "mixed"
        and isinstance(candidate_value.get("parsed_value"), dict)
    ):
        candidate_value = candidate_value["parsed_value"]
    if candidate_value.get("type") != "scalar":
        return False

    capacity_pattern = re.compile(
        r"\b(?:maximum|max\.?)\s+weight\s+capacity\b",
        re.IGNORECASE,
    )
    numeric_units = re.compile(
        r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
        r"(?P<unit>kg|kilograms?|lbs?|pounds?)\b",
        re.IGNORECASE,
    )
    matched_positions = set()
    for text in evidence:
        normalized_text = re.sub(r"\bmax\.", "max", text, flags=re.IGNORECASE)
        for clause in re.split(r"[.;\n]+", normalized_text):
            if not capacity_pattern.search(clause):
                continue
            if re.search(
                r"\b(?:not|never|no|cannot|can't|prohibited|excluded)\b",
                clause,
                re.IGNORECASE,
            ):
                continue
            quantities = list(numeric_units.finditer(clause))
            if not quantities:
                continue
            for position in positions:
                position_phrase = position.replace("_", " ")
                if not re.search(
                    rf"(?<!\w){re.escape(position_phrase)}(?!\w)",
                    clause,
                    re.IGNORECASE,
                ):
                    continue
                for quantity in quantities:
                    value = float(quantity.group("value").replace(",", ""))
                    unit = quantity.group("unit")
                    try:
                        candidate_value_in_unit = convert(
                            float(candidate_value["value"]),
                            candidate_value["unit"],
                            unit,
                        )
                    except (TypeError, ValueError):
                        continue
                    tolerance = max(abs(candidate_value_in_unit) * 0.01, 0.01)
                    if abs(value - candidate_value_in_unit) > tolerance:
                        continue
                    matched_positions.add(position)

    if logical_operator == "OR":
        return bool(matched_positions)
    return all(position in matched_positions for position in positions)


def _combine_condition_statuses(statuses, logical_operator):
    if not statuses or logical_operator == "AMBIGUOUS":
        return "UNKNOWN"
    if logical_operator == "OR":
        if "PASS" in statuses:
            return "PASS"
        if "UNKNOWN" in statuses:
            return "UNKNOWN"
        return "FAIL"
    if "FAIL" in statuses:
        return "FAIL"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    return "PASS"


def _source_load_distribution_evidence(source_texts):
    phrases = (
        ("even", re.compile(
            r"\b(?:evenly|uniformly)[\s-]+loaded\b|"
            r"\beven\s+surface\s+load\b",
            re.IGNORECASE,
        )),
        ("uneven", re.compile(
            r"\bunevenly[\s-]+loaded\b|\buneven\s+load(?:ed|ing)?\b|"
            r"\basymmetrically[\s-]+loaded\b|\basymmetric\s+load\b|"
            r"\bone[\s-]+sided\s+load(?:ed|ing)?\b|"
            r"\bnon[\s-]*uniform\s+load(?:ed|ing)?\b|"
            r"\bloaded\s+unevenly\b",
            re.IGNORECASE,
        )),
    )
    states = set()
    unsupported = False
    clause_boundary = re.compile(r"[.!?;]")
    negation = re.compile(
        r"(?:\bnot\b|\bnever\b|\bno\b)(?:[\s,():-]+\w+){0,5}"
        r"[\s,():-]*$|(?:^|[\s,():-])non[\s-]*$",
        re.IGNORECASE,
    )
    ambiguous_negation = re.compile(r"\bnot\s+only\b", re.IGNORECASE)

    for text in source_texts:
        for state, pattern in phrases:
            for match in pattern.finditer(text):
                prior = text[:match.start()]
                boundary = max(
                    (boundary.end() for boundary in clause_boundary.finditer(prior)),
                    default=0,
                )
                prefix = prior[boundary:]
                if ambiguous_negation.search(prefix):
                    unsupported = True
                    continue
                negation_match = negation.search(prefix)
                is_negated = bool(
                    negation_match
                    and not pattern.search(prefix[negation_match.end():])
                )
                states.add(
                    f"not_{state}" if is_negated else state
                )

        if re.search(
            r"\b(?:load distribution|loading pattern|"
            r"(?:radial(?:ly)?|concentrated|asymmetric(?:ally)?|"
            r"uneven(?:ly)?|uniform(?:ly)?) loading)\b|"
            r"\bradially loaded\b",
            text,
            re.IGNORECASE,
        ) and not any(pattern.search(text) for _, pattern in phrases):
            unsupported = True

    conflicting = bool(
        {"even", "not_even"} <= states
        or {"uneven", "not_uneven"} <= states
        or {"even", "uneven"} <= states
    )
    return {
        "states": states,
        "conflicting": conflicting,
        "unsupported": unsupported,
    }


def _source_maximum_inclinations(source_texts):
    number = r"(\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|�)"
    patterns = (
        re.compile(
            r"\bmaximum\s+(?:(?:operating\s+)?tabletop\s+)?"
            r"(?:inclination|tilt|angle)\b.{0,35}?\b(?:is|of|up to)?\s*"
            + number,
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:inclination|inclined|tilt(?:ed|ing)?|angle)\b.{0,80}?"
            r"\b(?:no more than|not more than|at most|up to|limited to|"
            r"(?:should|must|does|do) not exceed|not exceed|cannot exceed)\s*"
            + number,
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:inclination|inclined|tilt(?:ed|ing)?|angle)\b.{0,80}?"
            r"\b(?:should|must|shall)\s+not\s+be\s+"
            r"(?:tilted|inclined|exceeded)\s+beyond\s*" + number,
            re.IGNORECASE,
        ),
        re.compile(
            r"\btilt(?:ing)?\s+function\b.{0,50}?"
            r"\bstops?\s+automatically\s+at\s*" + number,
            re.IGNORECASE,
        ),
    )
    values = set()
    unsupported = False
    angle_statement = re.compile(
        r"\b(?:inclination|inclined|tilt(?:ed|ing)?|angle)\b[^.;!?]{0,100}?"
        + number,
        re.IGNORECASE,
    )
    for text in source_texts:
        found_spans = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                values.add(float(match.group(1)))
                found_spans.append(match.span())
        for match in angle_statement.finditer(text):
            if not any(
                match.start() < end and start < match.end()
                for start, end in found_spans
            ):
                unsupported = True
    return values, unsupported


def _evaluate_inclination_against_maximum(requested, maximum):
    requested_value = float(requested["value"])
    operator = requested.get("operator")
    if operator == "=":
        if requested_value > maximum:
            return (
                "FAIL",
                f"The requested {requested_value:g}-degree inclination exceeds "
                f"the source limit of {maximum:g} degrees.",
            )
        return (
            "PASS",
            f"The requested inclination is within the source limit "
            f"of {maximum:g} degrees.",
        )
    if operator == "<=":
        if requested_value >= maximum:
            return (
                "PASS",
                f"The source maximum of {maximum:g} degrees satisfies the "
                "requested upper bound.",
            )
        return (
            "UNKNOWN",
            "The source maximum does not establish the stricter requested "
            "inclination bound.",
        )
    if operator == "<":
        if requested_value > maximum:
            return (
                "PASS",
                f"The source maximum of {maximum:g} degrees is below the "
                "requested upper bound.",
            )
        return (
            "UNKNOWN",
            "The source maximum does not establish the stricter requested "
            "inclination bound.",
        )
    if operator == ">":
        status = "FAIL" if requested_value >= maximum else "UNKNOWN"
        return (
            status,
            "The requested lower bound exceeds the source maximum."
            if status == "FAIL"
            else "The source maximum does not establish the requested lower bound.",
        )
    if operator == ">=":
        status = "FAIL" if requested_value > maximum else "UNKNOWN"
        return (
            status,
            "The requested lower bound exceeds the source maximum."
            if status == "FAIL"
            else "The source maximum does not establish the requested lower bound.",
        )
    return (
        "UNKNOWN",
        "The requested inclination relation is not established by the source.",
    )


def evaluate_requirement(requirement, product_value_text, candidate_attribute=None, candidate=None):
    """
    Compare a parsed requirement with a product specification value.

    A reported range is treated as the full set of permitted values. PASS
    requires every value in the range to satisfy the requirement; FAIL means
    no value satisfies it; an overlapping range returns UNKNOWN.

    Returns:
        PASS
        FAIL
        UNKNOWN
    """

    if candidate is not None and isinstance(candidate, dict):
        candidate_attribute = candidate.get("attribute", candidate_attribute)
        product_value_text = candidate.get("raw_value", product_value_text)

    # Requirement must contain enough information to evaluate
    if requirement["value"] is None or requirement["operator"] is None:
        return "UNKNOWN"

    required_attribute = requirement.get("attribute")
    if required_attribute and (
        candidate_attribute is not None or candidate is not None
    ) and not attributes_equivalent(required_attribute, candidate_attribute):
        return "UNKNOWN"

    required_component = requirement.get("component")
    candidate_component = candidate.get("component") if isinstance(candidate, dict) else None
    if required_component:
        if normalize_component(required_component) != normalize_component(candidate_component):
            return "UNKNOWN"
    elif candidate_component:
        return "UNKNOWN"

    condition_status, _ = evaluate_condition_compatibility(requirement, candidate)
    if condition_status != "PASS":
        return condition_status

    product_value = None
    if isinstance(candidate, dict):
        product_value = deepcopy(candidate.get("parsed_value"))
    if not isinstance(product_value, dict):
        product_value = parse_value(product_value_text)

    if product_value.get("type") == "mixed" and isinstance(product_value.get("parsed_value"), dict):
        product_value = product_value["parsed_value"]

    # Cannot evaluate unavailable or unknown values
    if product_value["type"] in ["unknown", "not_available"]:
        return "UNKNOWN"

    required_unit = requirement["unit"]
    product_unit = product_value.get("unit")

    # ---------------------------------------------------------
    # UNIT NORMALIZATION
    # ---------------------------------------------------------

    if required_unit and product_unit:

        try:
            product_number = product_value.get("value")

            if product_value["type"] == "scalar":
                product_number = convert(
                    product_number,
                    product_unit,
                    required_unit
                )

                product_value["value"] = product_number

            elif product_value["type"] == "range":

                product_value["min"] = convert(
                    product_value["min"],
                    product_unit,
                    required_unit
                )

                product_value["max"] = convert(
                    product_value["max"],
                    product_unit,
                    required_unit
                )

        except ValueError:
            # Units are incompatible or unsupported
            return "UNKNOWN"

    elif required_unit and not product_unit:
        # Requirement specifies a unit but product does not
        return "UNKNOWN"
    elif product_unit and not required_unit:
        # A bare requirement value cannot be assumed to use the product's unit.
        return "UNKNOWN"

    if (
        product_value["type"] in {"scalar", "range"}
        and not required_unit
        and not product_unit
    ):
        return "UNKNOWN"

    # ---------------------------------------------------------
    # SCALAR
    # ---------------------------------------------------------

    if product_value["type"] == "scalar":

        product_number = product_value["value"]
        required_number = requirement["value"]
        operator = requirement["operator"]

        if operator == ">=":
            return "PASS" if product_number >= required_number else "FAIL"

        elif operator == "<=":
            return "PASS" if product_number <= required_number else "FAIL"

        elif operator == ">":
            return "PASS" if product_number > required_number else "FAIL"

        elif operator == "<":
            return "PASS" if product_number < required_number else "FAIL"

        elif operator == "=":
            return "PASS" if product_number == required_number else "FAIL"

    # ---------------------------------------------------------
    # BOOLEAN
    # ---------------------------------------------------------

    if product_value["type"] == "boolean":

        if requirement["operator"] != "=":
            return "UNKNOWN"

        required_value = requirement["value"]

        if required_value == 1:
            return "PASS" if product_value["value"] is True else "FAIL"

        elif required_value == 0:
            return "PASS" if product_value["value"] is False else "FAIL"

        return "UNKNOWN"

    # ---------------------------------------------------------
    # RANGE
    # ---------------------------------------------------------

    if product_value["type"] == "range":

        minimum = product_value["min"]
        maximum = product_value["max"]

        required_number = requirement["value"]
        operator = requirement["operator"]

        if operator == ">=":
            if minimum >= required_number:
                return "PASS"
            return "FAIL" if maximum < required_number else "UNKNOWN"

        elif operator == "<=":
            if maximum <= required_number:
                return "PASS"
            return "FAIL" if minimum > required_number else "UNKNOWN"

        elif operator == ">":
            if minimum > required_number:
                return "PASS"
            return "FAIL" if maximum <= required_number else "UNKNOWN"

        elif operator == "<":
            if maximum < required_number:
                return "PASS"
            return "FAIL" if minimum >= required_number else "UNKNOWN"

        elif operator == "=":
            if minimum == maximum == required_number:
                return "PASS"
            if required_number < minimum or required_number > maximum:
                return "FAIL"
            return "UNKNOWN"

    return "UNKNOWN"