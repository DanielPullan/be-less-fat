"""Your profile: avatar, name, password, two-step verification (authenticator app, recovery codes, passkeys),
display settings saved to your account, badges, and easter eggs found."""
import json
from collections import Counter, namedtuple
from datetime import timedelta, timezone

import pyotp
import qrcode
import qrcode.image.svg
from flask import abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, AuthenticatorTransport, ResidentKeyRequirement,
                                      UserVerificationRequirement)
from werkzeug.security import check_password_hash, generate_password_hash

import settings
from . import REQUIRE_MFA, UK, app, db, decrypt_secret, encrypt_secret, log_action, no_store, utcnow
from .auth import (LIMIT_MFA, MIN_PASSWORD, options_response, passkey_site, remember_passkey_challenge,
                   start_session, take_passkey_challenge, throttle_clear, throttle_fail, throttle_wait, wait_message)
from .display import (DISPLAY_CHOICES, EASTER_EGGS, EGG_THEMES, EXTRA_DISPLAY, STANDARD_THEMES, THEME_LABELS,
                      display_prefs_json, extra_themes, save_theme)
from .models import AVATAR_COLOURS, AVATARS, ROLE_DEFS, ActivityLog, Passkey
from .security import needs_passkey_redirect, passkey_confirmed

Badge = namedtuple('Badge', 'emoji title description earned secret group')
SECRET_EGGS = [('konami', '🎮', 'Cheat code', 'Up, up, down, down…'),
               ('emergency', '📟', 'New emergency number', '0118 999…')] + list(getattr(settings, 'EXTRA_SECRET_EGGS', []))


def longest_streak(days):
    """Most consecutive calendar days in a set of dates."""
    best = 0
    for d in days:
        if d - timedelta(days=1) not in days:
            length = 1
            while d + timedelta(days=length) in days:
                length += 1
            best = max(best, length)
    return best


def badges_for(user, logs, counts):
    """Achievements for the profile page: Kanto's own, then the app's (settings.app_badges)."""
    local = [e.timestamp.replace(tzinfo=timezone.utc).astimezone(UK) for e in logs]
    hours = {t.hour for t in local}
    days = {t.date() for t in local}
    eggs = set(user.found_easter_eggs)
    prefs = json.loads(user.display_prefs or '{}')
    joined = user.created_at or (min(e.timestamp for e in logs) if logs else None)
    rows = [
        ('🔐', 'Locked down', 'Turned on two-step verification', user.has_two_step, False, 'Getting started'),
        ('🔑', 'Passwordless', 'Added a passkey', bool(user.passkeys), False, 'Getting started'),
        ('🎨', 'Make yourself at home', 'Changed the display settings',
         any(v not in ('system', 'default', 'standard', 'on') for k, v in prefs.items() if k not in EXTRA_DISPLAY), False,
         'Getting started'),
        ('🧑‍🎨', 'Looking good', 'Chose an avatar', bool(user.avatar), False, 'Getting started'),
        ('🎂', 'Many happy returns', f'Used {settings.APP_NAME} for a year',
         bool(joined and utcnow() - joined >= timedelta(days=365)), False, 'Getting started'),
    ]
    rows += list(settings.app_badges(user, logs, counts))
    rows += [
        ('🦉', 'Night owl', 'Did something after 10pm', any(h >= 22 for h in hours), False, 'Just for fun'),
        ('🐓', 'Early bird', 'Did something before 7am', any(h < 7 for h in hours), False, 'Just for fun'),
        ('🥪', 'Lunch? What lunch?', 'Did something between 12 and 1', 12 in hours, False, 'Just for fun'),
        ('🛋️', 'Weekend warrior', 'Did something at the weekend', any(d.weekday() >= 5 for d in days), False, 'Just for fun'),
        ('🎄', 'Festive spirit', 'Did something between Christmas Eve and New Year',
         any((d.month == 12 and d.day >= 24) or (d.month == 1 and d.day == 1) for d in days), False, 'Just for fun'),
        ('🔥', 'On a roll', f'Used {settings.APP_NAME} five days in a row', longest_streak(days) >= 5, False, 'Just for fun'),
        ('🌌', 'Up all night', 'Did something between 2am and 4am', bool(hours & {2, 3}), True, 'Just for fun'),
        ('🐈‍⬛', 'Unlucky for some', 'Did something on Friday the 13th',
         any(d.day == 13 and d.weekday() == 4 for d in days), True, 'Just for fun'),
    ]
    rows += [(emoji, title, description, egg in eggs, True, 'Just for fun') for egg, emoji, title, description in SECRET_EGGS]
    return [Badge(*row) for row in rows]


@app.route('/profile')
@login_required
def profile():
    user = current_user
    logs = ActivityLog.query.filter_by(user_id=user.id).order_by(ActivityLog.timestamp.desc()).all()
    counts = Counter(e.action for e in logs)
    sign_ins = [e for e in logs if e.action == 'Logged in'][:6]
    since = utcnow() - timedelta(days=30)
    failed_recent = sum(1 for e in logs if e.action == 'Failed verification code' and e.timestamp >= since) + \
        ActivityLog.query.filter(ActivityLog.action == 'Failed login', ActivityLog.username == user.username,
                                 ActivityLog.timestamp >= since).count()
    member_since = user.created_at or (logs[-1].timestamp if logs else None)
    groups = list(dict.fromkeys(['Getting started'] + settings.BADGE_GROUPS + ['Just for fun']))
    extra = settings.profile_context(user, logs, counts) if hasattr(settings, 'profile_context') else {}
    return render_template('kanto/profile.html', user=user, role_defs=[ROLE_DEFS[c] for c in ROLE_DEFS if c in user.roles],
                           stats=settings.profile_stats(user, logs, counts), sign_ins=sign_ins,
                           failed_recent=failed_recent, member_since=member_since,
                           badges=badges_for(user, logs, counts), badge_groups=groups, require_mfa=REQUIRE_MFA, **extra)


def check_own_password(password):
    """Check the signed-in user's password, re-entered to confirm a change. Wrong guesses are limited like
    verification codes, so a stolen session can't be used to guess the password. Returns (ok, wait message)."""
    key = f'password:{current_user.id}'
    if wait := throttle_wait(key):
        return False, wait_message(wait)
    if check_password_hash(current_user.password_hash, password):
        throttle_clear(key)
        return True, None
    throttle_fail(key, LIMIT_MFA)
    log_action('Wrong password re-entered')
    db.session.commit()
    return False, None


@app.route('/profile/name', methods=['POST'])
@login_required
def profile_name():
    full_name = request.form.get('full_name', '').strip()[:150]
    if (full_name or None) != current_user.full_name:
        log_action('Name changed', detail=f'{current_user.full_name or "(none)"} → {full_name or "(none)"}')
        current_user.full_name = full_name or None
        db.session.commit()
        flash('Name saved.', 'success')
    return redirect(url_for('profile') + '#security')


@app.route('/profile/avatar', methods=['POST'])
@login_required
def profile_avatar():
    avatar, colour = request.form.get('avatar', ''), request.form.get('colour', '')
    if avatar and avatar not in AVATARS or colour and colour not in AVATAR_COLOURS:
        abort(400)
    if (avatar or None, colour or None) != (current_user.avatar, current_user.avatar_colour):
        current_user.avatar, current_user.avatar_colour = avatar or None, colour or None
        log_action('Avatar changed', detail=f'{AVATARS[avatar]} on {AVATAR_COLOURS[colour][0]}' if avatar and colour
                   else AVATARS.get(avatar, 'Initials'))
        db.session.commit()
        flash('Avatar saved.', 'success')
    return redirect(url_for('profile') + '#avatar')


@app.route('/profile/password', methods=['POST'])
@login_required
def profile_password():
    current, new, confirm = (request.form.get(k, '') for k in ('current_password', 'new_password', 'confirm_password'))
    password_ok, wait = check_own_password(current)
    if not password_ok:
        flash(wait or 'Your current password was wrong.', 'error')
    elif len(new) < MIN_PASSWORD:
        flash(f'Choose a new password of at least {MIN_PASSWORD} characters.', 'error')
    elif new != confirm:
        flash('The new passwords don\'t match.', 'error')
    elif new == current:
        flash('The new password must be different from the current one.', 'error')
    else:
        current_user.password_hash = generate_password_hash(new)
        current_user.must_change_password = False
        current_user.end_other_sessions()
        start_session(current_user)
        log_action('Password changed', detail='Other sessions signed out')
        db.session.commit()
        flash('Password changed.', 'success')
    return redirect(url_for('profile') + '#security')


def qr_svg(data):
    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return image.to_string(encoding='unicode')


@app.route('/profile/mfa', methods=['GET', 'POST'])
@login_required
def mfa_setup():
    if current_user.mfa_enabled:
        return redirect(url_for('profile') + '#security')
    # Held as a pending secret (encrypted, on the account) until a code from it is confirmed
    secret = decrypt_secret(current_user.mfa_pending_secret)
    if not secret:
        secret = pyotp.random_base32()
        current_user.mfa_pending_secret = encrypt_secret(secret)
        db.session.commit()
    if request.method == 'POST':
        if current_user.verify_totp(request.form.get('code', ''), secret=secret):
            current_user.totp_secret, current_user.mfa_enabled = encrypt_secret(secret), True
            current_user.mfa_pending_secret = None
            codes = current_user.new_recovery_codes()
            # Sign out any other sessions, e.g. someone who had the password before MFA was on
            current_user.end_other_sessions()
            start_session(current_user)
            log_action('Two-step verification turned on', detail='Other sessions signed out')
            db.session.commit()
            return no_store(render_template('kanto/mfa_codes.html', codes=codes, first_time=True))
        flash('That code didn\'t match. Check the time on your phone is right and try the newest code.', 'error')
    uri = pyotp.TOTP(secret).provisioning_uri(name=current_user.username, issuer_name=settings.APP_NAME)
    return no_store(render_template('kanto/mfa_setup.html', qr=qr_svg(uri),
                                    secret=' '.join(secret[i:i + 4] for i in range(0, len(secret), 4))))


@app.route('/profile/mfa/codes', methods=['POST'])
@login_required
def mfa_new_codes():
    mfa_key = f'mfa:{current_user.id}'
    if wait := throttle_wait(mfa_key):
        flash(wait_message(wait), 'error')
        return redirect(url_for('profile') + '#security')
    if not current_user.mfa_enabled or not current_user.verify_totp(request.form.get('code', '')):
        throttle_fail(mfa_key, LIMIT_MFA)
        db.session.commit()
        flash('Enter a current code from your authenticator app to make new recovery codes.', 'error')
        return redirect(url_for('profile') + '#security')
    throttle_clear(mfa_key)
    codes = current_user.new_recovery_codes()
    log_action('Recovery codes replaced')
    db.session.commit()
    return no_store(render_template('kanto/mfa_codes.html', codes=codes, first_time=False))


@app.route('/profile/mfa/disable', methods=['POST'])
@login_required
def mfa_disable():
    if REQUIRE_MFA and not current_user.passkeys:
        flash('Two-step verification is required for everyone, so it can\'t be turned off. '
              'Add a passkey first if you want to stop using the app.', 'error')
    elif not (checked := check_own_password(request.form.get('password', '')))[0]:
        flash(checked[1] or 'Enter your password to turn off two-step verification.', 'error')
    else:
        current_user.clear_mfa()
        current_user.end_other_sessions()
        start_session(current_user)
        log_action('Two-step verification turned off' if not current_user.passkeys else 'Authenticator app turned off',
                   detail='Other sessions signed out')
        db.session.commit()
        flash('Your passkeys still protect your account.' if current_user.passkeys
              else 'Two-step verification is off.', 'success')
    return redirect(url_for('profile') + '#security')


@app.route('/profile/passkeys/options', methods=['POST'])
@login_required
def passkey_options():
    if current_user.passkeys and not passkey_confirmed():
        return jsonify(error='Confirm it\'s you with one of your existing passkeys first (link above).'), 400
    options = generate_registration_options(
        rp_id=passkey_site()[0], rp_name=settings.APP_NAME, user_id=str(current_user.id).encode(),
        user_name=current_user.username, user_display_name=current_user.display_name,
        exclude_credentials=[p.descriptor for p in current_user.passkeys],
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,
                                                               user_verification=UserVerificationRequirement.REQUIRED))
    remember_passkey_challenge('register', options.challenge, current_user.id)
    return options_response(options)


@app.route('/profile/passkeys', methods=['POST'])
@login_required
def passkey_add():
    data = request.get_json(silent=True) or {}
    issued = take_passkey_challenge('register')
    if not issued or issued['user_id'] != current_user.id:
        return jsonify(error='That took too long. Try adding the passkey again.'), 400
    if current_user.passkeys and not passkey_confirmed():
        # Otherwise a phished password and code could add the attacker's own passkey
        return jsonify(error='Confirm it\'s you with one of your existing passkeys first (link above).'), 400
    rp_id, origin = passkey_site()
    try:
        verified = verify_registration_response(
            credential=data.get('credential'), expected_challenge=base64url_to_bytes(issued['challenge']),
            expected_rp_id=rp_id, expected_origin=origin, require_user_verification=True)
        transports = [t for t in data['credential']['response'].get('transports') or []
                      if t in {t.value for t in AuthenticatorTransport}]
    except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError):
        return jsonify(error='The passkey couldn\'t be checked, so it wasn\'t added. Try again.'), 400
    credential_id = bytes_to_base64url(verified.credential_id)
    if Passkey.query.filter_by(credential_id=credential_id).first():
        return jsonify(error='That passkey is already added.'), 400
    first = not current_user.has_two_step
    name = ' '.join(str(data.get('name') or '').split())[:100] or f'Passkey {len(current_user.passkeys) + 1}'
    db.session.add(Passkey(user_id=current_user.id, credential_id=credential_id, name=name,
                           public_key=verified.credential_public_key, sign_count=verified.sign_count,
                           transports=json.dumps(transports), synced=verified.credential_backed_up))
    if first:
        # As when the authenticator app is turned on: sign out anyone who had the password before
        current_user.end_other_sessions()
        start_session(current_user)
    log_action('Passkey added', detail=name + ('; other sessions signed out' if first else ''))
    db.session.commit()
    flash(f'Passkey "{name}" added. Next time, choose "Sign in with a passkey".', 'success')
    return jsonify(redirect=url_for('profile') + '#security')


@app.route('/profile/passkeys/<int:passkey_id>/remove', methods=['POST'])
@login_required
def passkey_remove(passkey_id):
    passkey = db.get_or_404(Passkey, passkey_id)
    if passkey.user_id != current_user.id:
        abort(404)
    if not passkey_confirmed():
        return needs_passkey_redirect('Confirm it\'s you with a passkey before removing one. Lost it? '
                                      'Ask an administrator to reset your two-step verification.',
                                      url_for('profile') + '#security')
    if not (checked := check_own_password(request.form.get('password', '')))[0]:
        flash(checked[1] or 'Enter your password to remove a passkey.', 'error')
    elif REQUIRE_MFA and not current_user.mfa_enabled and len(current_user.passkeys) == 1:
        flash('Two-step verification is required, so you can\'t remove your only passkey. '
              'Add another passkey or set up an authenticator app first.', 'error')
    else:
        current_user.passkeys.remove(passkey)
        log_action('Passkey removed', detail=passkey.name)
        db.session.commit()
        flash(f'Passkey "{passkey.name}" removed. Delete it from the device or password manager too.', 'success')
    return redirect(url_for('profile') + '#security')


@app.route('/profile/display', methods=['POST'])
@login_required
def profile_display():
    """Save Display menu choices to the account, so they follow the user between devices."""
    data = request.get_json(silent=True) or {}
    prefs = {k: v for k, v in data.items() if k in DISPLAY_CHOICES and v in DISPLAY_CHOICES[k]}
    prefs.setdefault('celebrations', 'on')  # pages from before the setting existed
    # The app's extra settings are optional in what's sent; keep the saved choice for any left out
    saved = json.loads(display_prefs_json() or '{}')
    for name in EXTRA_DISPLAY:
        if name not in prefs and name in saved:
            prefs[name] = saved[name]
    if set(prefs) - set(EXTRA_DISPLAY) != set(DISPLAY_CHOICES) - set(EXTRA_DISPLAY):
        abort(400)
    if prefs['theme'] not in STANDARD_THEMES and prefs['theme'] not in extra_themes():
        prefs['theme'] = 'system'
    if g.get('viewing_admin') is not None:
        session['view_as_display'] = json.dumps(prefs)  # this viewing session only; the viewed user's settings stay
        return '', 204
    current_user.display_prefs = json.dumps(prefs)
    db.session.commit()
    return '', 204


@app.route('/profile/badges', methods=['POST'])
@login_required
def profile_badges():
    """Show or hide badges on the profile page. They're still earned while hidden."""
    current_user.hide_badges = request.form.get('hide') == '1'
    db.session.commit()
    flash('Badges hidden. You can show them again from your profile.' if current_user.hide_badges else 'Badges shown.', 'success')
    return redirect(url_for('profile') + '#badges')


@app.route('/profile/easter-egg', methods=['POST'])
@login_required
def profile_easter_egg():
    egg = (request.get_json(silent=True) or {}).get('egg')
    if egg not in EASTER_EGGS:
        abort(400)
    found = current_user.found_easter_eggs
    if egg not in found:
        current_user.easter_eggs = json.dumps(found + [egg])
    # Some eggs unlock a theme (EGG_THEMES) and switch to it straight away (not while viewing as someone)
    theme = next((t for t, e in EGG_THEMES.items() if e == egg), None)
    if theme and g.get('viewing_admin') is None:
        save_theme(current_user, theme)
    db.session.commit()
    return ({'theme': theme, 'label': THEME_LABELS[theme]}, 200) if theme else ('', 204)
