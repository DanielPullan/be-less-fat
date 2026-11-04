"""Display settings, themes and celebrations.

Themes (kanto/static/css/themes.css, chosen in the Aa menu):
- Always: Match my device, Light, Dark, High contrast
- All year, for everyone: Haunted, Memes, Nord, Silly, Network Console, Fruity Frog, Pomegranate Piranha
- Unlocked by an easter egg: Frosted Glass (type the new emergency number, 0118 999 881 999 119 725 3)
- In their month: Pride (June), Black History Month (October, as in the UK), Festive (December)
- Around their day: Safer Internet Day, World Book Day, Pi Day, 4 May, Lunar New Year, Diwali, Eid

Celebrations (kanto/static/js/seasonal.js) play by chance on a page load, with the odds in CELEBRATIONS; admins can
change them for everyone on the Users page. ?celebrate=<name> plays one straight away (on staging, and for admins).
"""
import json
import os
from datetime import date, datetime, timedelta

from flask import has_request_context, session
from flask_login import current_user

import settings
from . import STAGING, SEASON_DATE, UK, app

STANDARD_THEMES = ['system', 'light', 'dark', 'contrast']
ALL_YEAR_THEMES = ['haunted', 'meme', 'nord', 'silly', 'console', 'frog', 'piranha']
# Themes unlocked by finding an easter egg (kanto/static/js/konami.js)
EGG_THEMES = {'vista': 'emergency'}
EASTER_EGGS = {'konami', 'emergency'}
# Seasonal themes, for everyone, only in their month
SEASONAL_THEMES = {'pride': 6, 'heritage': 10, 'festive': 12}

# Occasions on particular days. Each has a theme, offered to everyone from some days before to some days after,
# and an animation that may play for everyone on the day itself: (theme, days before, days after, animation days).
OCCASIONS = {
    'safer': ('safer', 1, 5, 1),     # Safer Internet Day (second Tuesday in February): that week
    'books': ('books', 3, 3, 1),     # World Book Day in the UK (first Thursday in March)
    'pi': ('pi', 3, 3, 1),           # Pi Day (14 March)
    'space': ('space', 0, 0, 1),     # 4 May, for the sci-fi fans (a nod, with nothing from any film)
    'lunar': ('lunar', 2, 14, 1),    # Lunar New Year: the fortnight of celebrations that follows
    'diwali': ('diwali', 2, 2, 1),   # Diwali: the five days of the festival
    'eid': ('eid', 1, 3, 2),         # Eid al-Fitr and Eid al-Adha: can be a day later, depending on the moon
}
# Festivals whose dates move each year (the main day in the UK). Add later years before these run out.
FESTIVAL_DATES = {
    'lunar': ['2026-02-17', '2027-02-06', '2028-01-26', '2029-02-13', '2030-02-03'],
    'diwali': ['2026-11-08', '2027-10-29', '2028-10-17', '2029-11-05', '2030-10-26'],
    'eid': ['2026-03-20', '2026-05-27', '2027-03-10', '2027-05-16', '2028-02-26', '2028-05-04',
            '2029-02-14', '2029-04-23', '2030-02-05', '2030-04-13'],
}
THEME_LABELS = {'haunted': 'Haunted 👻', 'meme': 'Memes 😎', 'nord': 'Nord', 'silly': 'Silly 🤡',
                'console': 'Network Console 🛜', 'frog': 'Fruity Frog 🐸', 'piranha': 'Pomegranate Piranha 🐟', 'vista': 'Frosted Glass 🪟', 'pride': 'Pride 🌈',
                'heritage': 'Black History Month', 'festive': 'Festive 🎄', 'safer': 'Safer Internet 🛡️',
                'books': 'Book Day 📚', 'pi': 'Raspberry π', 'space': 'Galaxy 🌌', 'lunar': 'Lunar New Year 🏮',
                'diwali': 'Diwali 🪔', 'eid': 'Eid 🌙'}

DISPLAY_CHOICES = {'theme': set(STANDARD_THEMES) | set(THEME_LABELS), 'text': {'default', 'large', 'larger'},
                   'font': {'standard', 'readable', 'fira'}, 'motion': {'system', 'reduce'},
                   'celebrations': {'on', 'off'}}
DISPLAY_DEFAULTS = {'theme': 'system', 'text': 'default', 'font': 'standard', 'motion': 'system', 'celebrations': 'on'}

# Celebrations that may play by themselves on a page load, with their usual 1 in N odds. 0 turns one off.
CELEBRATIONS = {
    'ghost': ('Ghost', 'with the Haunted theme', 25),
    'meme': ('Air horns', 'with the Memes theme', 8),
    'apple': ('Poison apple', 'in June, with the Pride theme', 25),
    'snow': ('Snow', 'in December, with the Festive theme', 12),
    'fireworks': ('Fireworks', 'Bonfire Night and New Year\'s Eve, for everyone', 20),
    'balloons': ('Balloons', '24 June, for everyone', 23),
    'occasion_day': ('Occasion, on the day', 'Safer Internet Day, Diwali and the rest, for everyone', 20),
    'occasion_theme': ('Occasion, with its theme', 'while that occasion\'s theme is chosen', 25),
}
# Each can be played on demand (?celebrate=, buttons on the Users page and the About page)
CELEBRATION_BUTTONS = [('ghost', 'Ghost 👻'), ('meme', 'Air horns 📯'), ('apple', 'Poison apple 🍎'), ('snow', 'Snow ❄️'),
                       ('fireworks', 'Fireworks 🎆'), ('balloons', 'Balloons 🎈'), ('safer', 'Safer Internet 🛡️'),
                       ('books', 'Book Day 📚'), ('pi', 'Pi Day π'), ('space', 'Galaxy 🌌'), ('lunar', 'Lunar New Year 🏮'),
                       ('diwali', 'Diwali 🪔'), ('eid', 'Eid 🌙')]
CELEBRATION_ODDS_FILE = os.path.join(app.instance_path, 'celebration-odds.json')
SEASON_DATE_FILE = os.path.join(app.instance_path, 'season-date.txt')
_odds_cache = [None, {}]  # (file modified time, odds): read again only when the file changes


@app.template_global()
def celebration_odds():
    """Each celebration's 1 in N odds: the usual ones, with any an admin changed."""
    odds = {name: usual for name, (_, _, usual) in CELEBRATIONS.items()}
    try:
        modified = os.path.getmtime(CELEBRATION_ODDS_FILE)
    except OSError:
        return odds
    if _odds_cache[0] != modified:
        try:
            with open(CELEBRATION_ODDS_FILE) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        _odds_cache[:] = [modified, {k: int(v) for k, v in saved.items() if k in CELEBRATIONS and str(v).isdigit()}]
    odds.update(_odds_cache[1])
    return odds


def real_today():
    return datetime.now(UK).date()


def staging_season_date():
    """The pretend date an admin set: on staging, for everyone (SEASON_DATE_FILE); otherwise just for that admin
    (their session). None when not set."""
    if not STAGING:
        if not has_request_context() or not current_user.is_authenticated or not current_user.can_admin:
            return None
        try:
            return date.fromisoformat(session.get('season_date') or '')
        except ValueError:
            return None
    try:
        with open(SEASON_DATE_FILE) as f:
            return date.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return None


def season_date():
    """Today in the UK (or the pretend date an admin set, or on staging SEASON_DATE), for the seasonal touches."""
    if set_by_admin := staging_season_date():
        return set_by_admin
    if SEASON_DATE:
        try:
            return date.fromisoformat(SEASON_DATE)
        except ValueError:
            pass
    return real_today()


@app.template_global()
def pretend_date():
    """The date the seasonal touches are acting as, if it isn't today."""
    day = season_date()
    return day if day != real_today() else None


def nth_weekday(year, month, weekday, n):
    """The nth Monday (0), Tuesday (1)… of a month."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def occasion_days(year):
    """Each occasion's day(s) in a year: [(occasion, date)]."""
    days = [('safer', nth_weekday(year, 2, 1, 2)), ('books', nth_weekday(year, 3, 3, 1)), ('pi', date(year, 3, 14)),
            ('space', date(year, 5, 4))]
    for occasion, dates in FESTIVAL_DATES.items():
        days += [(occasion, date.fromisoformat(d)) for d in dates if d.startswith(str(year))]
    return days


def occasions_now(today):
    """(themes offered today, occasions whose animation day it is)."""
    themes, days = [], []
    for year in (today.year - 1, today.year, today.year + 1):  # windows can cross New Year
        for occasion, day in occasion_days(year):
            theme, before, after, animate = OCCASIONS[occasion]
            if day - timedelta(days=before) <= today <= day + timedelta(days=after) and theme not in themes:
                themes.append(theme)
            if day <= today < day + timedelta(days=animate) and occasion not in days:
                days.append(occasion)
    return themes, days


def themes_on(day):
    """The seasonal and occasion themes offered on a day."""
    return [t for t, m in SEASONAL_THEMES.items() if m == day.month] + occasions_now(day)[0]


@app.template_global()
def season():
    """What today calls for, read by seasonal.js: 'fireworks' (Bonfire Night, New Year's Eve), 'balloons' (24 June),
    'june', 'december', 'day-<occasion>' (see OCCASIONS), or ''. New Year's Eve is both: 'fireworks december'."""
    today = season_date()
    parts = ['fireworks'] if (today.month, today.day) in ((11, 5), (12, 31)) else []
    if (today.month, today.day) == (6, 24):
        parts.append('balloons')
    parts += {6: ['june'], 12: ['december']}.get(today.month, [])
    return ' '.join(parts + ['day-' + occasion for occasion in occasions_now(today)[1]])


@app.template_global()
def extra_themes():
    """The themes beyond the standard four that the current user can choose now."""
    signed_in = has_request_context() and current_user.is_authenticated
    eggs = current_user.found_easter_eggs if signed_in else []
    themes = (ALL_YEAR_THEMES + [theme for theme, egg in EGG_THEMES.items() if egg in eggs]
              + themes_on(season_date()))
    # Admins can try any limited theme from the Users page (try_theme); keep whichever they're trying
    if signed_in and current_user.can_admin:
        tried = json.loads(current_user.display_prefs or '{}').get('theme')
        if tried in THEME_LABELS and tried not in themes:
            themes.append(tried)
    return themes


@app.template_global()
def theme_options():
    """The Aa menu's theme choices right now: [(theme, label)]."""
    return [('system', 'Match my device'), ('light', 'Light'), ('dark', 'Dark'), ('contrast', 'High contrast')] + \
        [(t, THEME_LABELS[t]) for t in extra_themes()]


@app.template_global()
def display_prefs_json():
    """The signed-in user's saved display settings (JSON). While a global admin is viewing as someone, their own
    choices for that viewing session come first, so the viewed user's settings never change."""
    from flask import g
    if g.get('viewing_admin') is not None and 'view_as_display' in session:
        return session['view_as_display']
    return current_user.display_prefs if current_user.is_authenticated else None


@app.template_global()
def celebration_messages():
    return {'bonfire': settings.CELEBRATION_MESSAGES.get('bonfire', ''), 'nye': settings.CELEBRATION_MESSAGES.get('nye', ''),
            'konami': settings.KONAMI_MESSAGES}


def limited_themes():
    """Every theme that's only offered to some people or at some times, for the Users page: [(theme, label, who)]"""
    months = {m: date(2000, m, 1).strftime('%B') for m in range(1, 13)}
    who = {theme: 'everyone' for theme in ALL_YEAR_THEMES}
    who.update({theme: 'unlocked by an easter egg' for theme in EGG_THEMES})
    who.update({theme: f'everyone in {months[m]}' for theme, m in SEASONAL_THEMES.items()})
    who.update({theme: 'around its day' for theme, *_ in OCCASIONS.values()})
    return [(theme, label, who.get(theme, '')) for theme, label in THEME_LABELS.items()]


def season_date_shortcuts():
    """Handy dates to try: the next of each occasion, festival and seasonal touch. [(label, date, what it shows)]"""
    today = real_today()
    names = {'safer': 'Safer Internet Day', 'books': 'World Book Day', 'pi': 'Pi Day', 'space': '4 May',
             'lunar': 'Lunar New Year', 'diwali': 'Diwali', 'eid': 'Eid'}
    shortcuts = {}
    for year in (today.year, today.year + 1):
        for occasion, day in occasion_days(year):
            if day >= today and names[occasion] not in shortcuts:
                shortcuts[names[occasion]] = day
        for label, month, day_of_month in [('Bonfire Night', 11, 5), ('Festive (December)', 12, 10), ("New Year's Eve", 12, 31),
                                           ('Pride (June)', 6, 10), ('24 June', 6, 24), ('Black History Month (October)', 10, 15)]:
            day = date(year, month, day_of_month)
            if day >= today and label not in shortcuts:
                shortcuts[label] = day
    shown = lambda day: ' + '.join([THEME_LABELS[t] for t in themes_on(day)]
                                   + ['fireworks'] * ((day.month, day.day) in ((11, 5), (12, 31)))
                                   + ['balloons'] * ((day.month, day.day) == (6, 24)))
    return [(label, day, shown(day)) for label, day in sorted(shortcuts.items(), key=lambda item: item[1])]


def coming_occasions():
    """The next date of each occasion, soonest first, for the About page."""
    today = season_date()
    coming = {}
    for year in (today.year, today.year + 1):
        for occasion, day in occasion_days(year):
            if day >= today and occasion not in coming:
                coming[occasion] = day
    return sorted(coming.items(), key=lambda item: item[1])


def save_theme(user, theme):
    """Switch USER's saved theme, keeping their other display settings. Caller commits."""
    prefs = dict(DISPLAY_DEFAULTS)
    prefs.update(json.loads(user.display_prefs or '{}'))
    prefs['theme'] = theme
    user.display_prefs = json.dumps(prefs)


# ---------------------------------------------------------------------------
# Kanto's own pages: About (your text, then the themes and celebrations) and /favicon.ico
# ---------------------------------------------------------------------------
from flask import render_template, send_from_directory  # noqa: E402


@app.route('/about')
def about():
    return render_template('kanto/about.html', celebrations=CELEBRATION_BUTTONS, coming=coming_occasions(),
                           all_year=[(t, THEME_LABELS[t]) for t in ALL_YEAR_THEMES],
                           monthly=[(THEME_LABELS[t], date(2000, m, 1).strftime('%B')) for t, m in SEASONAL_THEMES.items()],
                           occasion_labels={o: THEME_LABELS[t] for o, (t, *_) in OCCASIONS.items()})


@app.route('/favicon.ico')
def favicon():
    """For browsers that ask for /favicon.ico directly: staging's own amber icon on staging."""
    return send_from_directory(os.path.join(app.root_path, 'static', 'img'),
                               'favicon-staging.svg' if STAGING else 'favicon.svg', mimetype='image/svg+xml', max_age=86400)
