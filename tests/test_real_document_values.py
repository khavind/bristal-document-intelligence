from src.retrieval.value_parser import parse_value


def test_real_document_weight():
    parsed = parse_value("400 kg")

    assert parsed["type"] == "scalar"
    assert parsed["value"] == 400
    assert parsed["unit"] == "kg"


def test_real_document_two_dimensions():
    parsed = parse_value("372 mm x 311 mm")

    assert parsed["type"] == "compound"
    assert parsed["values"] == [372, 311]
    assert parsed["unit"] == "mm"


def test_real_document_three_dimensions():
    parsed = parse_value("916 mm x 527 mm x 25 mm")

    assert parsed["type"] == "compound"
    assert parsed["values"] == [916, 527, 25]
    assert parsed["unit"] == "mm"


def test_real_document_height_range():
    parsed = parse_value("510 mm to 1,060 mm")

    assert parsed["type"] == "range"
    assert parsed["min"] == 510
    assert parsed["max"] == 1060
    assert parsed["unit"] == "mm"


def test_real_document_paired_angles():
    parsed = parse_value("45°/45°")

    assert parsed["type"] == "paired"
    assert parsed["values"] == [45, 45]
    assert parsed["unit"] == "°"


def test_real_document_frequency_values():
    parsed = parse_value("50 Hz/60 Hz")

    assert parsed["type"] == "multiple"
    assert parsed["values"] == [50, 60]
    assert parsed["unit"] == "Hz"

def test_real_document_trendelenburg_range():
    parsed = parse_value("+17° to -17°")

    assert parsed["type"] == "range"
    assert parsed["min"] == -17
    assert parsed["max"] == 17
    assert parsed["unit"] == "°"


def test_real_document_mixed_measurement():
    parsed = parse_value("150 mm double band")

    assert parsed["type"] == "mixed"
    assert parsed["raw"] == "150 mm double band"
    assert parsed["parsed_value"]["type"] == "scalar"
    assert parsed["parsed_value"]["value"] == 150
    assert parsed["parsed_value"]["unit"] == "mm"
    assert parsed["description"] == "double band"

def test_real_document_categorical_location():
    parsed = parse_value("At head end")

    assert parsed["type"] == "categorical"
    assert parsed["value"] == "At head end"


def test_real_document_categorical_installation():
    parsed = parse_value("Integrated in right siderail")

    assert parsed["type"] == "categorical"
    assert parsed["value"] == "Integrated in right siderail"


def test_real_document_categorical_protection_class():
    parsed = parse_value("IPX4")

    assert parsed["type"] == "categorical"
    assert parsed["value"] == "IPX4"