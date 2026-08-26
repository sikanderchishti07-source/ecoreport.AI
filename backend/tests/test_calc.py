"""Tests for the calculation engine.

Written after a run of defects that all shared a shape: a number that looked
entirely ordinary on the page and was wrong. Barometric pressure printed as
92.3 hPa, a pressure found at sixteen kilometres altitude, because the file
was in kilopascals and nothing checked. Gas concentrations out by a factor of
a thousand from a units mismatch. Prevailing wind direction computed three
different ways in three places, so one report said N in its figure and NNW in
its conclusions. A daily average that weighted an eleven-hour day the same as
a thirteen-hour one.

None of those would survive a test. Every one reached an issued report.

So the tests here are not a demonstration that the code runs. Each one pins a
specific claim the reports make, chosen because getting it wrong is both
plausible and invisible:

  * a conversion factor, where an error is a constant multiple
  * a boundary, where an error moves a verdict from compliant to not
  * a tie, where an arbitrary winner reads as a finding
  * a refusal, where the engine should decline rather than guess

Run with:  pytest backend/tests -q
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

import calc
from models import Reading
from units_mdl import MOLAR_MASS, MOLAR_VOLUME_25C, to_ugm3

UTC = timezone.utc


def _hours(start: datetime, values, field: str = "SO2", valid=None):
    """One reading per clock hour, with `None` for an hour left blank."""
    out = []
    for i, v in enumerate(values):
        kwargs = {field: v}
        out.append(Reading(
            campaign_id="t", timestamp=start + timedelta(hours=i),
            valid=True if valid is None else valid[i], **kwargs))
    return out


# ---------------------------------------------------------------------------
# Gas unit conversion
#
# The bug this guards against understated CO by three orders of magnitude and
# was invisible: every number on the page was plausible, and the verdict was
# COMPLIANT throughout.
# ---------------------------------------------------------------------------
class TestUnitConversion:

    def test_ugm3_passes_through_untouched(self):
        assert to_ugm3(123.4, "SO2", "ugm3") == 123.4

    @pytest.mark.parametrize("gas", sorted(MOLAR_MASS))
    def test_ppb_uses_the_molar_ratio_at_reference_conditions(self, gas):
        """µg/m³ = ppb x M / 24.45, the NCEC reference of 25 °C and 101.3 kPa.

        Asserted from the constants rather than against a table of expected
        numbers: a test carrying its own copy of the answer passes happily
        after someone edits the molar mass to the wrong value.
        """
        expected = 100.0 * MOLAR_MASS[gas] / MOLAR_VOLUME_25C
        assert to_ugm3(100.0, gas, "ppb") == pytest.approx(expected)

    @pytest.mark.parametrize("gas", sorted(MOLAR_MASS))
    def test_ppm_is_exactly_one_thousand_times_ppb(self, gas):
        """The factor that went wrong. One ppm is one thousand ppb, always."""
        assert to_ugm3(1.0, gas, "ppm") == pytest.approx(
            to_ugm3(1000.0, gas, "ppb"))

    def test_known_values(self):
        """Two figures checkable against any air quality reference."""
        # 1 ppb SO2 at 25 °C is about 2.62 µg/m³
        assert to_ugm3(1.0, "SO2", "ppb") == pytest.approx(2.62, abs=0.01)
        # 1 ppm CO is about 1.145 mg/m³
        assert to_ugm3(1.0, "CO", "ppm") == pytest.approx(1145.6, abs=1.0)

    def test_nox_is_reported_as_no2_equivalent(self):
        """Convention, not chemistry. NOx has no single molar mass; the
        standards express it as NO2, and a report that used NO's mass would
        understate every NOx figure by a third."""
        assert MOLAR_MASS["NOx"] == MOLAR_MASS["NO2"]

    def test_particulates_are_never_converted(self):
        """PM is weighed, not inferred from a volume. A conversion applied to
        it would be meaningless, so an unknown pollutant passes through."""
        assert to_ugm3(296.0, "PM10", "ppb") == 296.0
        assert to_ugm3(34.1, "PM25", "ppm") == 34.1


# ---------------------------------------------------------------------------
# Barometric pressure units
#
# 92.3 hPa reached an issued report. It is the pressure at roughly 16 km
# altitude and nothing flagged it, because the file was in kilopascals and
# calc.py had no pressure unit handling at all.
# ---------------------------------------------------------------------------
class TestPressureUnits:

    def test_kilopascals_are_detected_and_converted(self):
        values, unit = calc.normalise_pressure([92.31, 92.15, 92.00, 92.28])
        assert unit == "kPa"
        assert max(values) == pytest.approx(923.1, abs=0.1)
        assert min(values) == pytest.approx(920.0, abs=0.1)

    def test_hectopascals_are_left_alone(self):
        values, unit = calc.normalise_pressure([1013.2, 1011.8, 1014.0])
        assert unit is None
        assert values == [1013.2, 1011.8, 1014.0]

    def test_inches_of_mercury_are_converted(self):
        values, unit = calc.normalise_pressure([29.92, 29.80, 30.05])
        assert unit == "inHg"
        assert values[0] == pytest.approx(1013.2, abs=0.5)

    def test_unrecognisable_values_are_left_exactly_as_recorded(self):
        """A number that matches no unit must not be rewritten into one that
        looks plausible. A blank or an odd figure is recoverable; a silently
        corrected one is not."""
        values, unit = calc.normalise_pressure([5.0, 6.2, 4.8])
        assert unit is None
        assert values == [5.0, 6.2, 4.8]

    def test_one_stray_reading_does_not_move_the_decision(self):
        """The median decides the unit, so a single glitch cannot flip a whole
        file into the wrong one."""
        _, unit = calc.normalise_pressure([92.3, 92.1, 92.0, 1013.0, 92.2])
        assert unit == "kPa"

    def test_a_reading_absurd_after_conversion_is_excluded(self):
        """A stray 1013 in a kilopascal file becomes 10130 hPa once the
        file's factor is applied, and being the largest number present it
        would become the reported maximum."""
        values, _ = calc.normalise_pressure([92.3, 92.1, 92.0, 1013.0, 92.2])
        assert max(values) < 1085.0
        assert len(values) == 4

    def test_empty_and_missing(self):
        assert calc.normalise_pressure([]) == ([], None)
        assert calc.normalise_pressure([None, None])[1] is None


# ---------------------------------------------------------------------------
# Prevailing wind direction
#
# Computed in three places by three rules, which disagreed inside one
# document: the wind rose figure was labelled N while the conclusions three
# pages later said NNW. Underneath, the two sectors were tied and the winner
# was whichever appeared first in the file.
# ---------------------------------------------------------------------------
class TestPrevailingDirection:

    def test_a_clear_winner(self):
        counts = {"N": 12, "NNE": 6, "NNW": 4}
        assert calc.prevailing_direction(counts) == "N"
        assert calc.prevailing_label(counts) == "N"

    def test_a_tie_is_reported_as_a_tie(self):
        """The survey that exposed this had N and NNW at exactly 37.5% each.
        Naming one of them is a statement the data does not support."""
        counts = {"N": 9, "NNE": 6, "NNW": 9}
        assert calc.prevailing_direction(counts) is None
        assert calc.prevailing_label(counts) == "N and NNW"

    def test_the_answer_does_not_depend_on_row_order(self):
        """The actual defect: the same data in a different order gave a
        different prevailing direction."""
        import itertools
        pairs = [("N", 9), ("NNE", 6), ("NNW", 9)]
        answers = {calc.prevailing_label(dict(p))
                   for p in itertools.permutations(pairs)}
        assert len(answers) == 1

    def test_three_sectors_tied_are_all_named(self):
        assert calc.prevailing_label({"N": 5, "E": 5, "S": 5, "W": 1}) \
            == "N, E and S"

    def test_more_than_three_tied_names_none(self):
        """A list four items long is not a finding."""
        assert calc.prevailing_label({"N": 5, "E": 5, "S": 5, "W": 5}) is None

    def test_no_data(self):
        assert calc.prevailing_label({}) is None
        assert calc.prevailing_label({"N": 0, "S": 0}) is None


# ---------------------------------------------------------------------------
# The eight-hour rolling average
#
# CO and ozone are judged against it, so an error here moves a verdict rather
# than a decimal.
# ---------------------------------------------------------------------------
class TestRolling8h:

    def test_the_first_seven_hours_are_blank(self):
        """Seven hours is not an eight-hour average, however tempting the
        arithmetic is."""
        start = datetime(2026, 7, 8, 13, tzinfo=UTC)
        rows = _hours(start, [10.0] * 12, field="CO")
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[:7] == [None] * 7
        assert out[7] == pytest.approx(10.0)

    def test_a_gap_in_the_file_does_not_stretch_the_window(self):
        """The window is eight clock hours, not the last eight rows present.

        Nine hours are exported with one missing in the middle. Counted by
        rows, hour 8 would average the eight rows before it and reach back to
        hour 0 — a nine-hour window wearing an eight-hour label. Counted by
        clock hour it sees eight slots, seven of them valid, which is above
        the six-hour minimum and reportable.
        """
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        rows = _hours(start, [10.0] * 9, field="CO")
        del rows[4]                       # hour 4 missing from the export
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[-1] == pytest.approx(10.0)

    def test_a_gap_too_wide_to_average_gives_nothing(self):
        """Three hours missing from an eight-hour window leaves five valid,
        below the six-hour minimum, so there is no average to report."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        rows = _hours(start, [10.0] * 8, field="CO")
        rows = rows[:2] + rows[5:]        # hours 2, 3 and 4 absent
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[-1] is None

    def test_fewer_than_six_valid_hours_gives_no_average(self):
        """USEPA practice: six of eight, or the window is not reportable."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        values = [10.0, 10.0, 10.0, None, None, None, None, 10.0]
        rows = _hours(start, values, field="CO")
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[7] is None

    def test_five_valid_hours_is_still_not_enough(self):
        """Pins the six-hour rule rather than merely a low one.

        Four valid hours fails whether the rule is six or four, so a test
        using it leaves the threshold free to drift. Five is the value that
        separates a correct rule from a loosened one.
        """
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        values = [10.0] * 5 + [None] * 3
        rows = _hours(start, values, field="CO")
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[7] is None

    def test_exactly_six_valid_hours_is_enough(self):
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        values = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, None, None]
        rows = _hours(start, values, field="CO")
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[7] == pytest.approx(10.0)

    def test_an_invalidated_row_is_excluded(self):
        """A row marked invalid by an operator must not reach an average."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        valid = [True] * 7 + [False]
        rows = _hours(start, [10.0] * 8, field="CO", valid=valid)
        out = calc.rolling_8h(rows, "CO", window_start=start)
        assert out[7] == pytest.approx(10.0)  # the seven valid hours only

    def test_empty_input(self):
        assert calc.rolling_8h([], "CO") == []


# ---------------------------------------------------------------------------
# Daily means and capture
# ---------------------------------------------------------------------------
class TestDailyMeans:

    def test_a_day_is_a_calendar_day(self):
        """The 24-hour standard applies to a calendar day, so a survey running
        13:00 to 13:00 covers parts of two days, not one."""
        start = datetime(2026, 7, 8, 13, tzinfo=UTC)
        end = start + timedelta(hours=24)
        rows = _hours(start, [10.0] * 24)
        days = calc.daily_means(rows, "SO2", window_start=start, window_end=end)
        assert len(days) == 2

    def test_expected_hours_are_the_window_not_the_file(self):
        """Hours missing from the export must count against capture. Measured
        against rows present, a file with half a day missing reports 100%."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        end = start + timedelta(hours=24)
        rows = _hours(start, [10.0] * 12)      # only half the day was exported
        days = calc.daily_means(rows, "SO2", window_start=start, window_end=end)
        _, mean, valid, expected = days[0]
        assert valid == 12
        assert expected == 24

    def test_below_seventy_five_percent_capture_gives_no_mean(self):
        """The completeness gate. A day that fails it is not reportable, and
        must not quietly contribute a mean drawn from a few hours."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        end = start + timedelta(hours=24)
        values = [10.0] * 17 + [None] * 7      # 17/24 = 70.8%
        rows = _hours(start, values)
        days = calc.daily_means(rows, "SO2", window_start=start, window_end=end)
        assert days[0][1] is None

    def test_the_gate_is_at_seventy_five_not_lower(self):
        """Pins the threshold itself.

        Testing only 70.8% and 75.0% leaves the gate free to slide anywhere
        between them, and a gate loosened to half would pass both. This sits
        one hour below the line: 12 of 24 is comfortably above a 50% gate and
        must still be refused.
        """
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        end = start + timedelta(hours=24)
        for valid_hours in (12, 15, 17):
            values = [10.0] * valid_hours + [None] * (24 - valid_hours)
            rows = _hours(start, values)
            days = calc.daily_means(rows, "SO2",
                                    window_start=start, window_end=end)
            assert days[0][1] is None, f"{valid_hours}/24 should be refused"

    def test_exactly_seventy_five_percent_is_sufficient(self):
        """The boundary itself. 18 of 24 is 75.0%, which passes."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        end = start + timedelta(hours=24)
        values = [10.0] * 18 + [None] * 6
        rows = _hours(start, values)
        days = calc.daily_means(rows, "SO2", window_start=start, window_end=end)
        assert days[0][1] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Monitoring window arithmetic
# ---------------------------------------------------------------------------
class TestWindowArithmetic:

    def test_a_whole_day_is_twenty_four_slots(self):
        """Midnight to midnight is 24 slots, not 25: the closing midnight
        belongs to the next day."""
        start = datetime(2026, 7, 8, 0, tzinfo=UTC)
        assert calc.hour_slots(start, start + timedelta(hours=24)) == 24

    def test_a_window_starting_mid_hour_touches_an_extra_slot(self):
        """25 hours from 04:30 spans 26 clock hours. Measured in elapsed hours
        instead, a report shows more than 100% capture."""
        start = datetime(2026, 7, 8, 4, 30, tzinfo=UTC)
        assert calc.hour_slots(start, start + timedelta(hours=25)) == 26
