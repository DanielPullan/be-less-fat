"""Which themes are offered, and what to celebrate, on a given day. Adapted from SecureMy.School.

- All year: Haunted, Memes, Nord, Silly, Network Console and Frosted Glass
- In their month: Pride (June), Black History Month (October, as in the UK), Festive (December)
- Around their day: Safer Internet Day, World Book Day, Pi Day, 4 May, Lunar New Year, Diwali, Eid
- static/js/seasonal.js reads season() to decide which celebration may play

BLF_SEASON_DATE=2026-12-31 makes all of this act as on that date, to try things out.
"""

import os
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    UK = ZoneInfo("Europe/London")
except Exception:  # no time zone database on this machine
    UK = None

ALL_YEAR_THEMES = ["haunted", "meme", "nord", "silly", "console", "vista"]

# Seasonal themes, for everyone, only in their month
SEASONAL_THEMES = {"pride": 6, "heritage": 10, "festive": 12}

# Occasions on particular days. Each has a theme, offered from some days before to some days after,
# and an animation that may play on the day itself: (theme, days before, days after, animation days).
OCCASIONS = {
    "safer": ("safer", 1, 5, 1),     # Safer Internet Day (second Tuesday in February): that week
    "books": ("books", 3, 3, 1),     # World Book Day in the UK (first Thursday in March)
    "pi": ("pi", 3, 3, 1),           # Pi Day (14 March)
    "space": ("space", 0, 0, 1),     # 4 May, for the sci-fi fans (a nod, with nothing from any film)
    "lunar": ("lunar", 2, 14, 1),    # Lunar New Year: the fortnight of celebrations that follows
    "diwali": ("diwali", 2, 2, 1),   # Diwali: the five days of the festival
    "eid": ("eid", 1, 3, 2),         # Eid al-Fitr and Eid al-Adha: can be a day later, depending on the moon
}
# Festivals whose dates move each year (the main day in the UK). Add later years before these run out.
FESTIVAL_DATES = {
    "lunar": ["2026-02-17", "2027-02-06", "2028-01-26", "2029-02-13", "2030-02-03"],
    "diwali": ["2026-11-08", "2027-10-29", "2028-10-17", "2029-11-05", "2030-10-26"],
    "eid": ["2026-03-20", "2026-05-27", "2027-03-10", "2027-05-16", "2028-02-26", "2028-05-04",
            "2029-02-14", "2029-04-23", "2030-02-05", "2030-04-13"],
}

THEME_LABELS = {
    "haunted": "Haunted 👻", "meme": "Memes 😎", "nord": "Nord", "silly": "Silly 🤡", "console": "Network Console 🛜",
    "vista": "Frosted Glass 🪟", "pride": "Pride 🌈", "heritage": "Black History Month", "festive": "Festive 🎄",
    "safer": "Safer Internet 🛡️", "books": "Book Day 📚", "pi": "Raspberry π", "space": "Galaxy 🌌",
    "lunar": "Lunar New Year 🏮", "diwali": "Diwali 🪔", "eid": "Eid 🌙",
}

# For the About page: each celebration, when it plays by itself, and its ?celebrate= name
CELEBRATIONS = [
    ("ghost", "Ghost 👻", "Sometimes, with the Haunted theme"),
    ("meme", "Air horns 📯", "Often, with the Memes theme"),
    ("apple", "Poison apple 🍎", "In June, with the Pride theme"),
    ("snow", "Snow ❄️", "In December, with the Festive theme"),
    ("fireworks", "Fireworks 🎆", "Bonfire Night and New Year's Eve"),
    ("balloons", "Balloons 🎈", "24 June"),
    ("safer", "Safer Internet 🛡️", "Safer Internet Day, or with its theme"),
    ("books", "Book Day 📚", "World Book Day, or with its theme"),
    ("pi", "Pi Day π", "14 March, or with its theme"),
    ("space", "Galaxy 🌌", "4 May, or with its theme"),
    ("lunar", "Lunar New Year 🏮", "Lunar New Year, or with its theme"),
    ("diwali", "Diwali 🪔", "Diwali, or with its theme"),
    ("eid", "Eid 🌙", "Eid, or with its theme"),
]


def today_uk():
    """Today in the UK, or BLF_SEASON_DATE if it's set."""
    pretend = os.environ.get("BLF_SEASON_DATE", "").strip()
    if pretend:
        try:
            return date.fromisoformat(pretend)
        except ValueError:
            pass
    return datetime.now(UK).date() if UK else date.today()


def nth_weekday(year, month, weekday, n):
    """The nth Monday (0), Tuesday (1)… of a month."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def occasion_days(year):
    """Each occasion's day(s) in a year: [(occasion, date)]."""
    days = [("safer", nth_weekday(year, 2, 1, 2)), ("books", nth_weekday(year, 3, 3, 1)), ("pi", date(year, 3, 14)),
            ("space", date(year, 5, 4))]
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


def extra_themes(today=None):
    """The themes beyond Light, Dark and High contrast offered today, in menu order."""
    today = today or today_uk()
    return (ALL_YEAR_THEMES + [t for t, m in SEASONAL_THEMES.items() if m == today.month]
            + occasions_now(today)[0])


def theme_options(today=None):
    return [(t, THEME_LABELS[t]) for t in extra_themes(today)]


def season(today=None):
    """What today calls for, read by static/js/seasonal.js: 'fireworks' (Bonfire Night, New Year's Eve),
    'balloons' (24 June), 'june', 'december', 'day-<occasion>' (see OCCASIONS), or ''.
    New Year's Eve is both: 'fireworks december'."""
    today = today or today_uk()
    parts = ["fireworks"] if (today.month, today.day) in ((11, 5), (12, 31)) else []
    if (today.month, today.day) == (6, 24):
        parts.append("balloons")
    parts += {6: ["june"], 12: ["december"]}.get(today.month, [])
    return " ".join(parts + ["day-" + occasion for occasion in occasions_now(today)[1]])
