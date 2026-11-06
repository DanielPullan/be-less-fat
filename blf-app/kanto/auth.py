"""Signing in and out: password, then an authenticator code, recovery code or passkey; passkey-only sign-in;
confirming with a passkey part-way through a session; lockouts after repeated failures; and signing out for good."""
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from webauthn import generate_authentication_options, options_to_json, verify_authentication_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import UserVerificationRequirement
from werkzeug.security import check_password_hash, generate_password_hash

import settings
from . import (PASSKEY_ORIGIN, PASSKEY_RP_ID, REQUIRE_MFA, SESSION_MAX_HOURS, app, db, is_local_url, log_action,
               utcnow)
from .models import Passkey, SignedOutSession, Throttle, User
from .security import passkey_confirmed

MFA_PENDING_SECONDS = 300
# Failed attempts allowed per window before that key is locked for the rest of the window.
# Counted in the database, so clearing or replaying cookies doesn't reset them.
THROTTLE_WINDOW = timedelta(minutes=15)
LIMIT_PER_USERNAME = 5       # wrong passwords for one username from one address: locks only that address out of it
LIMIT_PER_USERNAME_ALL = 50  # wrong passwords for one username from all addresses together: locks the username
LIMIT_PER_IP = 20            # wrong passwords from one address, across usernames
LIMIT_MFA = 5                # wrong verification codes for one account
# Checked against when the username doesn't exist, so both cases take the same time
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(16))
USERNAME_PATTERN = re.compile(r'[A-Za-z0-9._@-]{3,50}')
EMAIL_PATTERN = re.compile(r'[^@\s]{1,64}@[^@\s]+\.[^@\s]+')
MIN_PASSWORD = 12

# The same for a wrong password, an unknown name and a disabled account, so it doesn't tell anyone which accounts exist
WRONG_SIGN_IN = ('That username or password isn\'t right. Check them (passwords are case-sensitive) and try again. '
                 'If you\'ve forgotten your password, ask an admin to set a temporary one.')


def throttle_wait(key):
    """Seconds until KEY may try again (0 if not locked)."""
    record = db.session.get(Throttle, key)
    if record and record.locked_until and record.locked_until > utcnow():
        return int((record.locked_until - utcnow()).total_seconds()) + 1
    return 0


def throttle_fail(key, limit):
    record = db.session.get(Throttle, key)
    now = utcnow()
    if record is None:
        record = Throttle(key=key, failures=0, window_start=now)
        db.session.add(record)
    if now - record.window_start > THROTTLE_WINDOW:
        record.failures, record.window_start = 0, now
    record.failures += 1
    if record.failures >= limit:
        record.locked_until = now + THROTTLE_WINDOW
        record.failures, record.window_start = 0, now


def throttle_clear(key):
    if record := db.session.get(Throttle, key):
        db.session.delete(record)


# Wrong passwords are counted per username AND address, so someone guessing at a username only locks their own
# address out of it: the real user, elsewhere, can still sign in. A much higher limit across all addresses still
# stops a spread-out attack on one username.
def username_key(username):
    return f'login-user:{username.lower()[:100]}'


def username_ip_key(username, ip):
    return f'login-user-ip:{username.lower()[:100]}|{ip}'


def username_lockouts(username):
    """Every sign-in lockout record for USERNAME: across all addresses, and from each address."""
    return Throttle.query.filter(db.or_(Throttle.key == username_key(username),
                                        Throttle.key.startswith(username_ip_key(username, ''), autoescape=True))).all()


def clear_username_lockouts(username):
    for record in username_lockouts(username):
        db.session.delete(record)


def username_error(username, user=None):
    """Why USERNAME can't be used (for USER, if renaming), or None."""
    if not USERNAME_PATTERN.fullmatch(username):
        return 'Usernames are 3–50 characters: letters, numbers, dots, dashes, underscores or @.'
    taken = User.query.filter(db.or_(db.func.lower(User.username) == username.lower(),
                                     User.email == username.lower())).first()
    if taken and taken != user:
        return f'There is already a user called {username}.' if taken.username.lower() == username.lower() \
            else f'{username} is another account\'s email address, which also works as a sign-in name.'
    return None


def email_error(email, user=None):
    """Why EMAIL (already in lower case) can't be USER's, or None. Blank is fine: it's optional."""
    if not email:
        return None
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return f'{email} doesn\'t look like an email address.'
    taken = User.query.filter(db.or_(User.email == email, db.func.lower(User.username) == email)).first()
    if taken and taken != user:
        return f'{email} is already used by another account.'
    return None


def rename_user(user, username):
    """Change USER's sign-in name. Everything else is linked by account ID, so only the sign-in lockouts (kept by
    name) move with them; the log and other records keep the name used at the time."""
    old = user.username
    if old.lower() != username.lower():
        clear_username_lockouts(username)  # attempts on the new name were against no account
        db.session.flush()
        for record in username_lockouts(old):
            record.key = record.key.replace(old.lower()[:100], username.lower()[:100], 1)
    user.username = username


def wait_message(seconds):
    minutes = max(1, -(-seconds // 60))
    return f'Too many failed attempts. Try again in {minutes} minute{"s" if minutes != 1 else ""}.'


def landing_page(user):
    if REQUIRE_MFA and not user.has_two_step:
        return url_for('profile') + '#security'
    return url_for('home')


def start_session(user):
    """Sign in with a fresh, time-limited session."""
    # Callers may pass current_user; login_user needs the real object, not the proxy
    user = getattr(user, '_get_current_object', lambda: user)()
    # Restarting the same person's session (e.g. after a password change) keeps how they signed in
    same = current_user.is_authenticated and current_user.id == user.id
    kept = {k: session[k] for k in ('signed_in_with', 'passkey_ok') if same and k in session}
    session.clear()  # drop anything carried over from before sign-in
    login_user(user)
    session.permanent = True  # idle timeout: PERMANENT_SESSION_LIFETIME
    session['login_at'] = time.time()  # absolute timeout: SESSION_MAX_HOURS
    session['sid'] = secrets.token_urlsafe(32)  # this session's own id, so signing out can end it for good
    session.update(kept)


def complete_login(user, method=None, strength='password'):
    start_session(user)
    session['signed_in_with'] = strength
    session['passkey_ok'] = strength == 'passkey'
    log_action('Logged in', user=user, detail=method)
    db.session.commit()
    if user.must_change_password:
        flash('Please choose a new password to replace the temporary one.', 'error')
        return redirect(url_for('profile') + '#security')
    if REQUIRE_MFA and not user.has_two_step:
        flash('Two-step verification is required. Set it up below to carry on.', 'error')
    return redirect(landing_page(user))


def user_by_sign_in_name(name):
    """The account with this username, or this email address (either can be used to sign in)."""
    if not name:
        return None
    return User.query.filter_by(username=name).first() or \
        (User.query.filter_by(email=name.lower()).first() if '@' in name else None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = user_by_sign_in_name(username)
        # Lockouts count against the account, whichever of its sign-in names is used
        name = user.username if user else username
        user_key, ip_key = username_key(name), f'login-ip:{request.remote_addr}'
        user_ip_key = username_ip_key(name, request.remote_addr)
        wait = max(throttle_wait(user_key), throttle_wait(user_ip_key), throttle_wait(ip_key))
        if wait:
            log_action('Sign-in blocked (too many attempts)', username=username[:100])
            db.session.commit()
            flash(wait_message(wait), 'error')
            return render_template('kanto/login.html'), 429
        password_ok = check_password_hash(user.password_hash if user else DUMMY_PASSWORD_HASH, password)
        if user and password_ok and not user.is_active:
            log_action('Sign-in refused (account disabled)', username=username[:100])
            db.session.commit()
            flash(WRONG_SIGN_IN, 'error')
            return render_template('kanto/login.html')
        if user and password_ok:
            throttle_clear(user_ip_key)
            if user.has_two_step:
                # Password is right; hold the login until the second step is passed
                session.clear()
                session['mfa_pending'] = {'user_id': user.id, 'since': time.time()}
                db.session.commit()
                return redirect(url_for('login_mfa'))
            return complete_login(user)
        throttle_fail(user_ip_key, LIMIT_PER_USERNAME)
        throttle_fail(user_key, LIMIT_PER_USERNAME_ALL)
        throttle_fail(ip_key, LIMIT_PER_IP)
        log_action('Failed login', username=username[:100])
        db.session.commit()
        flash(WRONG_SIGN_IN, 'error')
    return render_template('kanto/login.html')


@app.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    """Create your own account (only with settings.ALLOW_SIGN_UP). Limited per address like wrong passwords."""
    if not settings.ALLOW_SIGN_UP:
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        ip_key = f'sign-up-ip:{request.remote_addr}'
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password, confirm = request.form.get('password') or '', request.form.get('confirm_password') or ''
        if wait := throttle_wait(ip_key):
            flash(wait_message(wait), 'error')
        elif problem := username_error(username) or email_error(email):
            flash(problem, 'error')
        elif len(password) < MIN_PASSWORD:
            flash(f'Choose a password of at least {MIN_PASSWORD} characters.', 'error')
        elif password != confirm:
            flash('The passwords don\'t match. Type the same password in both boxes.', 'error')
        else:
            user = User(username=username, email=email or None, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.flush()
            throttle_fail(ip_key, LIMIT_PER_IP)  # counts accounts made from this address, so it can't mass-create
            log_action('Signed up', user=user)
            complete_login(user, 'New account', 'password')
            flash(f'Welcome to {settings.APP_NAME}! Add a passkey or an authenticator app below to keep your account safe.', 'success')
            return redirect(url_for('profile') + '#security') if not settings.SIGN_UP_LANDING else redirect(url_for(settings.SIGN_UP_LANDING))
        db.session.commit()
    return render_template('kanto/sign_up.html')


@app.route('/login/verify', methods=['GET', 'POST'])
def login_mfa():
    pending = session.get('mfa_pending')
    user = db.session.get(User, pending['user_id']) if pending else None
    if not user or not user.is_active or time.time() - pending['since'] > MFA_PENDING_SECONDS:
        session.pop('mfa_pending', None)
        flash('Your sign-in timed out. Enter your password again.', 'error')
        return redirect(url_for('login'))
    mfa_key = f'mfa:{user.id}'
    if wait := throttle_wait(mfa_key):
        session.pop('mfa_pending', None)
        flash(wait_message(wait), 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if user.verify_totp(code):
            throttle_clear(mfa_key)
            return complete_login(user, 'With authenticator code', 'code')
        if user.use_recovery_code(code):
            throttle_clear(mfa_key)
            response = complete_login(user, f'With a recovery code ({user.recovery_codes_left} left)', 'recovery')
            flash(f'You signed in with a recovery code. You have {user.recovery_codes_left} left; '
                  'make new ones on your profile if you are running low.', 'error')
            return response
        throttle_fail(mfa_key, LIMIT_MFA)
        log_action('Failed verification code', user=user)
        db.session.commit()
        if wait := throttle_wait(mfa_key):
            session.pop('mfa_pending', None)
            flash('Too many incorrect codes. ' + wait_message(wait), 'error')
            return redirect(url_for('login'))
        flash('That code didn\'t work. Check your authenticator app and try again.', 'error')
    return render_template('kanto/login_mfa.html', user=user)


# Passkey sign-in: the browser signs a one-off challenge with a passkey saved on the device (or a phone nearby).
# From the sign-in page it's a whole sign-in, no password needed; after a password it's the second step.
PASSKEY_CHALLENGE_SECONDS = 300


def passkey_site():
    """(rp_id, origin) the browser will have used: from PASSKEY_RP_ID/PASSKEY_ORIGIN, or the address being visited."""
    origin = PASSKEY_ORIGIN or request.host_url.rstrip('/')
    return PASSKEY_RP_ID or urlsplit(origin).hostname, origin


def remember_passkey_challenge(purpose, challenge, user_id=None):
    session['passkey'] = {'purpose': purpose, 'challenge': bytes_to_base64url(challenge), 'user_id': user_id,
                          'since': time.time()}


def take_passkey_challenge(purpose):
    """The challenge issued for PURPOSE, used up so it can't be replayed; None if missing or too old."""
    issued = session.pop('passkey', None)
    if not issued or issued.get('purpose') != purpose or time.time() - issued['since'] > PASSKEY_CHALLENGE_SECONDS:
        return None
    return issued


def options_response(options):
    return app.response_class(options_to_json(options), mimetype='application/json')


@app.route('/login/passkey/options', methods=['POST'])
def login_passkey_options():
    user = None
    if (request.get_json(silent=True) or {}).get('second_step'):
        # After a password: only that account's passkeys
        pending = session.get('mfa_pending')
        user = db.session.get(User, pending['user_id']) if pending else None
        if not user or not user.is_active or time.time() - pending['since'] > MFA_PENDING_SECONDS:
            return jsonify(error='Your sign-in timed out. Start again.', redirect=url_for('login')), 400
    options = generate_authentication_options(
        rp_id=passkey_site()[0], user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[p.descriptor for p in user.passkeys] if user else None)
    remember_passkey_challenge('login', options.challenge, user.id if user else None)
    return options_response(options)


def check_passkey(issued, credential, passkey):
    """Verify a signed passkey challenge; raises on anything wrong. Returns the new signature count."""
    rp_id, origin = passkey_site()
    verified = verify_authentication_response(
        credential=credential, expected_challenge=base64url_to_bytes(issued['challenge']), expected_rp_id=rp_id,
        expected_origin=origin, credential_public_key=passkey.public_key,
        credential_current_sign_count=passkey.sign_count, require_user_verification=True)
    return verified.new_sign_count


@app.route('/login/passkey', methods=['POST'])
def login_passkey():
    ip_key = f'login-ip:{request.remote_addr}'
    if wait := throttle_wait(ip_key):
        return jsonify(error=wait_message(wait)), 429
    issued = take_passkey_challenge('login')
    if not issued:
        return jsonify(error='That took too long. Try again.'), 400
    credential = request.get_json(silent=True) or {}
    passkey = Passkey.query.filter_by(credential_id=str(credential.get('id', ''))[:1400]).first()
    user = passkey.user if passkey else None
    try:
        if not user or (issued['user_id'] and issued['user_id'] != user.id):
            raise ValueError('Unknown passkey')
        sign_count = check_passkey(issued, credential, passkey)
    except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError):
        throttle_fail(ip_key, LIMIT_PER_IP)
        log_action('Failed passkey sign-in', user=user)
        db.session.commit()
        return jsonify(error='That passkey wasn\'t recognised. Try another, or sign in with your password.'), 400
    if not user.is_active:
        log_action('Sign-in refused (account disabled)', username=user.username)
        db.session.commit()
        return jsonify(error='That passkey wasn\'t recognised. Try another, or sign in with your password.'), 400
    passkey.sign_count, passkey.last_used_at = sign_count, utcnow()
    throttle_clear(f'mfa:{user.id}')
    return jsonify(redirect=complete_login(user, f'With a passkey ({passkey.name})', 'passkey').location)


def next_url(default='home'):
    target = request.args.get('next', '')
    return target if is_local_url(target) else url_for(default)


@app.route('/confirm-passkey')
@login_required
def confirm_passkey():
    if passkey_confirmed():
        return redirect(next_url())
    return render_template('kanto/confirm_passkey.html', next_url=next_url(),
                           global_admin='global_admin' in current_user.roles)


@app.route('/confirm-passkey/options', methods=['POST'])
@login_required
def confirm_passkey_options():
    if not current_user.passkeys:
        return jsonify(error='You haven\'t added a passkey yet. Add one on your profile first.'), 400
    options = generate_authentication_options(
        rp_id=passkey_site()[0], user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[p.descriptor for p in current_user.passkeys])
    remember_passkey_challenge('confirm', options.challenge, current_user.id)
    return options_response(options)


@app.route('/confirm-passkey', methods=['POST'])
@login_required
def confirm_passkey_check():
    issued = take_passkey_challenge('confirm')
    if not issued or issued['user_id'] != current_user.id:
        return jsonify(error='That took too long. Try again.'), 400
    credential = request.get_json(silent=True) or {}
    passkey = Passkey.query.filter_by(credential_id=str(credential.get('id', ''))[:1400],
                                      user_id=current_user.id).first()
    try:
        if not passkey:
            raise ValueError('Not one of this user\'s passkeys')
        sign_count = check_passkey(issued, credential, passkey)
    except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError):
        log_action('Failed passkey confirmation')
        db.session.commit()
        return jsonify(error='That passkey wasn\'t recognised. Use one you\'ve added to this account.'), 400
    passkey.sign_count, passkey.last_used_at = sign_count, utcnow()
    session['passkey_ok'] = True
    log_action('Confirmed with a passkey', detail=passkey.name)
    db.session.commit()
    return jsonify(redirect=next_url())


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    log_action('Logged out')
    end_this_session()
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for('index'))


def end_this_session():
    """Record this session as signed out, so its cookie stops working everywhere (see SignedOutSession).
    Also tidies away records of sessions that have expired by now. Caller commits."""
    now = utcnow()
    SignedOutSession.query.filter(SignedOutSession.expires_at < now).delete()
    if sid := session.get('sid'):
        started = datetime.fromtimestamp(session.get('login_at', time.time()), timezone.utc).replace(tzinfo=None)
        expires = max(started + timedelta(hours=SESSION_MAX_HOURS), now) + timedelta(minutes=5)
        if db.session.get(SignedOutSession, sid) is None:
            db.session.add(SignedOutSession(sid=sid, expires_at=expires))
