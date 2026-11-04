"""The numbers: BMI, the daily calorie target (Mifflin-St Jeor), protein and fibre goals, high-protein and
high-fibre foods, and the weight chart. Plain functions, no database, so they're easy to test."""
from datetime import date, timedelta

MEALS = ('Breakfast', 'Lunch', 'Dinner', 'Snack')

# Activity multipliers for Mifflin-St Jeor (from archive/mifflin.py). 1 = potato, 5 = PT instructor.
ACTIVITY_LEVELS = {
    1: (1.2, 'Sedentary (little or no exercise)'),
    2: (1.375, 'Lightly active (exercise 1-3 days a week)'),
    3: (1.55, 'Moderately active (exercise 3-5 days a week)'),
    4: (1.725, 'Very active (hard exercise 6-7 days a week)'),
    5: (1.9, 'Extremely active (physical job or training twice a day)'),
}
SEXES = ('male', 'female')

DAILY_DEFICIT = 500                                # kcal/day, roughly 0.5 kg a week
MINIMUM_CALORIES = {'male': 1500, 'female': 1200}  # never recommend going below this
KCAL_PER_KG = 7700                                 # approx energy in 1 kg of body fat

# Protein, grams per kg of current weight, by activity level:
#   1 (sedentary): 0.75 g/kg, the UK Reference Nutrient Intake for adults
#   2-3 (lightly to moderately active): 1.0 g/kg, a step up chosen for Be Less Fat
#   4-5 (hard exercise most days): 1.2 g/kg, the bottom of the 1.2-2 g/kg UK sources give for resistance exercise
PROTEIN_PER_KG = {1: 0.75, 2: 1.0, 3: 1.0, 4: 1.2, 5: 1.2}
# Fibre: the NHS advises 30 g a day for every adult.
FIBRE_PER_DAY = 30
# "High protein": 10 g of protein or more per 100 kcal, a rule of thumb many people use
HIGH_PROTEIN_PER_100KCAL = 10
# "High fibre": 6 g of fibre or more per 100 g of the food (NHS), so it needs the portion's weight
HIGH_FIBRE_PER_100G = 6


def bmiCalc(weight, height):
    """BMI = kg / m^2. Returns None if we don't have the data."""
    if not weight or not height:
        return None
    return weight / (height ** 2)


def bmiCategory(bmi):
    if bmi is None:
        return 'Add your weight and height to see this'
    if bmi < 18.5:
        return 'Underweight'
    if bmi < 25:
        return 'Healthy weight'
    if bmi < 30:
        return 'Overweight'
    return 'Obese'


def ageFrom(birthdate, on=None):
    on = on or date.today()
    born = date.fromisoformat(birthdate)
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def mifflin(height, weight, age, sex):
    """Basal metabolic rate (kcal/day). Height in metres, weight in kg."""
    bmr = (10 * weight) + (6.25 * height * 100) - (5 * age)
    return bmr + 5 if sex == 'male' else bmr - 161


def calorieTarget(weight, height, goalweight, age, sex, activity, on=None):
    """A daily calorie target and an estimate of when the goal will be reached. None without enough info.

    Safeguards: never fewer than MINIMUM_CALORIES for the person's sex; at or below goal weight, it's maintenance.
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
        goal_date = (on or date.today()) + timedelta(days=round((to_lose * KCAL_PER_KG) / deficit))
    return {
        'bmr': round(bmr),
        'maintenance': round(maintenance),
        'target': round(target),
        'minimum': floor,
        'capped': capped,
        'to_lose': round(to_lose, 1),
        'goal_date': goal_date,
        'weekly_loss': round(deficit * 7 / KCAL_PER_KG, 2),
    }


def nutrientTargets(weight, activity):
    """Daily protein and fibre goals (grams), from UK guidance. Protein is None until there's a weight."""
    protein = None
    if weight:
        per_kg = PROTEIN_PER_KG.get(activity, PROTEIN_PER_KG[1])
        protein = {
            'target': int(round(weight * per_kg)),
            'per_kg': per_kg,
            'weight': weight,
            'activity': activity if activity in PROTEIN_PER_KG else None,
        }
    return {'protein': protein, 'fibre': {'target': FIBRE_PER_DAY}}


def protein_per_100kcal(protein, calories):
    """Grams of protein per 100 kcal, or None if we can't say."""
    if protein is None or not calories:
        return None
    return protein / calories * 100


def is_high_protein(protein, calories):
    ratio = protein_per_100kcal(protein, calories)
    return ratio is not None and ratio >= HIGH_PROTEIN_PER_100KCAL


def fibre_per_100g(fibre, portion):
    """Grams of fibre per 100 g of the food, or None if we can't say."""
    if fibre is None or not portion:
        return None
    return fibre / portion * 100


def is_high_fibre(fibre, portion):
    ratio = fibre_per_100g(fibre, portion)
    return ratio is not None and ratio >= HIGH_FIBRE_PER_100G


def day_totals(rows):
    """Calories, protein and fibre for a day's food. Protein/fibre count only the foods that have them."""
    return {
        'calories': sum(r.calories for r in rows),
        'protein': round(sum(r.protein or 0 for r in rows), 1),
        'fibre': round(sum(r.fibre or 0 for r in rows), 1),
        'missing_protein': sum(1 for r in rows if r.protein is None),
        'missing_fibre': sum(1 for r in rows if r.fibre is None),
    }


WEIGHT_RANGES = {'3m': ('3 months', 91), '1y': ('1 year', 365), 'all': ('All', None)}


def weight_chart(rows, goalweight=None, width=640, height=220):
    """Inline SVG line chart data for a run of weigh-ins (oldest first). None if fewer than 2.
    Points are spaced by date, so gaps between weigh-ins show as gaps in time."""
    if len(rows) < 2:
        return None
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 28
    days = [date.fromisoformat(r.logdate) for r in rows]
    span = max((days[-1] - days[0]).days, 1)
    values = [r.weight for r in rows] + ([goalweight] if goalweight else [])
    lo, hi = min(values), max(values)
    if hi - lo < 2:
        lo, hi = lo - 1, hi + 1
    lo, hi = lo - (hi - lo) * 0.1, hi + (hi - lo) * 0.1

    def x(d):
        return pad_l + (d - days[0]).days * (width - pad_l - pad_r) / span

    def y(v):
        return pad_t + (hi - v) * (height - pad_t - pad_b) / (hi - lo)

    points = [{'x': round(x(d), 1), 'y': round(y(r.weight), 1), 'weight': r.weight, 'date': r.logdate}
              for d, r in zip(days, rows)]
    ticks = [round(lo + (hi - lo) * k / 4, 1) for k in range(5)]
    return {
        'width': width, 'height': height, 'left': pad_l, 'right': width - pad_r, 'bottom': height - pad_b,
        'points': points,
        'dots': len(points) <= 60,
        'path': ' '.join(f"{'M' if i == 0 else 'L'}{p['x']},{p['y']}" for i, p in enumerate(points)),
        'area': f"M{points[0]['x']},{height - pad_b} " + ' '.join(f"L{p['x']},{p['y']}" for p in points)
                + f" L{points[-1]['x']},{height - pad_b} Z",
        'ticks': [{'value': t, 'y': round(y(t), 1)} for t in ticks],
        'goal_y': round(y(goalweight), 1) if goalweight else None,
        'first': rows[0].logdate,
        'last': rows[-1].logdate,
    }
