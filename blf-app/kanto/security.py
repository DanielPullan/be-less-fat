"""What runs around every request: the Content Security Policy and other security headers, long-lived caching of
static files, the session time limits, temporary passwords and required two-step verification, and viewing the
app as another user (global admins)."""
import os
import secrets
import time
from functools import wraps

import settings
from flask import abort, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user

from . import (MAX_UPLOAD_MB, REQUIRE_MFA, REQUIRE_PASSKEY, SECURE_COOKIES, SESSION_MAX_HOURS, STAGING, app, db,
               local_referrer)
from .models import AVATAR_COLOURS, AVATARS, DEFAULT_AVATAR_COLOUR, PROTECTED_ROLES, ROLE_DEFS, User

# Scripts only from this site, plus inline <script> blocks carrying this request's nonce. Inline style attributes
# are allowed (bars and charts size themselves with them); Google Fonts is only used for the optional fonts.
CSP = ("default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'")

# Pages a signed-in user can still reach while they must change a temporary password or set up two-step
# verification. Add your own public pages' endpoints here if they should stay reachable.
ALWAYS_ALLOWED = {'profile', 'profile_password', 'profile_display', 'profile_easter_egg', 'logout', 'static',
                  'kanto.static', 'login', 'login_mfa', 'index', 'about', 'favicon'}
ALWAYS_ALLOWED |= set(getattr(settings, 'EXTRA_ALLOWED_ENDPOINTS', ()))
MFA_ALLOWED = ALWAYS_ALLOWED | {'mfa_setup', 'passkey_options', 'passkey_add', 'passkey_remove'}
# Addresses that answer for themselves rather than redirecting to set up two-step verification (e.g. an API that
# takes its own tokens): settings.MFA_EXEMPT_PATHS = ('/api/',)
MFA_EXEMPT_PATHS = tuple(getattr(settings, 'MFA_EXEMPT_PATHS', ()))
# What protected roles are called in messages ("a protected role"); SecureMy.School's are safeguarding roles
PROTECTED_NAME = getattr(settings, 'PROTECTED_NAME', 'protected')


@app.before_request
def make_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)


# Static files get their file's version in the address, ?v=<last changed>, so browsers can keep them for a year and
# only fetch them again after a deploy changes them. Looked up once per worker (every time with FLASK_DEBUG on).
_static_versions = {}


@app.url_defaults
def static_file_version(endpoint, values):
    if endpoint in ('static', 'kanto.static') and 'filename' in values and 'v' not in values:
        folder = app.static_folder if endpoint == 'static' else os.path.join(os.path.dirname(__file__), 'static')
        key = (endpoint, values['filename'])
        version = None if app.debug else _static_versions.get(key)
        if version is None:
            try:
                version = _static_versions[key] = int(os.stat(os.path.join(folder, values['filename'])).st_mtime)
            except OSError:
                return
        values['v'] = version


@app.after_request
def cache_versioned_static(response):
    if request.endpoint in ('static', 'kanto.static') and request.args.get('v') and response.status_code in (200, 304):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@app.after_request
def security_headers(response):
    # setdefault: a page can set its own stricter policy (e.g. 'sandbox' for user uploads)
    response.headers.setdefault('Content-Security-Policy', CSP.format(nonce=g.get('csp_nonce', '')))
    response.headers.setdefault('X-Frame-Options', 'DENY')
    if STAGING:
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'  # keep the staging site out of search engines
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
    if SECURE_COOKIES:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000')
    return response


@app.errorhandler(413)
def too_large(e):
    flash(f'That upload is too big. Each save can include up to {MAX_UPLOAD_MB} MB.', 'error')
    return redirect(local_referrer() or url_for('home'))


# ---------------------------------------------------------------------------
# "Are you sure?" for actions that remove or reset something
# ---------------------------------------------------------------------------

def confirm_first(message, yes='Yes, go ahead', guard=None):
    """Ask before doing a POST action. With JavaScript, the form's data-confirm pop-up asks and adds confirmed=1
    (kanto/static/js/app.js). Without it (a script blocked or failed to load), the action isn't done: an
    "Are you sure?" page asks instead, then sends the same form again with confirmed=1.

    MESSAGE is the question, or a function taking the view's arguments (e.g. entry_id) that returns it.
    GUARD, also given the view's arguments, runs before asking: a response it returns (e.g. a refusal) is sent
    instead, so nobody is asked to confirm something they aren't allowed to do.
    Not for file uploads: a file can't be sent on again from the confirm page."""
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.method == 'POST' and guard is not None and (refused := guard(**kwargs)) is not None:
                return refused
            if request.method == 'POST' and request.form.get('confirmed') != '1':
                question = message(**kwargs) if callable(message) else message
                fields = [(k, v) for k, v in request.form.items(multi=True) if k not in ('csrf_token', 'confirmed')]
                back = local_referrer() or url_for('home')
                return render_template('kanto/confirm.html', question=question, yes=yes, action=request.full_path.rstrip('?'),
                                       fields=fields, back=back)
            return view(*args, **kwargs)
        return wrapped
    return decorate


# ---------------------------------------------------------------------------
# Passkey-confirmed sessions
# ---------------------------------------------------------------------------

def passkey_confirmed():
    """True when this session was signed in, or confirmed, with a passkey (or passkeys aren't required).
    While viewing as someone, this is the global admin's own session."""
    return not REQUIRE_PASSKEY or bool(session.get('passkey_ok'))


def needs_passkey_redirect(message, back):
    """Send the user to confirm with a passkey, then BACK."""
    flash(message, 'error')
    return redirect(url_for('confirm_passkey', next=back))


# How a session was signed in, strongest first. Only a passkey counts as confirmed (see passkey_confirmed).
SIGN_IN_METHODS = {'passkey': 'A passkey', 'code': 'Password and authenticator code',
                   'recovery': 'Password and recovery code', 'password': 'Password only'}


@app.template_global()
def passkey_ok():
    return passkey_confirmed()


@app.template_global()
def sign_in_methods():
    return SIGN_IN_METHODS


@app.template_global()
def avatar_choices():
    return AVATARS, AVATAR_COLOURS


@app.template_global()
def avatar_colour(user):
    return AVATAR_COLOURS.get(user.avatar_colour or DEFAULT_AVATAR_COLOUR, AVATAR_COLOURS[DEFAULT_AVATAR_COLOUR])[1]


@app.template_global()
def role_defs_all():
    return ROLE_DEFS


@app.template_global()
def passkey_locked_names():
    """What this session can't open until it's confirmed with a passkey, beyond global admin tools, in words
    (settings.passkey_locked_names(), e.g. ['Safeguarding audits'])."""
    names = getattr(settings, 'passkey_locked_names', None)
    return names() if names and not passkey_confirmed() else []


@app.template_global()
def protected_name():
    return PROTECTED_NAME


@app.template_global()
def protected_roles():
    return PROTECTED_ROLES


def roles_locked_for(user):
    """Roles USER can't give or take away: protected roles unless they hold one, and Global admin unless they are
    one. (Global admins can view as other users, so it's protected the same way.)"""
    locked = set() if user.has_protected_role else set(PROTECTED_ROLES)
    if 'global_admin' not in user.roles:
        locked.add('global_admin')
    return locked


@app.template_global()
def locked_roles():
    return roles_locked_for(current_user) if current_user.is_authenticated else set(ROLE_DEFS)


# ---------------------------------------------------------------------------
# Viewing as another user (global admins): see the app exactly as they do, read-only, to support them.
# The global admin stays signed in as themselves; for each request the app swaps in the viewed user, so every page
# is theirs. Nothing can be changed, and everything logged reads "global admin as viewed user".
# ---------------------------------------------------------------------------

# Display settings are allowed, but go to the viewing session, not the viewed user's account (see profile_display)
VIEW_AS_ALLOWED_POSTS = {'stop_viewing_as', 'logout', 'profile_display'}


def view_as_refusal(admin, target):
    """Why ADMIN can't view as TARGET, or None."""
    if 'global_admin' not in admin.roles:
        return 'Only global admins can view as other users.'
    if not admin.has_two_step:
        return 'Viewing as other users needs two-step verification on your own account.'
    if not passkey_confirmed():
        return 'Viewing as other users needs you to confirm it\'s you with a passkey.'
    if target is None or target == admin:
        return 'Choose someone else.'
    if not target.is_active:
        return f'{target.username}\'s account is disabled.'
    if 'global_admin' in target.roles:
        return 'Global admins can\'t view as each other.'
    if target.has_protected_role and not admin.has_protected_role:
        return f'{target.username} has a {PROTECTED_NAME} role, which you don\'t, so you can\'t view as them.'
    return None


@app.before_request
def apply_view_as():
    target_id = session.get('view_as')
    if not target_id or not current_user.is_authenticated:
        return None
    admin = current_user._get_current_object()
    target = db.session.get(User, target_id)
    if refusal := view_as_refusal(admin, target):
        session.pop('view_as', None)
        flash(f'Stopped viewing as another user. {refusal}', 'error')
        return redirect(url_for('home'))
    g.viewing_admin = admin
    g._login_user = target  # Flask-Login's per-request user: from here on, current_user is the viewed user
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.endpoint not in VIEW_AS_ALLOWED_POSTS:
        if request.is_json or request.accept_mimetypes.best == 'application/json':
            abort(403)
        flash(f'Nothing was changed: you\'re viewing as {target.username}, which is read-only.', 'error')
        return redirect(local_referrer() or url_for('home'))
    return None


# ---------------------------------------------------------------------------
# Session limits, temporary passwords and required two-step verification
# ---------------------------------------------------------------------------

@app.before_request
def enforce_session_age():
    # Absolute limit on a signed-in session, on top of the idle timeout
    if current_user.is_authenticated and time.time() - session.get('login_at', 0) > SESSION_MAX_HOURS * 3600:
        logout_user()
        session.clear()
        flash('Your session has ended. Please sign in again.', 'error')
        return redirect(url_for('login'))


@app.before_request
def enforce_password_change():
    # After an admin sets a temporary password, the user can only change it (or sign out)
    if (current_user.is_authenticated and current_user.must_change_password and not g.get('viewing_admin')
            and request.endpoint not in ALWAYS_ALLOWED):
        return redirect(url_for('profile') + '#security')


@app.before_request
def enforce_mfa():
    # With REQUIRE_MFA on, a signed-in user without two-step verification can only reach their profile to set it up
    if (REQUIRE_MFA and current_user.is_authenticated and not current_user.has_two_step and not g.get('viewing_admin')
            and request.endpoint not in MFA_ALLOWED and not request.path.startswith(MFA_EXEMPT_PATHS)):
        return redirect(url_for('profile') + '#security')
