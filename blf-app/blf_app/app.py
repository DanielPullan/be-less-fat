## BLF Flask by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Another test flask app for Be Less Fat.
## First attempted 29/07/2019, current attempt 14/02/2022. Third attempt 21/02/24 (seriously)

import os
import sqlite3
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
MEALS = ("Breakfast", "Lunch", "Dinner", "Snack")

# Activity multipliers for Mifflin-St Jeor (from archive/mifflin.py). 1 = potato, 5 = PT instructor.
ACTIVITY_LEVELS = {
    1: (1.2, "Sedentary (little or no exercise)"),
    2: (1.375, "Lightly active (exercise 1-3 days a week)"),
    3: (1.55, "Moderately active (exercise 3-5 days a week)"),
    4: (1.725, "Very active (hard exercise 6-7 days a week)"),
    5: (1.9, "Extremely active (physical job or training twice a day)"),
}
SEXES = ("male", "female")

DAILY_DEFICIT = 500                              # kcal/day, roughly 0.5 kg a week
MINIMUM_CALORIES = {"male": 1500, "female": 1200}  # never recommend going below this
KCAL_PER_KG = 7700                               # approx energy in 1 kg of body fat

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    pin_hash      TEXT    NOT NULL,
    height        REAL,              -- metres
    goalweight    REAL,              -- kg
    birthdate     TEXT,              -- YYYY-MM-DD
    sex           TEXT,              -- male / female (used for Mifflin-St Jeor)
    activity      INTEGER            -- 1-5, see ACTIVITY_LEVELS
);

CREATE TABLE IF NOT EXISTS weight (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    logdate TEXT    NOT NULL,        -- YYYY-MM-DD
    weight  REAL    NOT NULL         -- kg
);

CREATE TABLE IF NOT EXISTS calories (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    logdate  TEXT    NOT NULL,       -- YYYY-MM-DD
    food     TEXT    NOT NULL,
    calories INTEGER NOT NULL,
    meal     TEXT                    -- Breakfast / Lunch / Dinner / Snack / NULL
);
"""


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("BLF_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("BLF_DATABASE", str(BASE_DIR / "blf.sqlite3")),
    )
    if test_config:
        app.config.update(test_config)

    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    register_routes(app)
    return app


## Database stuff yo

def get_db():
    from flask import current_app

    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    # Add columns that didn't exist in older databases
    existing = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    for column, kind in (("birthdate", "TEXT"), ("sex", "TEXT"), ("activity", "INTEGER")):
        if column not in existing:
            db.execute(f"ALTER TABLE users ADD COLUMN {column} {kind}")
    db.commit()


## Functions and stuff yo

def today():
    return date.today().isoformat()


def bmiCalc(weight, height):
    """BMI = kg / m^2. Returns None if we don't have the data."""
    if not weight or not height:
        return None
    return weight / (height ** 2)


def bmiCategory(bmi):
    if bmi is None:
        return "Add your weight and height to see this"
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Healthy weight"
    if bmi < 30:
        return "Overweight"
    return "Obese"


def ageFrom(birthdate, on=None):
    on = on or date.today()
    born = date.fromisoformat(birthdate)
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def mifflin(height, weight, age, sex):
    """Basal metabolic rate (kcal/day). Height in metres, weight in kg."""
    bmr = (10 * weight) + (6.25 * height * 100) - (5 * age)
    return bmr + 5 if sex == "male" else bmr - 161


def calorieTarget(weight, height, goalweight, age, sex, activity, on=None):
    """Work out a daily calorie target and an estimate of when the goal will be reached.

    Returns None if we don't have enough info. Safeguards:
    - never recommends fewer than MINIMUM_CALORIES for the user's sex
    - if already at/below goal weight, the target is maintenance
    """
    if not all((weight, height, age, sex in SEXES, activity in ACTIVITY_LEVELS)):
        return None

    bmr = mifflin(height, weight, age, sex)
    maintenance = bmr * ACTIVITY_LEVELS[activity][0]
    floor = MINIMUM_CALORIES[sex]
    to_lose = (weight - goalweight) if goalweight else 0

    if to_lose > 0:
        target = max(maintenance - DAILY_DEFICIT, floor)
        capped = target == floor and maintenance - DAILY_DEFICIT < floor
    else:
        target = maintenance
        capped = False

    deficit = maintenance - target
    goal_date = None
    if to_lose > 0 and deficit > 0:
        days = (to_lose * KCAL_PER_KG) / deficit
        goal_date = (on or date.today()) + timedelta(days=round(days))

    return {
        "bmr": round(bmr),
        "maintenance": round(maintenance),
        "target": round(target),
        "minimum": floor,
        "capped": capped,
        "to_lose": round(to_lose, 1),
        "goal_date": goal_date,
        "weekly_loss": round(deficit * 7 / KCAL_PER_KG, 2),
    }


def target_for(user):
    """calorieTarget() for a user row, using their latest weight."""
    try:
        age = ageFrom(user["birthdate"]) if user["birthdate"] else None
    except ValueError:
        age = None
    return calorieTarget(
        getcurrent("weight"), user["height"], user["goalweight"], age, user["sex"], user["activity"]
    )


def current_user():
    """The logged-in user's row, or None for guests."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    if "user" not in g:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:  # user was deleted / db was wiped
            session.clear()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("You need to log in first.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def getcurrent(item):
    """Current value of weight / goalweight / height / date for the logged-in user."""
    user = current_user()
    if item == "date":
        return today()
    if user is None:
        return None
    if item == "weight":
        row = get_db().execute(
            "SELECT weight FROM weight WHERE user_id = ? ORDER BY logdate DESC, id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        return row["weight"] if row else None
    if item == "goalweight":
        return user["goalweight"]
    if item == "height":
        return user["height"]
    raise ValueError(f"getcurrent() doesn't know about {item!r}")


def calories_for(user_id, logdate):
    return get_db().execute(
        "SELECT food, calories, meal FROM calories WHERE user_id = ? AND logdate = ? ORDER BY id",
        (user_id, logdate),
    ).fetchall()


def parse_positive_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_non_negative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


## Routes and stuff yo

def register_routes(app):

    @app.context_processor
    def inject_username():
        # header.html uses `username` to decide which menu items / warning to show
        user = current_user()
        return {"username": user["username"] if user else "Guest"}

    @app.route("/")
    def home():
        weight = height = bmi = target = None
        eaten = 0
        status = "u ain't logged in"
        user = current_user()
        if user:
            target = target_for(user)
            eaten = sum(r["calories"] for r in calories_for(user["id"], today()))
            weight = getcurrent("weight")
            height = getcurrent("height")
            raw_bmi = bmiCalc(weight, height)
            bmi = round(raw_bmi, 1) if raw_bmi else None
            status = bmiCategory(raw_bmi)
        return render_template(
            "index.html", weight=weight, height=height, bmi=bmi, status=status, target=target, eaten=eaten
        )

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            pin = request.form.get("pin", "").strip()

            error = None
            if not username:
                error = "Username is required."
            elif len(password) < 6:
                error = "Password needs to be at least 6 characters."
            elif not pin.isdigit():
                error = "Pin must be numbers only."

            if error is None:
                db = get_db()
                try:
                    cur = db.execute(
                        "INSERT INTO users (username, password_hash, pin_hash) VALUES (?, ?, ?)",
                        (username, generate_password_hash(password), generate_password_hash(pin)),
                    )
                    db.commit()
                except sqlite3.IntegrityError:
                    error = f"Username {username!r} is already taken."
                else:
                    session.clear()
                    session["user_id"] = cur.lastrowid
                    flash("Account created. Add your height and goal weight to get started.")
                    return redirect(url_for("settings"))
            flash(error)

        return render_template("register.html", title="Register")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            pin = request.form.get("pin", "").strip()

            user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if (
                user is not None
                and check_password_hash(user["password_hash"], password)
                and check_password_hash(user["pin_hash"], pin)
            ):
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("me"))

            flash("Login failed. Check your username, password and pin.")

        return render_template("login.html", title="Login")

    @app.route("/logout", methods=["GET", "POST"])
    def logout():
        session.clear()
        return redirect(url_for("home"))

    @app.route("/me")
    @login_required
    def me():
        user = current_user()
        rows = calories_for(user["id"], today())
        totalcalories = sum(r["calories"] for r in rows)
        return render_template(
            "me.html",
            title="Me",
            user=user["username"],
            weight=getcurrent("weight"),
            height=getcurrent("height"),
            goalweight=getcurrent("goalweight"),
            food=totalcalories,
            target=target_for(user),
        )

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        user = current_user()
        if request.method == "POST":
            height = parse_positive_float(request.form.get("height"))
            goalweight = parse_positive_float(request.form.get("goalweight"))
            birthdate = request.form.get("birthdate", "").strip() or None
            sex = request.form.get("sex") or None
            activity = parse_non_negative_int(request.form.get("activity"))

            # Be forgiving: people will type 180 meaning cm
            if height is not None and height > 3:
                height = height / 100

            error = None
            if height is None or goalweight is None:
                error = "Height and goal weight need to be positive numbers."
            elif sex is not None and sex not in SEXES:
                error = "Pick a sex from the list."
            elif activity is not None and activity not in ACTIVITY_LEVELS:
                error = "Pick an activity level from the list."
            elif birthdate is not None:
                try:
                    age = ageFrom(birthdate)
                except ValueError:
                    error = "Date of birth needs to be a valid date."
                else:
                    if age < 18:
                        error = "Be Less Fat is not for under 18s."
                    elif age > 120:
                        error = "Date of birth doesn't look right."

            if error:
                flash(error)
            else:
                if bmiCalc(goalweight, height) < 18.5:
                    flash("Heads up: that goal weight would put you in the underweight BMI range.")
                db = get_db()
                db.execute(
                    "UPDATE users SET height = ?, goalweight = ?, birthdate = ?, sex = ?, activity = ? WHERE id = ?",
                    (height, goalweight, birthdate, sex, activity, user["id"]),
                )
                db.commit()
                flash("Saved.")
                return redirect(url_for("me"))

        return render_template(
            "settings.html", title="Settings", user=user, sexes=SEXES, activity_levels=ACTIVITY_LEVELS
        )

    @app.route("/track-weight", methods=["GET", "POST"])
    @login_required
    def trackweight():
        if request.method == "POST":
            weight = parse_positive_float(request.form.get("weight"))
            if weight is None:
                flash("Weight needs to be a positive number (kg).")
                return render_template("track-weight.html", title="Track Weight")

            db = get_db()
            db.execute(
                "INSERT INTO weight (user_id, logdate, weight) VALUES (?, ?, ?)",
                (current_user()["id"], today(), weight),
            )
            db.commit()
            return render_template("result-weight.html", title="Result", weight=weight)

        return render_template("track-weight.html", title="Track Weight")

    @app.route("/track-food", methods=["GET", "POST"])
    @login_required
    def trackfood():
        if request.method == "POST":
            food = request.form.get("food", "").strip()
            calories = parse_non_negative_int(request.form.get("calories"))
            meal = request.form.get("meal", "").strip().capitalize()
            if meal == "Snacks":
                meal = "Snack"
            if meal not in MEALS:
                meal = None

            if not food or calories is None:
                flash("Enter a food and a whole number of calories.")
                return render_template("track-food.html", title="Track Food", meals=MEALS)

            db = get_db()
            db.execute(
                "INSERT INTO calories (user_id, logdate, food, calories, meal) VALUES (?, ?, ?, ?, ?)",
                (current_user()["id"], today(), food, calories, meal),
            )
            db.commit()
            return render_template("result-food.html", title="Result", food=food, calories=calories)

        return render_template("track-food.html", title="Track Food", meals=MEALS)

    @app.route("/delete-last-weight", methods=["POST"])
    @login_required
    def deletelastweight():
        db = get_db()
        db.execute(
            "DELETE FROM weight WHERE id = ("
            " SELECT id FROM weight WHERE user_id = ? ORDER BY id DESC LIMIT 1)",
            (current_user()["id"],),
        )
        db.commit()
        flash("Last weight entry removed.")
        return redirect(url_for("me"))

    @app.route("/weight-history")
    @login_required
    def weighthistory():
        results = get_db().execute(
            "SELECT logdate, weight FROM weight WHERE user_id = ? ORDER BY logdate DESC, id DESC LIMIT 30",
            (current_user()["id"],),
        ).fetchall()
        return render_template("weight-history.html", title="Weight History", results=results)

    @app.route("/food-history")
    @login_required
    def foodhistory():
        logdate = request.args.get("date") or today()
        try:
            date.fromisoformat(logdate)
        except ValueError:
            abort(400)

        results = calories_for(current_user()["id"], logdate)
        per_meal = {meal: 0 for meal in MEALS}
        for row in results:
            if row["meal"] in per_meal:
                per_meal[row["meal"]] += row["calories"]

        return render_template(
            "food-history.html",
            title="Food History",
            logdate=logdate,
            results=results,
            totalcalories=sum(r["calories"] for r in results),
            breakfast=per_meal["Breakfast"],
            lunch=per_meal["Lunch"],
            dinner=per_meal["Dinner"],
            snacks=per_meal["Snack"],
        )

    @app.route("/notice")
    def notice():
        return render_template("notice.html", title="Notice")


def main():
    """Entry point for `uv run blf`."""
    app = create_app()
    app.run(
        host=os.environ.get("BLF_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLF_PORT", "5050")),  # 5000 is taken by AirPlay on macOS
        debug=os.environ.get("BLF_DEBUG") == "1",
    )


if __name__ == "__main__":
    main()
