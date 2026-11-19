"""NSE and BSE symbol validation."""
from data.validation import validate_bse_symbol, validate_nse_symbol


def test_valid_nse_symbols():
    for symbol in ["RELIANCE", "TCS", "M&M", "BAJAJ-AUTO", "HDFCBANK", "L&TFH"]:
        assert validate_nse_symbol(symbol), symbol


def test_invalid_nse_symbols():
    for symbol in ["", "reli ance", "REL$IANCE", "X" * 25, "!!"]:
        assert not validate_nse_symbol(symbol), symbol


def test_lowercase_accepted_after_normalisation():
    assert validate_nse_symbol("reliance")  # upper-cased internally


def test_valid_bse_symbols():
    for symbol in ["500325", "532540", "RELIANCE"]:
        assert validate_bse_symbol(symbol), symbol


def test_invalid_bse_symbols():
    for symbol in ["", "12 3", "ABC$", "X" * 25, "@@"]:
        assert not validate_bse_symbol(symbol), symbol
