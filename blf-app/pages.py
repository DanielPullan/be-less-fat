"""Be Less Fat's pages: Today, Food, Weight (with importing from other apps) and Goals.
Sign-in, profiles, users, the activity log, themes and the rest come from Kanto (kanto/)."""
import json
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import importer
from kanto import app, db, is_local_url, log_action
from kanto.security import confirm_first
from models import BodyDetails, FoodEntry, WeighIn
from nutrition import (ACTIVITY_LEVELS, HIGH_PROTEIN_PER_100KCAL, MEALS, SEXES, WEIGHT_RANGES, bmiCalc, bmiCategory,
                       calorieTarget, day_totals, fibre_per_100g, is_high_fibre, is_high_protein, nutrientTargets,
                       protein_per_100kcal, weight_chart)


def today():
    return date.today().isoformat()


def longdate(value):
    """3 November 2026"""
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return f'{d.day} {d.strftime("%B %Y")}'


def shortdate(value):
    """3 Nov"""
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return f'{d.day} {d.strftime("%b")}'


app.template_filter('longdate')(longdate)
app.template_filter('shortdate')(shortdate)
app.jinja_env.globals.update(protein_per_100kcal=protein_per_100kcal, fibre_per_100g=fibre_per_100g)


def body_for(user):
    """The user's body details (an empty, unsaved row if they haven't filled them in)."""
    return db.session.get(BodyDetails, user.id) or BodyDetails(user_id=user.id)


@app.context_processor
def inject_body():
    if current_user.is_authenticated:
        return {'body': body_for(current_user), 'meals': MEALS, 'today_iso': today}
    return {'meals': MEALS, 'today_iso': today}


def latest_weight(user):
    row = (WeighIn.query.filter_by(user_id=user.id)
           .order_by(WeighIn.logdate.desc(), WeighIn.id.desc()).first())
    return row.weight if row else None


def target_for(user, body, weight):
    return calorieTarget(weight, body.height, body.goalweight, body.age, body.sex, body.activity)


def foods_on(user, logdate):
    return FoodEntry.query.filter_by(user_id=user.id, logdate=logdate).order_by(FoodEntry.id).all()


def parse_positive_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_grams(value, limit=1000):
    """An optional amount in grams: None if blank, False if it isn't a sensible number."""
    if value is None or str(value).strip() == '':
        return None
    try:
        number = float(str(value).replace(',', '.'))
    except ValueError:
        return False
    return round(number, 1) if 0 <= number <= limit else False


def parse_non_negative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def safe_next():
    """The form's `next` page, if it's a page on this site (never an outside address)."""
    target = request.form.get('next', '')
    return target if is_local_url(target) else None


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('index.html')


@app.route('/today')
@login_required
def home():
    body = body_for(current_user)
    weight = latest_weight(current_user)
    raw_bmi = bmiCalc(weight, body.height)
    rows = foods_on(current_user, today())
    recent = (WeighIn.query.filter_by(user_id=current_user.id)
              .order_by(WeighIn.logdate.desc(), WeighIn.id.desc()).limit(2).all())
    change = round(recent[0].weight - recent[1].weight, 1) if len(recent) == 2 else None
    return render_template(
        'dashboard.html', today_date=date.today(), weight=weight, change=change,
        bmi=round(raw_bmi, 1) if raw_bmi else None, status=bmiCategory(raw_bmi),
        target=target_for(current_user, body, weight), eaten=sum(r.calories for r in rows),
        totals=day_totals(rows), nutrients=nutrientTargets(weight, body.activity), rows=rows,
        profile_complete=body.complete)


@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    body = body_for(current_user)
    if request.method == 'POST':
        height = parse_positive_float(request.form.get('height'))
        goalweight = parse_positive_float(request.form.get('goalweight'))
        birthdate = request.form.get('birthdate', '').strip() or None
        sex = request.form.get('sex') or None
        activity = parse_non_negative_int(request.form.get('activity'))
        # Be forgiving: people will type 180 meaning cm
        if height is not None and height > 3:
            height = height / 100
        error = None
        if height is None or goalweight is None:
            error = 'Height and goal weight need to be positive numbers.'
        elif sex is not None and sex not in SEXES:
            error = 'Pick a sex from the list.'
        elif activity is not None and activity not in ACTIVITY_LEVELS:
            error = 'Pick an activity level from the list.'
        elif birthdate is not None:
            from nutrition import ageFrom
            try:
                age = ageFrom(birthdate)
            except ValueError:
                error = 'Date of birth needs to be a valid date.'
            else:
                if age < 18:
                    error = 'Be Less Fat is not for under 18s.'
                elif age > 120:
                    error = "Date of birth doesn't look right."
        if error:
            flash(error, 'error')
        else:
            if bmiCalc(goalweight, height) < 18.5:
                flash('Heads up: that goal weight would put you in the underweight BMI range.', 'warning')
            body.height, body.goalweight, body.birthdate, body.sex, body.activity = height, goalweight, birthdate, sex, activity
            db.session.add(body)
            log_action('Goals saved')
            db.session.commit()
            flash('Goals saved.', 'success')
            return redirect(url_for('home'))
    return render_template('settings.html', sexes=SEXES, activity_levels=ACTIVITY_LEVELS)


@app.route('/settings')
def old_settings():
    return redirect(url_for('goals'), 301)


@app.route('/track-weight', methods=['GET', 'POST'])
@login_required
def trackweight():
    if request.method == 'GET':
        return redirect(url_for('weighthistory'))
    weight = parse_positive_float(request.form.get('weight'))
    try:
        day = date.fromisoformat(request.form.get('logdate') or today())
    except ValueError:
        day = None
    if weight is None:
        flash('Weight needs to be a positive number (kg).', 'error')
    elif day is None or day > date.today() or day.year < 1900:
        flash('The date needs to be today or earlier.', 'error')
    else:
        db.session.add(WeighIn(user_id=current_user.id, logdate=day.isoformat(), weight=weight))
        db.session.commit()
        when = '' if day == date.today() else f' for {longdate(day)}'
        flash(f'Weight of {weight:g} kg tracked{when}.', 'success')
    return redirect(safe_next() or url_for('weighthistory'))


@app.route('/track-food', methods=['GET', 'POST'])
@login_required
def trackfood():
    if request.method == 'GET':
        return redirect(url_for('foodhistory'))
    food = request.form.get('food', '').strip()
    calories = parse_non_negative_int(request.form.get('calories'))
    meal = request.form.get('meal', '').strip().capitalize()
    if meal == 'Snacks':
        meal = 'Snack'
    if meal not in MEALS:
        meal = None
    protein = parse_grams(request.form.get('protein'))
    fibre = parse_grams(request.form.get('fibre'))
    portion = parse_grams(request.form.get('portion'), limit=5000)
    if not food or calories is None:
        flash('Enter a food and a whole number of calories.', 'error')
    elif protein is False or fibre is False:
        flash('Protein and fibre need to be grams between 0 and 1000, or left blank.', 'error')
    elif portion is False or portion == 0:
        flash('Portion needs to be grams between 1 and 5000, or left blank.', 'error')
    elif portion is not None and any(v is not None and v > portion for v in (protein, fibre)):
        flash("Protein and fibre can't weigh more than the whole portion.", 'error')
    else:
        db.session.add(FoodEntry(user_id=current_user.id, logdate=today(), food=food[:200], calories=calories,
                                 meal=meal, protein=protein, fibre=fibre, portion=portion))
        db.session.commit()
        extras = ''.join(f', {v:g} g {k}' for k, v in (('protein', protein), ('fibre', fibre)) if v is not None)
        portion_text = f'{portion:g} g of ' if portion else ''
        high = ''
        if is_high_protein(protein, calories):
            high += ' High protein: {:.1f} g per 100 kcal.'.format(protein_per_100kcal(protein, calories))
        if is_high_fibre(fibre, portion):
            high += ' High fibre: {:.1f} g per 100 g.'.format(fibre_per_100g(fibre, portion))
        flash(f'{portion_text}{food} ({calories} kcal{extras}) tracked.{high}', 'success')
    return redirect(safe_next() or url_for('foodhistory'))


def _food_question(entry_id):
    entry = FoodEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    return f'Remove {entry.food} from {longdate(entry.logdate)}?' if entry else 'Remove this food?'


def _weigh_in_question(entry_id):
    entry = WeighIn.query.filter_by(id=entry_id, user_id=current_user.id).first()
    return f'Remove the weigh-in from {longdate(entry.logdate)} ({entry.weight:g} kg)?' if entry else 'Remove this weigh-in?'


def _import_question(import_id):
    count = WeighIn.query.filter_by(user_id=current_user.id, import_id=import_id).count()
    return f'Remove the {count} weigh-in{"s" if count != 1 else ""} from this import?'


@app.route('/delete-food/<int:entry_id>', methods=['POST'])
@login_required
@confirm_first(_food_question, 'Yes, remove it')
def deletefood(entry_id):
    entry = FoodEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    logdate = entry.logdate
    db.session.delete(entry)
    db.session.commit()
    flash('Food entry removed.', 'success')
    return redirect(safe_next() or url_for('foodhistory', date=logdate))


@app.route('/delete-last-weight', methods=['POST'])
@login_required
@confirm_first('Remove the weigh-in you added most recently?', 'Yes, remove it')
def deletelastweight():
    last = WeighIn.query.filter_by(user_id=current_user.id).order_by(WeighIn.id.desc()).first()
    if last:
        db.session.delete(last)
        db.session.commit()
    flash('Last weight entry removed.', 'success')
    return redirect(url_for('weighthistory'))


@app.route('/delete-weight/<int:entry_id>', methods=['POST'])
@login_required
@confirm_first(_weigh_in_question, 'Yes, remove it')
def deleteweight(entry_id):
    entry = WeighIn.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash('Weigh-in removed.', 'success')
    return redirect(safe_next() or url_for('weighthistory'))


@app.route('/weight-history')
@login_required
def weighthistory():
    mine = WeighIn.query.filter_by(user_id=current_user.id)
    wanted = request.args.get('range')
    if wanted not in WEIGHT_RANGES:
        # Default to 3 months, unless that would leave too little to draw (e.g. only old, imported data)
        recent = mine.filter(WeighIn.logdate >= (date.today() - timedelta(days=91)).isoformat()).count()
        wanted = '3m' if recent >= 2 else 'all'
    days = WEIGHT_RANGES[wanted][1]
    since = (date.today() - timedelta(days=days)).isoformat() if days else '0000-00-00'
    results = mine.filter(WeighIn.logdate >= since).order_by(WeighIn.logdate.desc(), WeighIn.id.desc()).all()
    imported = None
    if import_id := request.args.get('imported', type=int):
        count = mine.filter_by(import_id=import_id).count()
        imported = {'id': import_id, 'count': count} if count else None
    show_all = request.args.get('rows') == 'all'
    return render_template(
        'weight-history.html',
        results=results[:(500 if show_all else 50)],
        show_all_url=url_for('weighthistory', range=wanted, rows='all') if len(results) > 50 and not show_all else None,
        in_range=len(results), total=mine.count(), ranges=WEIGHT_RANGES, current_range=wanted,
        chart=weight_chart(list(reversed(results)), body_for(current_user).goalweight), imported=imported)


@app.route('/import-weights', methods=['GET', 'POST'])
@login_required
def importweights():
    unit = request.form.get('unit') if request.form.get('unit') in importer.UNITS else 'kg'
    order = request.form.get('order') if request.form.get('order') in importer.DATE_ORDERS else 'dmy'
    options = {'units': importer.UNITS, 'orders': importer.DATE_ORDERS, 'unit': unit, 'order': order}
    if request.method == 'GET':
        return render_template('import-weights.html', **options)

    mine = WeighIn.query.filter_by(user_id=current_user.id)
    if request.form.get('step') == 'save':
        try:
            rows = json.loads(request.form.get('rows', '[]'))
        except ValueError:
            rows = []
        existing_mode = request.form.get('existing', 'skip')
        clean = []
        for r in rows if isinstance(rows, list) else []:
            try:
                day, kg = date.fromisoformat(r['date']), float(r['kg'])
            except (KeyError, TypeError, ValueError):
                continue
            if day <= date.today() and importer.MIN_KG <= kg <= importer.MAX_KG:
                clean.append((day.isoformat(), round(kg, 1)))
        if not clean:
            flash('There was nothing to import.', 'error')
            return redirect(url_for('importweights'))
        have = {w.logdate for w in mine}
        import_id = (db.session.query(db.func.max(WeighIn.import_id)).filter(WeighIn.user_id == current_user.id).scalar() or 0) + 1
        added = replaced = skipped = 0
        for logdate, kg in clean:
            if logdate in have:
                if existing_mode == 'skip':
                    skipped += 1
                    continue
                mine.filter_by(logdate=logdate).delete()
                replaced += 1
            db.session.add(WeighIn(user_id=current_user.id, logdate=logdate, weight=kg, import_id=import_id))
            added += 1
        log_action('Weights imported', detail=f'{added} added, {replaced} replaced, {skipped} skipped')
        db.session.commit()
        parts = [f"Imported {added} weigh-in{'s' if added != 1 else ''}"]
        if replaced:
            parts.append(f'replacing {replaced} you already had')
        if skipped:
            parts.append(f"skipped {skipped} day{'s' if skipped != 1 else ''} you'd already tracked")
        flash(', '.join(parts) + '.', 'success')
        return redirect(url_for('weighthistory', range='all', imported=import_id if added else None))

    # Preview
    text = request.form.get('text', '')
    upload = request.files.get('file')
    if upload and upload.filename:
        raw = upload.read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
    if not text.strip():
        flash('Choose a file or paste some rows first.', 'error')
        return render_template('import-weights.html', **options)
    result = importer.read_weights(text, unit=unit, order=order)
    have = {w.logdate: w.weight for w in mine.order_by(WeighIn.id)}
    preview = [dict(r, existing=have.get(r['date'].isoformat())) for r in result.rows]
    return render_template(
        'import-weights.html', result=result, preview=preview,
        clashes=sum(1 for r in preview if r['existing'] is not None),
        rows_json=json.dumps([{'date': r['date'].isoformat(), 'kg': r['kg']} for r in result.rows]),
        text=text if not (upload and upload.filename) else '', **options)


@app.route('/undo-import/<int:import_id>', methods=['POST'])
@login_required
@confirm_first(_import_question, 'Yes, undo the import')
def undoimport(import_id):
    removed = WeighIn.query.filter_by(user_id=current_user.id, import_id=import_id).delete()
    log_action('Weight import undone', detail=f'{removed} weigh-in{"s" if removed != 1 else ""} removed')
    db.session.commit()
    flash(f"Import undone: {removed} weigh-in{'s' if removed != 1 else ''} removed.", 'success')
    return redirect(url_for('weighthistory'))


@app.route('/food-history')
@login_required
def foodhistory():
    logdate = request.args.get('date') or today()
    try:
        day = date.fromisoformat(logdate)
    except ValueError:
        abort(400)
    body = body_for(current_user)
    weight = latest_weight(current_user)
    results = foods_on(current_user, logdate)
    per_meal = {meal: 0 for meal in MEALS}
    meal_protein = {meal: None for meal in MEALS}
    for row in results:
        if row.meal in per_meal:
            per_meal[row.meal] += row.calories
            if row.protein is not None:
                meal_protein[row.meal] = (meal_protein[row.meal] or 0) + row.protein
    # A meal counts as high protein (or fibre) only if every food in it has the amounts needed
    in_meal = {meal: [r for r in results if r.meal == meal] for meal in MEALS}
    high_meals = {meal for meal, rows in in_meal.items()
                  if rows and all(r.protein is not None for r in rows)
                  and is_high_protein(meal_protein[meal], per_meal[meal])}
    high_fibre_meals = {meal for meal, rows in in_meal.items()
                        if rows and all(r.fibre is not None and r.portion for r in rows)
                        and is_high_fibre(sum(r.fibre for r in rows), sum(r.portion for r in rows))}
    return render_template(
        'food-history.html', logdate=logdate, is_today=logdate == today(),
        prev_day=(day - timedelta(days=1)).isoformat(),
        next_day=(day + timedelta(days=1)).isoformat() if logdate < today() else None,
        results=results, totalcalories=sum(r.calories for r in results), totals=day_totals(results),
        nutrients=nutrientTargets(weight, body.activity), per_meal=per_meal, meal_protein=meal_protein,
        high_meals=high_meals,
        high_foods={r.id for r in results if is_high_protein(r.protein, r.calories)},
        high_fibre_foods={r.id for r in results if is_high_fibre(r.fibre, r.portion)},
        high_fibre_meals=high_fibre_meals,
        meal_fibre={meal: (sum(r.fibre for r in rows), sum(r.portion for r in rows))
                    for meal, rows in in_meal.items() if meal in high_fibre_meals},
        high_bar=HIGH_PROTEIN_PER_100KCAL, target=target_for(current_user, body, weight))


@app.route('/notice')
def notice():
    return redirect(url_for('about'), 301)
