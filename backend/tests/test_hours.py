from datetime import datetime

from app.services.hours import status_at

THU_2330 = datetime(2026, 10, 29, 23, 30)  # Thursday
SAT_1000 = datetime(2026, 10, 31, 10, 0)  # Saturday
FRI_0100 = datetime(2026, 10, 30, 1, 0)  # Friday, just after midnight


def test_24_7():
    assert status_at("24/7", "pharmacy", THU_2330) == ("open", "listed")


def test_simple_range_open_and_closed():
    assert status_at("Mo-Su 08:00-23:00", "fuel", THU_2330) == ("closed", "listed")
    assert status_at("Mo-Su 08:00-23:45", "fuel", THU_2330) == ("open", "listed")


def test_no_days_means_every_day():
    assert status_at("08:00-22:00", "food_shop", SAT_1000) == ("open", "listed")


def test_several_day_groups():
    hours = "Mo-Fr 09:00-17:00; Sa 10:00-14:00; Su off"
    assert status_at(hours, "pharmacy", SAT_1000) == ("open", "listed")
    assert status_at(hours, "pharmacy", THU_2330) == ("closed", "listed")
    assert status_at(hours, "pharmacy", datetime(2026, 11, 1, 11, 0)) == ("closed", "listed")  # Sunday


def test_split_ranges_and_day_list():
    hours = "Mo,We,Fr 09:00-13:00,14:00-18:00"
    assert status_at(hours, "clinic", datetime(2026, 10, 30, 13, 30)) == ("closed", "listed")  # Friday lunch
    assert status_at(hours, "clinic", datetime(2026, 10, 30, 15, 0)) == ("open", "listed")


def test_past_midnight():
    assert status_at("Mo-Su 18:00-02:00", "food_shop", FRI_0100) == ("open", "listed")
    assert status_at("Mo-Su 18:00-02:00", "food_shop", datetime(2026, 10, 30, 3, 0)) == ("closed", "listed")


def test_missing_hours_use_blueprint_defaults():
    assert status_at(None, "police", THU_2330) == ("open", "default")
    assert status_at(None, "hospital", THU_2330) == ("open", "default")
    assert status_at(None, "pharmacy", THU_2330) == ("unknown", "missing")


def test_unreadable_hours_are_unknown_not_guessed():
    assert status_at("sunrise-sunset", "atm", THU_2330) == ("unknown", "unreadable")
    assert status_at("Mo-Fr 9am to 5pm", "atm", THU_2330) == ("unknown", "unreadable")
