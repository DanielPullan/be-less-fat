import pytest

from blf_app import __version__
from datetime import date

from blf_app.app import ageFrom, bmiCalc, bmiCategory, calorieTarget, create_app, mifflin


@pytest.fixture
def client(tmp_path):
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
    assert b"Welcome Guest" in client.get("/").data
    assert client.get("/me").headers["Location"].endswith("/login")
    assert client.get("/track-food").status_code == 302


def test_register_login_logout(client):
    assert register(client).headers["Location"].endswith("/settings")
    client.get("/logout")
    assert client.get("/me").status_code == 302

    bad = client.post("/login", data={"username": "lea", "password": "hunter22", "pin": "9999"})
    assert b"Login failed" in bad.data

    ok = client.post("/login", data={"username": "lea", "password": "hunter22", "pin": "1234"})
    assert ok.headers["Location"].endswith("/me")
    assert client.get("/me").status_code == 200


def test_duplicate_username(client):
    register(client)
    client.get("/logout")
    assert b"already taken" in register(client).data


def test_new_user_pages_dont_crash(client):
    register(client)
    for page in ("/", "/me", "/weight-history", "/food-history", "/settings"):
        assert client.get(page).status_code == 200, page


def test_weight_tracking_and_bmi(client):
    register(client)
    client.post("/settings", data={"height": "180", "goalweight": "75"})  # cm gets converted
    client.post("/track-weight", data={"weight": "81"})
    client.post("/track-weight", data={"weight": "80"})

    home = client.get("/").data
    assert b"80.0 kg" in home and b"1.8 m" in home and b"24.7" in home

    me = client.get("/me").data
    assert b"5.0 kg to go" in me

    client.post("/delete-last-weight")
    assert b"81.0 kg" in client.get("/me").data


def test_bad_weight_rejected(client):
    register(client)
    assert b"positive number" in client.post("/track-weight", data={"weight": "lots"}).data
    assert b"Nothing tracked yet" in client.get("/weight-history").data


def test_food_tracking(client):
    register(client)
    client.post("/track-food", data={"food": "Tea", "calories": "40", "meal": "breakfast"})
    client.post("/track-food", data={"food": "Cheeky Nandos", "calories": "900", "meal": "Dinner"})
    client.post("/track-food", data={"food": "Custard", "calories": "150", "meal": ""})

    history = client.get("/food-history").data
    assert b"Cheeky Nandos" in history
    assert b"Breakfast: 40" in history
    assert b"Dinner: 900" in history
    assert b"1090" in history
    assert b"1090 calories today" in client.get("/me").data


def test_users_cant_see_each_others_data(client):
    register(client, "lea")
    client.post("/track-food", data={"food": "Secret Cake", "calories": "500"})
    client.get("/logout")
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
    assert b"to get a daily calorie target" in client.get("/me").data

    client.post("/settings", data={
        "height": "1.8", "goalweight": "75", "birthdate": "1990-01-01", "sex": "male", "activity": "1",
    })
    client.post("/track-weight", data={"weight": "80"})
    client.post("/track-food", data={"food": "Tea", "calories": "36"})

    age = ageFrom("1990-01-01")
    target = round(calorieTarget(80, 1.8, 75, age, "male", 1)["target"])
    for page in ("/", "/me"):
        body = client.get(page).data.decode()
        assert f"{target} kcal" in body
        assert f"{target - 36} kcal left today" in body


def test_settings_rejects_under_18(client):
    register(client)
    young = date.today().replace(year=date.today().year - 16).isoformat()
    resp = client.post("/settings", data={"height": "1.8", "goalweight": "75", "birthdate": young, "sex": "male"})
    assert b"not for under 18s" in resp.data
