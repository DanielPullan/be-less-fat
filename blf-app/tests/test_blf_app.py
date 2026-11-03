import pytest

from blf_app import __version__
from blf_app.app import bmiCalc, bmiCategory, create_app


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
