from src.retrieval.value_parser import parse_value


test_values = [
    # Scalar values
    "5 hours",
    "400 kg",
    "400kg",
    "400 KG",
    "12.1 inch",
    "12.1 inches",
    "500 samples/sec",

    # Ranges
    "1–1000 ml/hr",
    "1-1000 ml/hr",
    "1 to 1000 ml/hr",
    "70–100%",
    "0 - 100 %",
    "10 to 40 °C",

    # Tolerance
    "±3%",
    "± 3 %",
    "+/-3%",
    "+/- 3%",

    # Boolean
    "Supported",
    "Not Supported",
    "Available",
    "Unavailable",

    # Categorical
    "Standard",
    "Optional",
    "Configurable",

    # Multiple values
    "25/50 mm/sec",
    "25 / 50 mm/sec",

    # Comma-separated number
    "1,000 ml/hr",

    # Not available
    "N/A",
    "Not available",
    "Not specified",

    # Unknown
    "Something unknown",
    "—"
]


print("=" * 60)
print("VALUE PARSER TEST")
print("=" * 60)


for value in test_values:

    result = parse_value(value)

    print()
    print(f"Input : {value}")
    print(f"Output: {result}")


print()
print("=" * 60)
print("TEST COMPLETED")
print("=" * 60)