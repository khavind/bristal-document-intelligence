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

    if requested.get("unsupported"):
        outcomes.append(
            (
                "UNKNOWN",
                "The requested operating condition is not recognized well enough "
                "to compare with the source.",
            )
        )

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
        if source_requires_level:
            status = "PASS" if requested_travel == "level" else "FAIL"
            outcomes.append(
                (
                    status,
                    "The source requires level longitudinal travel."
                    if status == "PASS"
                    else "The requested travel condition contradicts the source's level-travel requirement.",
                )
            )
        elif source_requires_non_level:
            status = "PASS" if requested_travel == "not_level" else "FAIL"
            outcomes.append(
                (
                    status,
                    "The source supports the requested non-level travel condition."
                    if status == "PASS"
                    else "The requested level-travel condition contradicts the source.",
                )
            )
        else:
            outcomes.append(
                ("UNKNOWN", "The source does not establish the requested travel condition.")
            )

    requested_distribution = requested.get("load_distribution")
    if requested_distribution:
        source_even = bool(
            re.search(r"\bevenly\s+loaded\b|\beven\s+surface\s+load\b", condition_text)
        )
        source_uneven = bool(
            re.search(r"\b(?:unevenly|uneven|non[- ]uniformly)\s+loaded\b", condition_text)
        )
        if requested_distribution == "uneven" and source_even:
            outcomes.append(
                ("FAIL", "The source requires an evenly loaded tabletop.")
            )
        elif requested_distribution == "even" and source_uneven:
            outcomes.append(
                ("FAIL", "The source requires an uneven load distribution.")
            )
        elif requested_distribution == "even" and source_even:
            outcomes.append(
                ("PASS", "The source requires an evenly loaded tabletop.")
            )
        elif requested_distribution == "uneven" and source_uneven:
            outcomes.append(
                ("PASS", "The source supports the requested uneven load distribution.")
            )
        else:
            outcomes.append(
                ("UNKNOWN", "The source does not establish the requested load distribution.")
            )

    requested_position = requested.get("position")
    if requested_position:
        position_phrases = {
            "trendelenburg": r"\btrendelenburg\b",
            "reverse_trendelenburg": r"\breverse\s+trendelenburg\b",
        }
        source_position = next(
            (
                name
                for name, pattern in position_phrases.items()
                if re.search(pattern, condition_text)
            ),
            None,
        )
        if source_position == requested_position:
            outcomes.append(
                ("PASS", "The source explicitly supports the requested table position.")
            )
        elif source_position:
            outcomes.append(
                ("FAIL", "The source explicitly describes a different table position.")
            )
        else:
            outcomes.append(
                ("UNKNOWN", "The source does not establish the requested operating position.")
            )

    requested_inclination = requested.get("inclination")
    if isinstance(requested_inclination, dict):
        source_limit = re.search(
            r"\b(?:inclined|tilted|inclination)\b.{0,100}?"
            r"\b(?:no more than|not more than|at most|up to|limited to)\s*"
            r"(\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|�)?",
            condition_text,
        )
        if not source_limit:
            outcomes.append(
                ("UNKNOWN", "The source does not establish a maximum inclination.")
            )
        else:
            maximum = float(source_limit.group(1))
            requested_value = float(requested_inclination["value"])
            requested_operator = requested_inclination.get("operator")
            if requested_operator == "=" and requested_value > maximum:
                outcomes.append(
                    (
                        "FAIL",
                        f"The requested {requested_value:g}-degree inclination exceeds "
                        f"the source limit of {maximum:g} degrees.",
                    )
                )
            elif requested_operator == "=":
                outcomes.append(
                    (
                        "PASS",
                        f"The requested inclination is within the source limit "
                        f"of {maximum:g} degrees.",
                    )
                )
            elif requested_operator == "<=" and requested_value >= maximum:
                outcomes.append(
                    (
                        "PASS",
                        f"The source maximum of {maximum:g} degrees satisfies the "
                        "requested upper bound.",
                    )
                )
            elif requested_operator == "<" and requested_value > maximum:
                outcomes.append(
                    (
                        "PASS",
                        f"The source maximum of {maximum:g} degrees is below the "
                        "requested upper bound.",
                    )
                )
            elif requested_operator in {"<=", "<"}:
                outcomes.append(
                    (
                        "UNKNOWN",
                        "The source maximum does not establish the stricter requested "
                        "inclination bound.",
                    )
                )
            elif requested_operator == ">":
                status = "FAIL" if requested_value >= maximum else "UNKNOWN"
                outcomes.append(
                    (
                        status,
                        "The requested lower bound exceeds the source maximum."
                        if status == "FAIL"
                        else "The source maximum does not establish the requested lower bound.",
                    )
                )
            elif requested_operator == ">=":
                status = "FAIL" if requested_value > maximum else "UNKNOWN"
                outcomes.append(
                    (
                        status,
                        "The requested lower bound exceeds the source maximum."
                        if status == "FAIL"
                        else "The source maximum does not establish the requested lower bound.",
                    )
                )
            else:
                outcomes.append(
                    ("UNKNOWN", "The requested inclination relation is not established by the source.")
                )

    failures = [reason for status, reason in outcomes if status == "FAIL"]
    if failures:
        return "FAIL", " ".join(failures)
    unknowns = [reason for status, reason in outcomes if status == "UNKNOWN"]
    if unknowns:
        return "UNKNOWN", " ".join(unknowns)
    return "PASS", " ".join(reason for _, reason in outcomes)


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