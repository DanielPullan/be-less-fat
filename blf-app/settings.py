"""Be Less Fat's settings for Kanto (kanto/): name, roles, header links, badges and the profile's figures."""
from collections import namedtuple

APP_NAME = 'Be Less Fat'
WORDMARK = ('BeLess', 'Fat')
TAGLINE = ('Be Less Fat tracks your food and weight, works out a daily calorie target from your details, '
           'and estimates when you\'ll reach your goal.')
FOOTER_NOTE = 'Be Less Fat is a test project. It isn\'t medical advice: please only use dummy data.'

# Anyone can create an account; new accounts go to Goals to fill in their details
ALLOW_SIGN_UP = True
SIGN_UP_LANDING = 'goals'

RoleDef = namedtuple('RoleDef', 'label kind summary')
ROLE_DEFS = {
    'member': RoleDef('Member', 'user', 'Tracks their own food and weight'),
    'admin': RoleDef('Admin', 'admin', 'Manages user accounts'),
    'global_admin': RoleDef('Global admin', 'admin',
                            'Can view the app as any other user, read-only, to support them. Logged as "you as them".'),
}
ROLE_KINDS = [('user', 'Using the app', ''), ('admin', 'User management', '')]
DEFAULT_ROLES = {'member'}
PROTECTED_ROLES = set()

BADGE_GROUPS = ['Getting started', 'Tracking', 'Just for fun']


def app_badges(user, logs, counts):
    # Counted from Be Less Fat's own tables, so tracking food and weight doesn't fill the activity log
    from models import BodyDetails, FoodEntry, WeighIn
    from nutrition import is_high_fibre, is_high_protein
    weigh_ins = WeighIn.query.filter_by(user_id=user.id)
    foods = FoodEntry.query.filter_by(user_id=user.id).all()
    from kanto import db
    body = db.session.get(BodyDetails, user.id)
    return [
        ('🎯', 'Goal setter', 'Filled in your height, goal and details', bool(body and body.complete), False, 'Getting started'),
        ('⚖️', 'First weigh-in', 'Tracked your weight', weigh_ins.count() >= 1, False, 'Tracking'),
        ('📈', 'Trend spotter', 'Tracked your weight ten times', weigh_ins.count() >= 10, False, 'Tracking'),
        ('🍽', 'First bite', 'Tracked some food', len(foods) >= 1, False, 'Tracking'),
        ('📒', 'Food diary', 'Tracked a hundred foods', len(foods) >= 100, False, 'Tracking'),
        ('📥', 'Moving in', 'Imported weigh-ins from another app', weigh_ins.filter(WeighIn.import_id.isnot(None)).count() >= 1, False, 'Tracking'),
        ('💪', 'Protein pick', 'Tracked a high-protein food', any(is_high_protein(f.protein, f.calories) for f in foods), False, 'Tracking'),
        ('🌾', 'Fibre fan', 'Tracked a high-fibre food', any(is_high_fibre(f.fibre, f.portion) for f in foods), False, 'Tracking'),
    ]


def profile_stats(user, logs, counts):
    from models import FoodEntry, WeighIn
    return [('Weigh-ins', WeighIn.query.filter_by(user_id=user.id).count()),
            ('Foods tracked', FoodEntry.query.filter_by(user_id=user.id).count()),
            ('Sign-ins', counts.get('Logged in', 0))]


def nav_links(user, url_for):
    return ([(url_for('home'), 'Today'), (url_for('foodhistory'), 'Food'), (url_for('weighthistory'), 'Weight'),
             (url_for('goals'), 'Goals')],
            [(url_for('importweights'), 'Import weights'), (url_for('about'), 'About and disclaimer')])


CELEBRATION_MESSAGES = {
    'bonfire': 'Remember, remember: log your toffee apples in November.',
    'nye': 'New year, same you, a little lighter? Here\'s to it.',
}
KONAMI_MESSAGES = [
    '30 extra lives granted. Calories unchanged.',
    'Cheat code accepted. Sadly it doesn\'t work on the scales.',
    'Achievement unlocked: knows the classics.',
    'Up, up, down, down… that\'s a lot of stairs. Well done.',
]
