"""Search: the header's search button and box (press / or Ctrl+K, Cmd+K on a Mac), results as you type, and a
full results page. Matching tolerates small typos ("padington", "acadmy"). From SecureMy.School's search.

Off unless the app turns it on in settings.py:

    SEARCH = 'mysearch:results'      # module:function giving the app's results (below)
    SEARCH_PAGES = [                 # optional: the app's pages, found by name or keywords
        ('Reports', 'Every report', 'reports', '', 'charts totals', lambda user: user.has_role('member')),
    ]                                # (title, where it is, endpoint, #anchor, keywords, who can open it)

The function is given a Search (`search.score(text)` says how well some text matches, 0 to 1) and returns
{group name: [(score, item)]}, where an item is {'title', 'detail', 'url'} (or a function making one, so links are
only built for the results shown). It must only return what the signed-in user could open themselves: search
never shows more than the pages do. Kanto adds its own pages (profile, password, passkeys, display) and, for
admins, user accounts.
"""
import importlib
import re
from difflib import SequenceMatcher
from functools import lru_cache

import settings
from flask import jsonify, render_template, request, url_for
from flask_login import current_user, login_required

from . import app
from .models import User

LIMIT = 6  # results per group in the search box
PAGE_LIMIT = 50  # per group on the full results page


def search_words(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower())


@lru_cache(maxsize=4096)
def _trigrams(word):
    padded = f'  {word} '
    return frozenset(padded[i:i + 3] for i in range(len(padded) - 2))


@lru_cache(maxsize=65536)
def word_match(term, word):
    """How well one search term matches one word, 0 to 1. Short terms and numbers must start the word
    ("ul", "2024"); longer ones may have typos, judged by shared three-letter chunks (as PostgreSQL's pg_trgm
    does) or by letters in order."""
    if word.startswith(term):
        return 1.0
    if len(term) < 4 or term.isdigit():
        return 0.0
    if term in word:
        return 0.9
    a, b = _trigrams(term), _trigrams(word)
    chunks = len(a & b) / len(a | b)
    order = SequenceMatcher(None, term, word).ratio()
    return max(chunks, order) if chunks >= 0.4 or order >= 0.75 else 0.0


def match_score(terms, text):
    """How well TEXT matches every search term (0 when any term finds nothing)."""
    words = set(search_words(text))
    if not words or not terms:
        return 0.0
    total = 0.0
    for term in terms:
        best = max(word_match(term, w) for w in words)
        if not best:
            return 0.0
        total += best
    return total / len(terms)


class Search:
    def __init__(self, text, limit):
        self.text = text
        self.terms = search_words(text)[:8]
        self.limit = limit

    def score(self, text):
        return match_score(self.terms, text)


# Kanto's own pages: (title, where it is, endpoint, anchor, keywords, who can open it)
KANTO_PAGES = [
    ('Home', 'Your home page', 'home', '', 'start dashboard', lambda u: True),
    ('Your profile', 'Your account and sign-in', 'profile', '', 'account me settings', lambda u: True),
    ('Change your password', 'Profile › Security', 'profile', 'security', 'password security reset', lambda u: True),
    ('Two-step verification', 'Profile › Security', 'profile', 'security', 'mfa 2fa authenticator app code totp recovery codes', lambda u: True),
    ('Passkeys', 'Profile › Security', 'profile', 'security', 'passkey face id touch id fingerprint windows hello security key', lambda u: True),
    ('Display and accessibility', 'Profile › Display (or the Aa menu)', 'profile', 'display', 'theme dark light contrast font text size larger motion animation accessibility', lambda u: True),
    ('Badges', 'Profile › Badges', 'profile', 'badges', 'achievements badges', lambda u: True),
    ('Log', 'Everything done, by whom', 'activity', '', 'log activity audit trail history who did what', lambda u: u.can_view_log),
    ('Users', 'Manage user accounts', 'admin_users', '', 'users accounts admin roles unlock lockout reset password', lambda u: u.can_admin),
    ('View as a user', 'See the app as someone else, read-only', 'view_as_list', '', 'view as impersonate support', lambda u: 'global_admin' in u.roles),
]


def provider():
    spec = getattr(settings, 'SEARCH', None)
    if not spec:
        return None
    module, _, name = spec.partition(':')
    return getattr(importlib.import_module(module), name)


def run_search(text, limit=LIMIT):
    """{group: [{'title', 'detail', 'url'}]} for the signed-in user, best first."""
    search = Search(text, limit)
    if not search.terms:
        return {}
    user = current_user
    groups = {}
    pages = []
    for title, where, endpoint, anchor, keywords, allowed in KANTO_PAGES + list(getattr(settings, 'SEARCH_PAGES', [])):
        if endpoint in app.view_functions and allowed(user):
            pages.append((search.score(f'{title} {where} {keywords}'),
                          {'title': title, 'detail': where, 'url': url_for(endpoint, _anchor=anchor or None)}))
    groups['Pages'] = pages
    groups.update(provider()(search) or {})
    # User accounts: admins only, as the Users page (which also needs two-step verification on)
    if user.can_admin and user.has_two_step:
        groups['Users'] = [(search.score(f'{u.username} {u.full_name or ""} {u.email or ""} {" ".join(u.role_labels)} user account'),
                            lambda u=u: {'title': u.display_name + ('' if u.is_active else ' (disabled)'),
                                         'detail': ' · '.join(filter(None, [u.username, ', '.join(u.role_labels)])),
                                         'url': url_for('admin_user', user_id=u.id)})
                           for u in User.query.all()]
    found = {}
    for group, scored in groups.items():
        scored = sorted((x for x in scored if x[0] > 0), key=lambda x: -x[0])[:limit]
        if scored:
            found[group] = [item() if callable(item) else item for _, item in scored]
    return found


def search_page():
    q = request.args.get('q', '').strip()[:100]
    return render_template('kanto/search.html', q=q, results=run_search(q, PAGE_LIMIT) if q else {})


def search_json():
    q = request.args.get('q', '').strip()[:100]
    return jsonify({'q': q, 'groups': [{'name': group, 'items': items} for group, items in run_search(q).items()]})


SEARCH_ON = bool(getattr(settings, 'SEARCH', None))
if SEARCH_ON:
    app.add_url_rule('/search', 'search', login_required(search_page))
    app.add_url_rule('/search.json', 'search_json', login_required(search_json))
app.jinja_env.globals.update(kanto_search_on=SEARCH_ON)
