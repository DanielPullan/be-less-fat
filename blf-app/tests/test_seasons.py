from datetime import date

from blf_app import seasons


def test_monthly_themes():
    assert "pride" in seasons.extra_themes(date(2026, 6, 10))
    assert "festive" in seasons.extra_themes(date(2026, 12, 1))
    assert "heritage" in seasons.extra_themes(date(2026, 10, 15))
    assert not {"pride", "festive", "heritage"} & set(seasons.extra_themes(date(2026, 1, 15)))


def test_all_year_themes_always_offered():
    for day in (date(2026, 1, 1), date(2026, 7, 7)):
        assert set(seasons.ALL_YEAR_THEMES) <= set(seasons.extra_themes(day))


def test_occasion_windows():
    # Safer Internet Day 2026 is Tuesday 10 February: offered from the 9th to the 15th
    assert seasons.nth_weekday(2026, 2, 1, 2) == date(2026, 2, 10)
    assert "safer" in seasons.extra_themes(date(2026, 2, 9))
    assert "safer" in seasons.extra_themes(date(2026, 2, 15))
    assert "safer" not in seasons.extra_themes(date(2026, 2, 16))
    assert "diwali" in seasons.extra_themes(date(2026, 11, 7))


def test_season_string():
    assert seasons.season(date(2026, 11, 5)) == "fireworks"
    assert seasons.season(date(2026, 12, 31)) == "fireworks december"
    assert seasons.season(date(2026, 6, 24)) == "balloons june"
    assert "day-pi" in seasons.season(date(2026, 3, 14))
    assert seasons.season(date(2026, 8, 12)) == ""


def test_pretend_date(monkeypatch):
    monkeypatch.setenv("BLF_SEASON_DATE", "2026-12-25")
    assert seasons.today_uk() == date(2026, 12, 25)
    assert "festive" in seasons.extra_themes()


def test_pages_offer_todays_themes(client_factory=None):
    import tempfile, os
    from blf_app.app import create_app
    d = tempfile.mkdtemp()
    os.environ["BLF_SEASON_DATE"] = "2026-06-24"
    try:
        app = create_app({"TESTING": True, "DATABASE": os.path.join(d, "t.db"), "SECRET_KEY": "x"})
        html = app.test_client().get("/").data.decode()
        assert 'name="blf-season" content="balloons june"' in html
        assert 'value="pride"' in html and 'value="festive"' not in html
        about = app.test_client().get("/notice").data.decode()
        assert "?celebrate=ghost" in about
    finally:
        del os.environ["BLF_SEASON_DATE"]
