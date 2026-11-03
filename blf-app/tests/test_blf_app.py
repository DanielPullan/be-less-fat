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
    row = 'text-slate-900">{}</td>'
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
