"""Kanto, the shared framework: sign-in, two-step verification, passkeys, users and roles, the activity log, display
settings, themes and celebrations, and security headers. Taken from SecureMy.School.

Importing kanto sets up `app` and `db`. Your app's own models and pages (models.py, pages.py) import them from here.
Settings come from environment variables, or a .env file next to app.py (real environment variables win):

  SECRET_KEY        required. Generate one: python -c "import secrets; print(secrets.token_hex(32))"
  DATABASE_URL      e.g. postgresql://user:password@localhost/myapp. Unset: SQLite in instance/app.db
  STAGING=1         a banner on every page, search engines kept out, ?celebrate= for everyone, pretend dates for all
  SEASON_DATE       (staging only) make the seasonal themes and celebrations act as on that date, e.g. 2026-12-31
  REQUIRE_MFA=1     everyone must set up two-step verification (an authenticator app or a passkey)
  REQUIRE_PASSKEY=0 global admin tools and protected roles stop needing a passkey-confirmed session (on by default)
  SECURE_COOKIES=1  once served over HTTPS: cookies only over HTTPS, and HSTS
  PASSKEY_RP_ID     the domain passkeys belong to (e.g. example.com). Unset: the address being visited
  PASSKEY_ORIGIN    the full address (e.g. https://example.com). Unset: the address being visited
  BEHIND_PROXY=1    behind Apache or another reverse proxy: trust its X-Forwarded-For and X-Forwarded-Proto
  MAX_UPLOAD_MB     the largest request accepted (default 20)
"""
import base64
import csv
import hashlib
import hmac
import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from dotenv import load_dotenv
from flask import Blueprint, Flask, g, has_request_context, request
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from jinja2 import ChoiceLoader, FileSystemLoader
from sqlalchemy import event
from sqlalchemy.orm import Session
from werkzeug.middleware.proxy_fix import ProxyFix

import settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANTO = os.path.dirname(os.path.abspath(__file__))
UK = ZoneInfo('Europe/London')

load_dotenv(os.path.join(ROOT, '.env'))


def env_flag(name, default=''):
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes')


app = Flask('app', root_path=ROOT, instance_path=os.path.join(ROOT, 'instance'))
# Your templates (templates/) come first, so you can override any of Kanto's (kanto/templates/)
app.jinja_loader = ChoiceLoader([FileSystemLoader(os.path.join(ROOT, 'templates')),
                                 FileSystemLoader(os.path.join(KANTO, 'templates'))])
# Kanto's own scripts, icons and avatars, at /static/kanto/...; your styles and images stay in static/
app.register_blueprint(Blueprint('kanto', __name__, static_folder='static', static_url_path='/static/kanto'))

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise RuntimeError('SECRET_KEY is not set. Add it to .env (or the environment). '
                       'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"')
os.makedirs(app.instance_path, exist_ok=True)
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip() or getattr(settings, 'DEFAULT_DATABASE', 'sqlite:///app.db')
DATABASE_URL = re.sub(r'^postgres(?:ql)?://', 'postgresql+psycopg://', DATABASE_URL)  # the psycopg 3 driver
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
USING_SQLITE = DATABASE_URL.startswith('sqlite')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {} if USING_SQLITE else {'pool_pre_ping': True}

STAGING = env_flag('STAGING')
SEASON_DATE = os.environ.get('SEASON_DATE', '').strip() if STAGING else ''
REQUIRE_MFA = env_flag('REQUIRE_MFA')
# Global admin tools, and giving or removing protected roles, need this session to be confirmed with a passkey
# (by signing in with one, or confirming later): a password and code can be phished, a passkey can't.
REQUIRE_PASSKEY = env_flag('REQUIRE_PASSKEY', '1')
SECURE_COOKIES = env_flag('SECURE_COOKIES')
# Passkeys are tied to the site's domain name. Browsers only offer them over HTTPS or on localhost, and passkeys
# made for one domain don't work on another, so changing the domain means everyone adds theirs again.
PASSKEY_RP_ID = os.environ.get('PASSKEY_RP_ID', '').strip()
PASSKEY_ORIGIN = os.environ.get('PASSKEY_ORIGIN', '').strip().rstrip('/')
MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', str(getattr(settings, 'MAX_UPLOAD_MB', 20))))

# CSRF tokens last as long as the login session rather than an hour, so a long form doesn't fail to save
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = SECURE_COOKIES
# Signed-in sessions end after SESSION_IDLE_HOURS without activity, and SESSION_MAX_HOURS after signing in
SESSION_IDLE_HOURS = 4
SESSION_MAX_HOURS = 12
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_IDLE_HOURS)
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024

# Behind Apache (or another reverse proxy): take the visitor's real IP address and https:// from the proxy's
# X-Forwarded-* headers. Without it every request seems to come from the proxy, so sign-in limits per address would
# lock out everyone at once. Never set it without a proxy in front, or visitors could fake their address.
if env_flag('BEHIND_PROXY'):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.json.sort_keys = False

db = SQLAlchemy(app)
migrate = Migrate(app, db, render_as_batch=True, directory=os.path.join(ROOT, 'migrations'))
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please sign in to see that page.'
login_manager.login_message_category = 'error'


@event.listens_for(Session, 'before_flush')
def fit_text_to_columns(session, flush_context, instances):
    """Trim text to its column's length before saving. SQLite ignores VARCHAR lengths but PostgreSQL refuses
    longer values, so a long name typed into a form would otherwise be an error."""
    for obj in list(session.new) + list(session.dirty):
        mapper = getattr(obj, '__mapper__', None)
        if mapper is None:
            continue
        for column in mapper.columns:
            limit = getattr(column.type, 'length', None)
            if limit and isinstance(column.type, db.String):
                value = getattr(obj, column.key, None)
                if isinstance(value, str) and len(value) > limit:
                    setattr(obj, column.key, value[:limit])


# ---------------------------------------------------------------------------
# Small helpers used across Kanto (and handy in your own pages)
# ---------------------------------------------------------------------------

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def derived_key(purpose):
    """A separate 32-byte key for PURPOSE, derived from SECRET_KEY.
    Changing SECRET_KEY therefore makes stored authenticator secrets and recovery codes unreadable:
    run `flask reset-mfa --all` afterwards so everyone sets their authenticator app up again."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=f'kanto:{purpose}'.encode()).derive(app.config['SECRET_KEY'].encode())


def mfa_cipher():
    return Fernet(base64.urlsafe_b64encode(derived_key('mfa-secret')))


def encrypt_secret(secret):
    return mfa_cipher().encrypt(secret.encode()).decode()


def decrypt_secret(stored):
    """The plain TOTP secret, or None if it can't be decrypted (e.g. SECRET_KEY changed)."""
    if not stored:
        return None
    try:
        return mfa_cipher().decrypt(stored.encode()).decode()
    except InvalidToken:
        return None


def hash_recovery_code(code):
    # Keyed, so a copy of the database alone isn't enough to brute-force the codes
    return hmac.new(derived_key('recovery-codes'), code.encode(), hashlib.sha256).hexdigest()


def csv_safe(value):
    """Stop spreadsheet apps treating text as a formula (e.g. a name of =HYPERLINK(...)) when a CSV is opened."""
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


class SafeCSVWriter:
    """csv.writer that applies csv_safe to every cell."""
    def __init__(self, out):
        self.writer = csv.writer(out)

    def writerow(self, row):
        self.writer.writerow([csv_safe(v) for v in row])


def is_local_url(target):
    """True for a path on this site (e.g. /things?view=all), never another host."""
    if not target or not target.startswith('/') or '\\' in target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and not target.startswith('//')


def local_referrer():
    """The page this request came from, as a path, when it's on this site; otherwise None."""
    ref = urlsplit(request.referrer or '')
    back = ref.path + (f'?{ref.query}' if ref.query else '')
    return back if ref.netloc == request.host and is_local_url(back) else None


def no_store(body):
    """Pages showing secrets (recovery codes, temporary passwords) mustn't be cached or come back with Back."""
    response = app.make_response(body)
    response.headers['Cache-Control'] = 'no-store'
    return response


def commit_keeping_loaded():
    """Commit without expiring what's already loaded (a normal commit makes the next page reload every row)."""
    session = db.session()
    session.expire_on_commit = False
    try:
        session.commit()
    finally:
        session.expire_on_commit = True


@app.template_filter('ukdate')
def ukdate(value):
    """A date (or YYYY-MM-DD text) as DD/MM/YYYY."""
    if isinstance(value, (date, datetime)):
        return value.strftime('%d/%m/%Y')
    try:
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return value or '—'


@app.template_filter('localtime')
def localtime(value):
    """A stored UTC time as UK time, DD/MM/YYYY HH:MM."""
    if not value:
        return ''
    return value.replace(tzinfo=timezone.utc).astimezone(UK).strftime('%d/%m/%Y %H:%M')


@app.context_processor
def inject_basics():
    return {'settings': settings, 'staging': STAGING, 'viewing_admin': g.get('viewing_admin'),
            'csp_nonce': g.get('csp_nonce', '')}


def log_action(action, detail=None, user=None, username=None, target=None, **fields):
    """Record an action in the activity log. Adds to the session; the caller commits.
    target: the user account the action was done to, when that's someone else (admin changes).
    fields: values for columns an app added to the log (ActivityLogExtras), e.g. audit_id=7."""
    from .models import ActivityLog
    if user is None and has_request_context() and current_user.is_authenticated:
        user = current_user
    viewing_admin = g.get('viewing_admin') if has_request_context() else None
    if viewing_admin is not None and user is not None and user.id == current_user.id:
        # Done while viewing as someone: recorded against the global admin, named "admin as viewed user"
        user, username = viewing_admin, f'{viewing_admin.username} as {user.username}'
    else:
        username = user.username if user else username
    db.session.add(ActivityLog(
        target_user_id=target.id if target else None,
        target_username=target.username if target else None,
        user_id=user.id if user else None,
        username=username,
        ip_address=request.remote_addr if has_request_context() else 'CLI',
        action=action,
        detail=detail,
        **fields,
    ))


# The rest of Kanto: each module adds its models, routes and page hooks to `app`
from . import models, display, security, auth, profile, admin, activity, debug, cli  # noqa: E402,F401


def prepare_database():
    """Bring the database up to date at startup. SQLite: applies any new migrations (migrations/) automatically.
    PostgreSQL: only warns, so changes happen when you choose (`flask --app app db upgrade`, which the systemd
    service in deploy/ runs before each start)."""
    import sys
    if app.config.get('TESTING') or {'db', 'copy-from-sqlite'} & set(sys.argv[1:]):
        return
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from flask_migrate import upgrade
    with app.app_context():
        if USING_SQLITE:
            upgrade()
            return
        with db.engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        head = ScriptDirectory.from_config(migrate.get_config()).get_current_head()
        if current != head:
            app.logger.warning('The database needs upgrading: run `flask --app app db upgrade`.')
