# Tests

    pip install pytest
    cd backend && python -m pytest tests -q

`test_calc.py` covers the calculation engine: gas unit conversion, barometric
pressure units, prevailing wind direction, the eight-hour rolling average, and
the data-capture gates.

Each test pins a claim an issued report makes, chosen because getting it wrong
would be both plausible and invisible on the page. Several exist because the
error they guard against actually happened: pressure printed as 92.3 hPa from
an unconverted kilopascal file, gas concentrations out by a factor of a
thousand, and a prevailing wind direction that disagreed with itself between a
figure and the conclusions three pages later.

The suite was checked by mutation: the engine was deliberately broken twelve
ways — the conversion factor removed, the completeness gate loosened and
tightened, a tie broken arbitrarily, capture measured against the file instead
of the monitoring window — and every break was caught. Two gaps found that way
have their own tests now, named for the boundary they pin.

When adding a test, prefer the boundary to a comfortable value. A gate tested
only at 70% and 75% is free to slide anywhere between them.
