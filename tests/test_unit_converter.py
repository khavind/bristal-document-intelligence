import pytest

from src.retrieval.unit_converter import convert


def test_weight_conversion():

    assert convert(4000, "g", "kg") == pytest.approx(4)

    assert convert(4, "kg", "g") == pytest.approx(4000)


def test_time_conversion():

    assert convert(2, "hours", "minutes") == pytest.approx(120)

    assert convert(120, "minutes", "hours") == pytest.approx(2)

    assert convert(3600, "seconds", "hours") == pytest.approx(1)


def test_length_conversion():

    assert convert(1000, "mm", "m") == pytest.approx(1)

    assert convert(100, "cm", "m") == pytest.approx(1)

    assert convert(1, "inch", "cm") == pytest.approx(2.54)


def test_same_unit():

    assert convert(5, "kg", "kg") == pytest.approx(5)


def test_unit_aliases():

    assert convert(2, "hrs", "minutes") == pytest.approx(120)

    assert convert(4000, "grams", "kilograms") == pytest.approx(4)

    assert convert(100, "centimeters", "meters") == pytest.approx(1)


def test_case_insensitive_units():

    assert convert(4, "KG", "g") == pytest.approx(4000)

    assert convert(2, "HOURS", "minutes") == pytest.approx(120)


def test_incompatible_units():

    with pytest.raises(ValueError):

        convert(5, "kg", "hours")


def test_unsupported_unit():

    with pytest.raises(ValueError):

        convert(5, "kg", "litres")