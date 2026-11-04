"""Be Less Fat's own tables. Accounts, roles and the rest are Kanto's (kanto/models.py).

After changing a model:  uv run flask --app app db migrate -m "What changed"  (SQLite upgrades itself at startup)
"""
from kanto import db
from nutrition import ageFrom


class BodyDetails(db.Model):
    """What the calorie, protein and BMI figures are worked out from: one row per account."""
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    height = db.Column(db.Float)          # metres
    goalweight = db.Column(db.Float)      # kg
    birthdate = db.Column(db.String(10))  # YYYY-MM-DD
    sex = db.Column(db.String(10))        # male / female (used for Mifflin-St Jeor)
    activity = db.Column(db.Integer)      # 1-5, see nutrition.ACTIVITY_LEVELS

    @property
    def complete(self):
        return all((self.height, self.goalweight, self.birthdate, self.sex, self.activity))

    @property
    def age(self):
        try:
            return ageFrom(self.birthdate) if self.birthdate else None
        except ValueError:
            return None


class WeighIn(db.Model):
    __tablename__ = 'weight'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    logdate = db.Column(db.String(10), nullable=False, index=True)  # YYYY-MM-DD
    weight = db.Column(db.Float, nullable=False)                     # kg
    import_id = db.Column(db.Integer)  # set on weigh-ins brought in from another app, so an import can be undone


class FoodEntry(db.Model):
    __tablename__ = 'food'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    logdate = db.Column(db.String(10), nullable=False, index=True)  # YYYY-MM-DD
    food = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    meal = db.Column(db.String(20))    # Breakfast / Lunch / Dinner / Snack / none
    protein = db.Column(db.Float)      # grams, optional
    fibre = db.Column(db.Float)        # grams, optional
    portion = db.Column(db.Float)      # the food's weight in grams, optional (for the high-fibre rule)
