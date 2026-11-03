## BLF Flask by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Another test flask app for Be Less Fat.
## First attempted 29/07/2019, current attempt 14/02/2022. Third attempt 21/02/24 (seriously)

import json
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
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

from . import importer, seasons

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

# Protein, in grams per kg of body weight, by activity level. 0.8 g/kg is the usual adult reference
# intake (UK RNI 0.75, EFSA 0.83); people who exercise regularly are advised 1.2-2.0 g/kg
# (International Society of Sports Nutrition), rising with how much they train.
PROTEIN_PER_KG = {1: 0.8, 2: 1.0, 3: 1.2, 4: 1.4, 5: 1.6}
PROTEIN_PER_KG_OVER_65 = 1.0   # at least this from 65 (PROT-AGE / ESPEN advice for older adults)
# Fibre, grams a day: the US Institute of Medicine adequate intakes, by sex and age.
# (The UK's SACN advises 30 g a day for every adult.)
FIBRE_PER_DAY = {("male", "under51"): 38, ("male", "51plus"): 30, ("female", "under51"): 25, ("female", "51plus"): 21}

# Same policy as SecureMy.School: only our own scripts; Google Fonts only for the optional fonts
CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)

csrf = CSRFProtect()

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
    weight  REAL    NOT NULL,        -- kg
    import_id INTEGER                -- set on weigh-ins brought in from another app, so an import can be undone
);

CREATE TABLE IF NOT EXISTS calories (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    logdate  TEXT    NOT NULL,       -- YYYY-MM-DD
    food     TEXT    NOT NULL,
    calories INTEGER NOT NULL,
    meal     TEXT,                   -- Breakfast / Lunch / Dinner / Snack / NULL
    protein  REAL,                   -- grams, optional
    fibre    REAL                    -- grams, optional
);
"""


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("BLF_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("BLF_DATABASE", str(BASE_DIR / "blf.sqlite3")),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # imported files
    )
    if test_config:
        app.config.update(test_config)

    csrf.init_app(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

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
    food_columns = {row["name"] for row in db.execute("PRAGMA table_info(calories)")}
    for column in ("protein", "fibre"):
        if column not in food_columns:
            db.execute(f"ALTER TABLE calories ADD COLUMN {column} REAL")
    if "import_id" not in {row["name"] for row in db.execute("PRAGMA table_info(weight)")}:
        db.execute("ALTER TABLE weight ADD COLUMN import_id INTEGER")
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


def nutrientTargets(weight, age, sex, activity):
    """Daily protein and fibre goals (grams). Either can be None if we don't know enough yet.

    Protein comes from current weight, activity level and age; fibre from sex and age.
    """
    protein = None
    if weight:
        per_kg = PROTEIN_PER_KG.get(activity, PROTEIN_PER_KG[1])
        older = age is not None and age >= 65
        if older:
            per_kg = max(per_kg, PROTEIN_PER_KG_OVER_65)
        protein = {
            "target": int(round(weight * per_kg)),
            "per_kg": per_kg,
            "weight": weight,
            "older": older,
            "guessed_activity": activity not in PROTEIN_PER_KG,
        }
    fibre = None
    if sex in SEXES and age is not None:
        group = "under51" if age < 51 else "51plus"
        fibre = {"target": FIBRE_PER_DAY[(sex, group)], "sex": sex, "group": group}
    return {"protein": protein, "fibre": fibre}


def user_age(user):
    try:
        return ageFrom(user["birthdate"]) if user["birthdate"] else None
    except ValueError:
        return None


def nutrients_for(user):
    return nutrientTargets(getcurrent("weight"), user_age(user), user["sex"], user["activity"])


def day_totals(rows):
    """Calories, protein and fibre for a day's food. Protein/fibre count only the foods that have them."""
    return {
        "calories": sum(r["calories"] for r in rows),
        "protein": round(sum(r["protein"] or 0 for r in rows), 1),
        "fibre": round(sum(r["fibre"] or 0 for r in rows), 1),
        "missing_protein": sum(1 for r in rows if r["protein"] is None),
        "missing_fibre": sum(1 for r in rows if r["fibre"] is None),
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
        "SELECT id, food, calories, meal, protein, fibre FROM calories WHERE user_id = ? AND logdate = ? ORDER BY id",
        (user_id, logdate),
    ).fetchall()


def parse_positive_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_grams(value):
    """An optional amount in grams: None if blank, False if it isn't a sensible number."""
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return False
    return round(number, 1) if 0 <= number <= 1000 else False


def parse_non_negative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def weight_chart(rows, goalweight=None, width=640, height=220):
    """Inline SVG line chart data for a run of weigh-ins (oldest first). None if fewer than 2.

    Points are spaced by date, so gaps between weigh-ins show as gaps in time.
    """
    if len(rows) < 2:
        return None
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 28
    days = [date.fromisoformat(r["logdate"]) for r in rows]
    span = max((days[-1] - days[0]).days, 1)
    weights = [r["weight"] for r in rows]
    values = weights + ([goalweight] if goalweight else [])
    lo, hi = min(values), max(values)
    if hi - lo < 2:
        lo, hi = lo - 1, hi + 1
    lo, hi = lo - (hi - lo) * 0.1, hi + (hi - lo) * 0.1

    def x(d):
        return pad_l + (d - days[0]).days * (width - pad_l - pad_r) / span

    def y(v):
        return pad_t + (hi - v) * (height - pad_t - pad_b) / (hi - lo)

    points = [{"x": round(x(d), 1), "y": round(y(r["weight"]), 1), "weight": r["weight"], "date": r["logdate"]}
              for d, r in zip(days, rows)]
    ticks = [round(lo + (hi - lo) * k / 4, 1) for k in range(5)]
    return {
        "width": width,
        "height": height,
        "left": pad_l,
        "right": width - pad_r,
        "bottom": height - pad_b,
        "points": points,
        "dots": len(points) <= 60,
        "path": " ".join(f"{'M' if i == 0 else 'L'}{p['x']},{p['y']}" for i, p in enumerate(points)),
        "area": f"M{points[0]['x']},{height - pad_b} "
                + " ".join(f"L{p['x']},{p['y']}" for p in points)
                + f" L{points[-1]['x']},{height - pad_b} Z",
        "ticks": [{"value": t, "y": round(y(t), 1)} for t in ticks],
        "goal_y": round(y(goalweight), 1) if goalweight else None,
        "first": rows[0]["logdate"],
        "last": rows[-1]["logdate"],
    }


WEIGHT_RANGES = {"3m": ("3 months", 91), "1y": ("1 year", 365), "all": ("All", None)}


def ukdate(value):
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{d.day} {d.strftime('%B %Y')}"


def safe_next():
    """The form's `next` page, if it's a page on this site (never an outside address)."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def profile_complete(user):
    return all(user[k] for k in ("height", "goalweight", "birthdate", "sex", "activity"))


## Routes and stuff yo

def register_routes(app):

    app.template_filter("ukdate")(ukdate)

    @app.template_filter("shortdate")
    def shortdate(value):
        d = date.fromisoformat(value) if isinstance(value, str) else value
        return f"{d.day} {d.strftime('%b')}"

    @app.context_processor
    def inject_user():
        return {"user": current_user(), "meals": MEALS, "today_iso": today,
                "theme_options": seasons.theme_options(), "season": seasons.season()}

    @app.route("/")
    def home():
        user = current_user()
        if not user:
            return render_template("index.html", title="Be Less Fat")

        weight = getcurrent("weight")
        raw_bmi = bmiCalc(weight, user["height"])
        rows = calories_for(user["id"], today())
        recent = get_db().execute(
            "SELECT logdate, weight FROM weight WHERE user_id = ? ORDER BY logdate DESC, id DESC LIMIT 2",
            (user["id"],),
        ).fetchall()
        change = round(recent[0]["weight"] - recent[1]["weight"], 1) if len(recent) == 2 else None
        return render_template(
            "dashboard.html",
            title="Today",
            today_date=date.today(),
            weight=weight,
            change=change,
            bmi=round(raw_bmi, 1) if raw_bmi else None,
            status=bmiCategory(raw_bmi),
            target=target_for(user),
            eaten=sum(r["calories"] for r in rows),
            totals=day_totals(rows),
            nutrients=nutrients_for(user),
            rows=rows,
            profile_complete=profile_complete(user),
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
                    flash("Account created. Add your details to get a daily calorie target.", "success")
                    return redirect(url_for("settings"))
            flash(error, "error")

        return render_template("register.html", title="Create an account")

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
                return redirect(url_for("home"))

            flash("Login failed. Check your username, password and pin.", "error")

        return render_template("login.html", title="Log in")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("home"))

    @app.route("/me")
    def me():
        return redirect(url_for("home"))

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
                flash(error, "error")
            else:
                if bmiCalc(goalweight, height) < 18.5:
                    flash("Heads up: that goal weight would put you in the underweight BMI range.", "warning")
                db = get_db()
                db.execute(
                    "UPDATE users SET height = ?, goalweight = ?, birthdate = ?, sex = ?, activity = ? WHERE id = ?",
                    (height, goalweight, birthdate, sex, activity, user["id"]),
                )
                db.commit()
                flash("Settings saved.", "success")
                return redirect(url_for("home"))

        return render_template(
            "settings.html", title="Settings", sexes=SEXES, activity_levels=ACTIVITY_LEVELS
        )

    @app.route("/track-weight", methods=["GET", "POST"])
    @login_required
    def trackweight():
        if request.method == "GET":
            return redirect(url_for("weighthistory"))
        weight = parse_positive_float(request.form.get("weight"))
        logdate = request.form.get("logdate") or today()
        try:
            day = date.fromisoformat(logdate)
        except ValueError:
            day = None
        if weight is None:
            flash("Weight needs to be a positive number (kg).", "error")
        elif day is None or day > date.today() or day.year < 1900:
            flash("The date needs to be today or earlier.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO weight (user_id, logdate, weight) VALUES (?, ?, ?)",
                (current_user()["id"], day.isoformat(), weight),
            )
            db.commit()
            when = "" if day == date.today() else f" for {ukdate(day)}"
            flash(f"Weight of {weight:g} kg tracked{when}.", "success")
        return redirect(safe_next() or url_for("weighthistory"))

    @app.route("/track-food", methods=["GET", "POST"])
    @login_required
    def trackfood():
        if request.method == "GET":
            return redirect(url_for("foodhistory"))
        food = request.form.get("food", "").strip()
        calories = parse_non_negative_int(request.form.get("calories"))
        meal = request.form.get("meal", "").strip().capitalize()
        if meal == "Snacks":
            meal = "Snack"
        if meal not in MEALS:
            meal = None

        protein = parse_grams(request.form.get("protein"))
        fibre = parse_grams(request.form.get("fibre"))

        if not food or calories is None:
            flash("Enter a food and a whole number of calories.", "error")
        elif protein is False or fibre is False:
            flash("Protein and fibre need to be grams between 0 and 1000, or left blank.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO calories (user_id, logdate, food, calories, meal, protein, fibre) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (current_user()["id"], today(), food, calories, meal, protein, fibre),
            )
            db.commit()
            extras = "".join(f", {v:g} g {k}" for k, v in (("protein", protein), ("fibre", fibre)) if v is not None)
            flash(f"{food} ({calories} kcal{extras}) tracked.", "success")
        return redirect(safe_next() or url_for("foodhistory"))

    @app.route("/delete-food/<int:entry_id>", methods=["POST"])
    @login_required
    def deletefood(entry_id):
        db = get_db()
        row = db.execute(
            "SELECT logdate FROM calories WHERE id = ? AND user_id = ?", (entry_id, current_user()["id"])
        ).fetchone()
        if row is None:
            abort(404)
        db.execute("DELETE FROM calories WHERE id = ?", (entry_id,))
        db.commit()
        flash("Food entry removed.", "success")
        return redirect(safe_next() or url_for("foodhistory", date=row["logdate"]))

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
        flash("Last weight entry removed.", "success")
        return redirect(url_for("weighthistory"))

    @app.route("/delete-weight/<int:entry_id>", methods=["POST"])
    @login_required
    def deleteweight(entry_id):
        db = get_db()
        cur = db.execute("DELETE FROM weight WHERE id = ? AND user_id = ?", (entry_id, current_user()["id"]))
        db.commit()
        if cur.rowcount == 0:
            abort(404)
        flash("Weigh-in removed.", "success")
        return redirect(safe_next() or url_for("weighthistory"))

    @app.route("/weight-history")
    @login_required
    def weighthistory():
        user = current_user()
        db = get_db()
        wanted = request.args.get("range")
        days = None
        if wanted not in WEIGHT_RANGES:
            # Default to 3 months, unless that would leave too little to draw (e.g. only old, imported data)
            recent = db.execute(
                "SELECT COUNT(*) FROM weight WHERE user_id = ? AND logdate >= ?",
                (user["id"], (date.today() - timedelta(days=91)).isoformat()),
            ).fetchone()[0]
            wanted = "3m" if recent >= 2 else "all"
        days = WEIGHT_RANGES[wanted][1]
        since = (date.today() - timedelta(days=days)).isoformat() if days else "0000-00-00"
        results = db.execute(
            "SELECT id, logdate, weight, import_id FROM weight WHERE user_id = ? AND logdate >= ?"
            " ORDER BY logdate DESC, id DESC",
            (user["id"], since),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM weight WHERE user_id = ?", (user["id"],)).fetchone()[0]

        imported = None
        import_id = request.args.get("imported", type=int)
        if import_id:
            count = db.execute(
                "SELECT COUNT(*) FROM weight WHERE user_id = ? AND import_id = ?", (user["id"], import_id)
            ).fetchone()[0]
            imported = {"id": import_id, "count": count} if count else None

        return render_template(
            "weight-history.html",
            title="Weight",
            results=results[:(500 if request.args.get("rows") == "all" else 50)],
            show_all_url=url_for("weighthistory", range=wanted, rows="all") if len(results) > 50 and request.args.get("rows") != "all" else None,
            in_range=len(results),
            total=total,
            ranges=WEIGHT_RANGES,
            current_range=wanted,
            chart=weight_chart(list(reversed(results)), user["goalweight"]),
            imported=imported,
        )

    @app.route("/import-weights", methods=["GET", "POST"])
    @login_required
    def importweights():
        user = current_user()
        unit = request.form.get("unit", "kg") if request.form.get("unit") in importer.UNITS else "kg"
        order = request.form.get("order", "dmy") if request.form.get("order") in importer.DATE_ORDERS else "dmy"
        options = {"units": importer.UNITS, "orders": importer.DATE_ORDERS, "unit": unit, "order": order}

        if request.method == "GET":
            return render_template("import-weights.html", title="Import weights", **options)

        db = get_db()
        if request.form.get("step") == "save":
            try:
                rows = json.loads(request.form.get("rows", "[]"))
            except ValueError:
                rows = []
            existing_mode = request.form.get("existing", "skip")
            clean = []
            for r in rows if isinstance(rows, list) else []:
                try:
                    day = date.fromisoformat(r["date"])
                    kg = float(r["kg"])
                except (KeyError, TypeError, ValueError):
                    continue
                if day <= date.today() and importer.MIN_KG <= kg <= importer.MAX_KG:
                    clean.append((day.isoformat(), round(kg, 1)))
            if not clean:
                flash("There was nothing to import.", "error")
                return redirect(url_for("importweights"))

            have = {r["logdate"] for r in db.execute("SELECT DISTINCT logdate FROM weight WHERE user_id = ?", (user["id"],))}
            import_id = (db.execute("SELECT MAX(import_id) FROM weight WHERE user_id = ?", (user["id"],)).fetchone()[0] or 0) + 1
            added = replaced = skipped = 0
            for logdate, kg in clean:
                if logdate in have:
                    if existing_mode == "skip":
                        skipped += 1
                        continue
                    db.execute("DELETE FROM weight WHERE user_id = ? AND logdate = ?", (user["id"], logdate))
                    replaced += 1
                db.execute(
                    "INSERT INTO weight (user_id, logdate, weight, import_id) VALUES (?, ?, ?, ?)",
                    (user["id"], logdate, kg, import_id),
                )
                added += 1
            db.commit()
            parts = [f"Imported {added} weigh-in{'s' if added != 1 else ''}"]
            if replaced:
                parts.append(f"replacing {replaced} you already had")
            if skipped:
                parts.append(f"skipped {skipped} day{'s' if skipped != 1 else ''} you'd already tracked")
            flash(", ".join(parts) + ".", "success")
            return redirect(url_for("weighthistory", range="all", imported=import_id if added else None))

        # Preview
        text = request.form.get("text", "")
        upload = request.files.get("file")
        if upload and upload.filename:
            raw = upload.read()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
        if not text.strip():
            flash("Choose a file or paste some rows first.", "error")
            return render_template("import-weights.html", title="Import weights", **options)

        result = importer.read_weights(text, unit=unit, order=order)
        have = {r["logdate"]: r["weight"] for r in db.execute(
            "SELECT logdate, weight FROM weight WHERE user_id = ? ORDER BY id", (user["id"],))}
        preview = [dict(r, existing=have.get(r["date"].isoformat())) for r in result.rows]
        return render_template(
            "import-weights.html",
            title="Import weights",
            result=result,
            preview=preview,
            clashes=sum(1 for r in preview if r["existing"] is not None),
            rows_json=json.dumps([{"date": r["date"].isoformat(), "kg": r["kg"]} for r in result.rows]),
            text=text if not (upload and upload.filename) else "",
            **options,
        )

    @app.route("/undo-import/<int:import_id>", methods=["POST"])
    @login_required
    def undoimport(import_id):
        db = get_db()
        cur = db.execute("DELETE FROM weight WHERE user_id = ? AND import_id = ?", (current_user()["id"], import_id))
        db.commit()
        flash(f"Import undone: {cur.rowcount} weigh-in{'s' if cur.rowcount != 1 else ''} removed.", "success")
        return redirect(url_for("weighthistory"))

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_e):
        flash("That file is too big: the limit is 5 MB.", "error")
        return redirect(url_for("importweights"))

    @app.route("/food-history")
    @login_required
    def foodhistory():
        logdate = request.args.get("date") or today()
        try:
            day = date.fromisoformat(logdate)
        except ValueError:
            abort(400)

        user = current_user()
        results = calories_for(user["id"], logdate)
        per_meal = {meal: 0 for meal in MEALS}
        for row in results:
            if row["meal"] in per_meal:
                per_meal[row["meal"]] += row["calories"]

        return render_template(
            "food-history.html",
            title="Food",
            logdate=logdate,
            is_today=logdate == today(),
            prev_day=(day - timedelta(days=1)).isoformat(),
            next_day=(day + timedelta(days=1)).isoformat() if logdate < today() else None,
            results=results,
            totalcalories=sum(r["calories"] for r in results),
            totals=day_totals(results),
            nutrients=nutrients_for(user),
            per_meal=per_meal,
            target=target_for(user),
        )

    @app.route("/notice")
    def notice():
        today_uk = seasons.today_uk()
        coming = []
        for year in (today_uk.year, today_uk.year + 1):
            for occasion, day in seasons.occasion_days(year):
                if day >= today_uk and occasion not in [c[0] for c in coming]:
                    coming.append((occasion, day))
        return render_template(
            "notice.html",
            title="About and disclaimer",
            celebrations=seasons.CELEBRATIONS,
            all_year=[(t, seasons.THEME_LABELS[t]) for t in seasons.ALL_YEAR_THEMES],
            monthly=[(seasons.THEME_LABELS[t], m) for t, m in seasons.SEASONAL_THEMES.items()],
            coming=sorted(coming, key=lambda c: c[1]),
            labels=seasons.THEME_LABELS,
        )


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
