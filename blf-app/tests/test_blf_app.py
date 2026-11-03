import pytest

from blf_app import __version__
from datetime import date

from blf_app.app import ageFrom, bmiCalc, bmiCategory, calorieTarget, create_app, mifflin


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"), "SECRET_KEY": "test",
                      "WTF_CSRF_ENABLED": False})
    return app.test_client()


@pytest.fixture
def csrf_client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"), "SECRET_KEY": "test"})
    return app.test_client()


def register(client, username="lea", password="hunter22", pin="1234"):
    return client.post("/register", data={"username": username, "password": password, "pin": pin})


def test_version():
    assert __version__ == '0.1.0'


def test_bmi():
    assert round(bmiCalc(80, 1.8), 1) == 24.7
    assert bmiCalc(None, 1.8) is None
    assert bmiCategory(24.7) == "Healthy weight"
    assert bmiCategory(31) == "Obese"


def test_guest_pages(client):
    assert b"Create an account" in client.get("/").data
    assert client.get("/settings").headers["Location"].endswith("/login")
    assert client.get("/track-food").status_code == 302


def test_register_login_logout(client):
    assert register(client).headers["Location"].endswith("/settings")
    client.post("/logout")
    assert client.get("/settings").status_code == 302

    bad = client.post("/login", data={"username": "lea", "password": "hunter22", "pin": "9999"})
    assert b"Login failed" in bad.data

    ok = client.post("/login", data={"username": "lea", "password": "hunter22", "pin": "1234"})
    assert ok.headers["Location"] == "/"
    assert b"Hello, Lea" in client.get("/").data


def test_duplicate_username(client):
    register(client)
    client.post("/logout")
    assert b"already taken" in register(client).data


def test_new_user_pages_dont_crash(client):
    register(client)
    for page in ("/", "/weight-history", "/food-history", "/settings", "/notice"):
        assert client.get(page).status_code == 200, page


def test_weight_tracking_and_bmi(client):
    register(client)
    client.post("/settings", data={"height": "180", "goalweight": "75"})  # cm gets converted
    client.post("/track-weight", data={"weight": "81"})
    client.post("/track-weight", data={"weight": "80"})

    home = client.get("/").data.decode()
    assert "80.0" in home and "24.7" in home and "Healthy weight" in home
    assert "5.0 kg to go" in home
    assert "▼ 1.0 kg" in home

    history = client.get("/weight-history").data.decode()
    assert "<svg" in history and "Goal 75.0 kg" in history

    client.post("/delete-last-weight")
    assert "81.0" in client.get("/").data.decode()


def test_bad_weight_rejected(client):
    register(client)
    assert b"positive number" in client.post("/track-weight", data={"weight": "lots"}, follow_redirects=True).data
    assert b"Nothing tracked yet" in client.get("/weight-history").data


def test_food_tracking(client):
    register(client)
    client.post("/track-food", data={"food": "Tea", "calories": "40", "meal": "breakfast"})
    client.post("/track-food", data={"food": "Cheeky Nandos", "calories": "900", "meal": "Dinner"})
    client.post("/track-food", data={"food": "Custard", "calories": "150", "meal": ""})

    history = client.get("/food-history").data.decode()
    assert "Cheeky Nandos" in history
    assert "1090 kcal" in history
    assert "1090" in client.get("/").data.decode()


def test_users_cant_see_each_others_data(client):
    register(client, "lea")
    client.post("/track-food", data={"food": "Secret Cake", "calories": "500"})
    client.post("/logout")
    register(client, "dan")
    assert b"Secret Cake" not in client.get("/food-history").data


def test_mifflin_and_age():
    assert mifflin(1.8, 80, 30, "male") == 1780
    assert mifflin(1.6, 55, 60, "female") == 1089
    assert ageFrom("1990-06-15", on=date(2026, 6, 14)) == 35
    assert ageFrom("1990-06-15", on=date(2026, 6, 15)) == 36


def test_calorie_target_deficit_and_estimate():
    t = calorieTarget(80, 1.8, 75, 30, "male", 1, on=date(2026, 1, 1))
    assert t["maintenance"] == 2136
    assert t["target"] == 1636
    assert not t["capped"]
    assert t["to_lose"] == 5
    assert t["goal_date"] == date(2026, 3, 19)  # 5kg * 7700 / 500 = 77 days


def test_calorie_target_never_below_minimum():
    t = calorieTarget(55, 1.6, 50, 60, "female", 1)
    assert t["target"] == 1200
    assert t["capped"]


def test_calorie_target_at_goal_is_maintenance():
    t = calorieTarget(70, 1.8, 75, 30, "male", 3)
    assert t["target"] == t["maintenance"]
    assert t["goal_date"] is None


def test_calorie_target_needs_profile():
    assert calorieTarget(80, 1.8, 75, None, "male", 1) is None
    assert calorieTarget(80, 1.8, 75, 30, None, 1) is None
    assert calorieTarget(None, 1.8, 75, 30, "male", 1) is None


def test_calorie_target_on_pages(client):
    register(client)
    assert b"to get a daily calorie target" in client.get("/").data

    client.post("/settings", data={
        "height": "1.8", "goalweight": "75", "birthdate": "1990-01-01", "sex": "male", "activity": "1",
    })
    client.post("/track-weight", data={"weight": "80"})
    client.post("/track-food", data={"food": "Tea", "calories": "36"})

    age = ageFrom("1990-01-01")
    target = round(calorieTarget(80, 1.8, 75, age, "male", 1)["target"])
    body = client.get("/").data.decode()
    assert f"of {target} kcal" in body
    assert f"{target - 36} kcal left" in body


def test_settings_rejects_under_18(client):
    register(client)
    young = date.today().replace(year=date.today().year - 16).isoformat()
    resp = client.post("/settings", data={"height": "1.8", "goalweight": "75", "birthdate": young, "sex": "male"})
    assert b"not for under 18s" in resp.data


def test_remove_food_entry(client):
    register(client)
    client.post("/track-food", data={"food": "Custard", "calories": "150"})
    client.post("/track-food", data={"food": "Tea", "calories": "40"})
    client.post("/delete-food/1")
    history = client.get("/food-history").data.decode()
    row = 'text-slate-900">{}</span>'
    assert row.format("Custard") not in history and row.format("Tea") in history


def test_cant_remove_someone_elses_food(client):
    register(client, "lea")
    client.post("/track-food", data={"food": "Secret Cake", "calories": "500"})
    client.post("/logout")
    register(client, "dan")
    assert client.post("/delete-food/1").status_code == 404


def test_next_only_goes_to_this_site(client):
    register(client)
    resp = client.post("/track-weight", data={"weight": "80", "next": "https://evil.example/"})
    assert resp.headers["Location"] == "/weight-history"
    resp = client.post("/track-weight", data={"weight": "80", "next": "/"})
    assert resp.headers["Location"] == "/"


def test_forms_need_csrf_token(csrf_client):
    resp = csrf_client.post("/register", data={"username": "lea", "password": "hunter22", "pin": "1234"})
    assert resp.status_code == 400
    assert b'name="csrf_token"' in csrf_client.get("/register").data


def test_security_headers(client):
    headers = client.get("/").headers
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"


def test_food_form_lists_meals(client):
    register(client)
    for page in ("/", "/food-history"):
        html = client.get(page).data.decode()
        for meal in ("Breakfast", "Lunch", "Dinner", "Snack"):
            assert f'<option value="{meal}">' in html, (page, meal)


def test_weigh_in_for_a_past_date(client):
    register(client)
    client.post("/track-weight", data={"weight": "84", "logdate": "2026-01-05"})
    assert "5 January 2026" in client.get("/weight-history?range=all").data.decode()
    future = client.post("/track-weight", data={"weight": "84", "logdate": "2999-01-01"}, follow_redirects=True)
    assert b"today or earlier" in future.data


def test_import_preview_then_save_then_undo(client):
    import io
    import json
    register(client)
    client.post("/track-weight", data={"weight": "90", "logdate": "2026-01-02"})
    csv_file = (io.BytesIO(b"Date,Weight (kg)\n2026-01-01,91.0\n2026-01-02,90.5\n2026-01-03,90.1\n"), "export.csv")
    preview = client.post("/import-weights", data={"step": "preview", "file": csv_file, "unit": "kg", "order": "dmy"},
                          content_type="multipart/form-data").data.decode()
    assert "Found 3 weigh-ins" in preview
    assert "already has a weigh-in here" in preview
    # Nothing saved yet
    assert client.get("/").data.decode().count("Imported") == 0

    rows = json.dumps([{"date": "2026-01-01", "kg": 91.0}, {"date": "2026-01-02", "kg": 90.5}, {"date": "2026-01-03", "kg": 90.1}])
    saved = client.post("/import-weights", data={"step": "save", "rows": rows, "existing": "skip"})
    location = saved.headers["Location"]
    assert "imported=1" in location
    page = client.get(location).data.decode()
    assert "Imported 2 weigh-ins, skipped 1 day" in page
    assert "Undo this import" in page
    assert "90.0 kg" in page  # kept the one already tracked

    client.post("/undo-import/1")
    page = client.get("/weight-history?range=all").data.decode()
    assert "91.0 kg" not in page and "90.0 kg" in page


def test_import_replace_existing_day(client):
    import json
    register(client)
    client.post("/track-weight", data={"weight": "90", "logdate": "2026-01-02"})
    rows = json.dumps([{"date": "2026-01-02", "kg": 90.5}])
    client.post("/import-weights", data={"step": "save", "rows": rows, "existing": "replace"})
    page = client.get("/weight-history?range=all").data.decode()
    assert "90.5 kg" in page and "90.0 kg" not in page


def test_import_save_rejects_bad_rows(client):
    import json
    register(client)
    rows = json.dumps([{"date": "2999-01-01", "kg": 80}, {"date": "2026-01-01", "kg": 5000}, {"oops": 1}])
    resp = client.post("/import-weights", data={"step": "save", "rows": rows}, follow_redirects=True)
    assert b"nothing to import" in resp.data


def test_import_from_pasted_text_in_pounds(client):
    register(client)
    page = client.post("/import-weights", data={"step": "preview", "text": "2026-01-01 200\n2026-01-08 199", "unit": "lb"}).data.decode()
    assert "Found 2 weigh-ins" in page and "90.7 kg" in page


def test_remove_one_weigh_in_and_not_someone_elses(client):
    register(client, "lea")
    client.post("/track-weight", data={"weight": "70", "logdate": "2026-01-01"})
    client.post("/logout")
    register(client, "dan")
    assert client.post("/delete-weight/1").status_code == 404
    client.post("/track-weight", data={"weight": "80", "logdate": "2026-01-01"})
    client.post("/delete-weight/2")
    assert "80.0 kg" not in client.get("/weight-history?range=all").data.decode()


def test_long_history_shows_latest_50_with_show_all(client):
    import json
    from datetime import date, timedelta
    register(client)
    start = date(2025, 1, 1)
    rows = json.dumps([{"date": (start + timedelta(days=i)).isoformat(), "kg": 90 - i / 100} for i in range(80)])
    client.post("/import-weights", data={"step": "save", "rows": rows})
    page = client.get("/weight-history?range=all").data.decode()
    assert "Showing the latest 50 of 80" in page and "rows=all" in page
    page = client.get("/weight-history?range=all&rows=all").data.decode()
    assert "Showing the latest" not in page


def test_nutrient_targets_follow_uk_guidance():
    from blf_app.app import nutrientTargets
    t = nutrientTargets(80, 3)
    assert t["protein"]["target"] == 60 and t["protein"]["per_kg"] == 0.75
    assert t["fibre"]["target"] == 30
    assert nutrientTargets(80, 5)["protein"]["per_kg"] == 1.2
    assert nutrientTargets(80, None)["protein"]["target"] == 60
    assert nutrientTargets(None, 3)["protein"] is None
    assert nutrientTargets(None, None)["fibre"]["target"] == 30


def test_high_protein_rule():
    from blf_app.app import is_high_protein
    assert is_high_protein(31, 165)        # chicken breast: 18.8 g per 100 kcal
    assert is_high_protein(10, 100)        # exactly the bar
    assert not is_high_protein(9.9, 100)
    assert not is_high_protein(None, 100)
    assert not is_high_protein(5, 0)


def test_protein_and_fibre_tracking(client):
    register(client)
    client.post("/settings", data={"height": "1.8", "goalweight": "75", "birthdate": "1990-01-01", "sex": "male", "activity": "3"})
    client.post("/track-weight", data={"weight": "80"})
    client.post("/track-food", data={"food": "Porridge", "calories": "300", "protein": "10.5", "fibre": "8"})
    client.post("/track-food", data={"food": "Chicken", "calories": "250", "protein": "40"})
    client.post("/track-food", data={"food": "Tea", "calories": "20"})

    home = client.get("/").data.decode()
    assert "50.5 g</strong> of 60 g" in home and "9.5 g to go" in home
    assert "8 g</strong> of 30 g" in home
    assert "2 foods today have no fibre amount" in home
    assert "0.75 g for each kg" in home and "NHS advises" in home

    history = client.get("/food-history").data.decode()
    assert "10.5 g" in history and "40 g" in history


def test_protein_goal_reached_and_bad_grams(client):
    register(client)
    client.post("/track-weight", data={"weight": "50"})
    client.post("/track-food", data={"food": "Steak", "calories": "600", "protein": "45"})
    assert "✓ reached" in client.get("/").data.decode()
    bad = client.post("/track-food", data={"food": "X", "calories": "1", "protein": "lots"}, follow_redirects=True)
    assert b"between 0 and 1000" in bad.data


def test_high_protein_foods_and_meals_are_marked(client):
    register(client)
    client.post("/track-food", data={"food": "Chicken breast", "calories": "165", "protein": "31", "meal": "Lunch"})
    client.post("/track-food", data={"food": "Rice", "calories": "200", "protein": "4", "meal": "Lunch"})
    client.post("/track-food", data={"food": "Skyr", "calories": "100", "protein": "17", "meal": "Snack"})
    flashed = client.post("/track-food", data={"food": "Tuna", "calories": "110", "protein": "25"}, follow_redirects=True).data.decode()
    assert "High protein: 22.7 g per 100 kcal" in flashed

    page = client.get("/food-history").data.decode()
    assert page.count(">High protein</span>") == 1 + 4  # the explainer's sample + chicken, skyr, tuna + the snack meal
    assert 'Chicken breast</span> <span' in page and 'Rice</span></td>' in page
    # Lunch: 35 g over 365 kcal = 9.6 g per 100 kcal, so not a high-protein meal
    lunch = page[page.index(">Lunch</h2>"):page.index(">Dinner</h2>")]
    assert "35 g protein" in lunch and "High protein" not in lunch


def test_high_fibre_rule():
    from blf_app.app import is_high_fibre
    assert is_high_fibre(3.8, 37)       # Weetabix: 10.3 g per 100 g
    assert is_high_fibre(6, 100)        # exactly the NHS bar
    assert not is_high_fibre(8.5, 250)  # a big bowl of porridge: 3.4 g per 100 g
    assert not is_high_fibre(5, None)   # no portion, can't say
    assert not is_high_fibre(None, 100)


def test_high_fibre_foods_and_meals_are_marked(client):
    register(client)
    flashed = client.post("/track-food", data={"food": "Weetabix", "calories": "136", "fibre": "3.8", "portion": "37", "meal": "Breakfast"},
                          follow_redirects=True).data.decode()
    assert "37 g of Weetabix" in flashed and "High fibre: 10.3 g per 100 g" in flashed
    client.post("/track-food", data={"food": "Porridge", "calories": "320", "fibre": "8.5", "portion": "250", "meal": "Lunch"})
    client.post("/track-food", data={"food": "Lentils", "calories": "230", "fibre": "16", "meal": "Dinner"})  # no portion

    page = client.get("/food-history").data.decode()
    assert 'Weetabix</span> <span class="text-xs text-slate-500 whitespace-nowrap">37 g</span> <span' in page
    assert page.count(">High fibre</span>") == 1 + 2   # explainer sample + Weetabix + the breakfast meal
    dinner = page[page.index(">Dinner</h2>"):page.index(">Snack</h2>")]
    assert "High fibre" not in dinner


def test_portion_checks(client):
    register(client)
    bad = client.post("/track-food", data={"food": "X", "calories": "10", "fibre": "50", "portion": "20"}, follow_redirects=True)
    assert b"weigh more than the whole portion" in bad.data
    bad = client.post("/track-food", data={"food": "X", "calories": "10", "portion": "0"}, follow_redirects=True)
    assert b"Portion needs to be grams" in bad.data
