"""Kanto's tables: user accounts and their roles, passkeys, sign-in lockouts, the activity log and signed-out sessions."""
import hmac
import importlib
import json
import secrets
import time
from datetime import datetime

import pyotp
from flask import session
from flask_login import UserMixin
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import AuthenticatorTransport, PublicKeyCredentialDescriptor

import settings
from . import db, decrypt_secret, hash_recovery_code, hash_token, login_manager, utcnow

ROLE_DEFS = settings.ROLE_DEFS

# An app can add its own columns and behaviour to Kanto's tables: settings.MODEL_EXTRAS names a module with
# UserExtras and/or ActivityLogExtras classes (plain columns, and methods that may override Kanto's and call super()),
# and optionally after_models(User, ActivityLog) to run once they exist (e.g. SQLAlchemy event listeners).
_extras = importlib.import_module(settings.MODEL_EXTRAS) if getattr(settings, 'MODEL_EXTRAS', None) else None
_USER_EXTRAS = (_extras.UserExtras,) if hasattr(_extras, 'UserExtras') else ()
_LOG_EXTRAS = (_extras.ActivityLogExtras,) if hasattr(_extras, 'ActivityLogExtras') else ()
# Roles only someone holding one can give or take away (global admin always works this way)
PROTECTED_ROLES = set(settings.PROTECTED_ROLES)

# Profile pictures: original storybook-style animals (kanto/static/img/avatars.svg), each on a colour of the
# person's choice, or their initials
AVATARS = {'fox': 'Fox in a scarf', 'owl': 'Wise owl', 'bear': 'Bear in a bobble hat', 'rabbit': 'Rabbit',
           'cat': 'Black cat', 'dog': 'Floppy-eared dog', 'frog': 'Frog with a crown', 'penguin': 'Penguin in a scarf',
           'lion': 'Lion', 'elephant': 'Elephant', 'hedgehog': 'Hedgehog with an apple', 'mouse': 'Mouse with a book',
           'panda': 'Panda', 'tiger': 'Tiger', 'giraffe': 'Giraffe', 'koala': 'Koala', 'pig': 'Pig with a bow',
           'duck': 'Duckling', 'whale': 'Whale', 'dragon': 'Friendly dragon', 'unicorn': 'Unicorn', 'sloth': 'Sleepy sloth',
           'octopus': 'Octopus'}
AVATAR_COLOURS = {'sky': ('Sky', '#7cc6fe'), 'sunshine': ('Sunshine', '#ffe066'), 'mint': ('Mint', '#9be7c4'),
                  'coral': ('Coral', '#ff8a80'), 'lavender': ('Lavender', '#c9b6ff'), 'peach': ('Peach', '#ffc9a3'),
                  'bubblegum': ('Bubblegum', '#ffb3d9'), 'lime': ('Lime', '#c5f277'), 'teal': ('Teal', '#2fb5a5'),
                  'forest': ('Forest', '#2f7d4f'), 'navy': ('Navy', '#2d3a8c'), 'plum': ('Plum', '#7b3fa0'),
                  'slate': ('Slate', '#64748b'), 'cream': ('Cream', '#fff4dc')}
DEFAULT_AVATAR_COLOUR = 'sky'


class Throttle(db.Model):
    """Failed sign-in / verification attempts per key (username, IP address or account)."""
    key = db.Column(db.String(200), primary_key=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    window_start = db.Column(db.DateTime, nullable=False)
    locked_until = db.Column(db.DateTime)


class KantoUser:
    """What Kanto's User can do. Kept apart from the columns so an app's UserExtras can override any of it."""

    def __init__(self, **kwargs):
        roles = kwargs.pop('roles', None)
        super().__init__(**kwargs)
        self.set_roles(roles if roles is not None else settings.DEFAULT_ROLES)

    def get_id(self):
        return f'{self.id}:{self.session_version or 0}'

    def end_other_sessions(self):
        """Invalidate every existing session. Call start_session() afterwards to keep the current one."""
        self.session_version = (self.session_version or 0) + 1

    @property
    def is_active(self):
        return bool(self.active)

    # --- roles ---
    @property
    def roles(self):
        return {r.role for r in self.role_rows}

    def set_roles(self, codes):
        codes = {c for c in codes if c in ROLE_DEFS}
        current = {r.role: r for r in self.role_rows}
        self.role_rows = [current.get(c) or UserRole(role=c) for c in sorted(codes)]

    def has_role(self, code):
        return code in self.roles

    @property
    def role_labels(self):
        return [ROLE_DEFS[c].label for c in ROLE_DEFS if c in self.roles]

    @property
    def has_protected_role(self):
        return bool(self.roles & PROTECTED_ROLES)

    @property
    def can_admin(self):
        return 'admin' in self.roles and self.is_active

    @property
    def can_view_log(self):
        """The activity log (who did what, sign-ins and their IP addresses): admins and global admins."""
        return bool(self.roles & {'admin', 'global_admin'}) and self.is_active

    @property
    def display_name(self):
        return self.full_name or self.username

    # --- two-step verification ---
    def verify_totp(self, code, secret=None):
        """Check a 6-digit code (allowing one step of clock drift) and refuse reuse of an accepted code."""
        secret = secret or decrypt_secret(self.totp_secret)
        code = ''.join(ch for ch in (code or '') if ch.isdigit())
        if not secret or len(code) != 6:
            return False
        totp = pyotp.TOTP(secret)
        now = time.time()
        for drift in (0, -1, 1):
            step = totp.timecode(datetime.fromtimestamp(now + drift * totp.interval))
            if hmac.compare_digest(totp.generate_otp(step), code):
                if self.mfa_last_step is not None and step <= self.mfa_last_step:
                    return False
                self.mfa_last_step = step
                return True
        return False

    def new_recovery_codes(self, count=8):
        codes = [f'{secrets.token_hex(3)}-{secrets.token_hex(3)}' for _ in range(count)]
        self.recovery_codes = json.dumps([hash_recovery_code(c) for c in codes])
        return codes

    def use_recovery_code(self, code):
        code = (code or '').strip().lower().replace(' ', '')
        if len(code) == 12 and '-' not in code:
            code = code[:6] + '-' + code[6:]
        hashes = json.loads(self.recovery_codes or '[]')
        for digest in (hash_recovery_code(code), hash_token(code)):
            if digest in hashes:
                hashes.remove(digest)
                self.recovery_codes = json.dumps(hashes)
                return True
        return False

    def clear_mfa(self):
        """Turn off the authenticator app (passkeys are separate; see remove_passkeys)."""
        self.mfa_enabled = False
        self.totp_secret = self.mfa_pending_secret = self.recovery_codes = self.mfa_last_step = None

    def remove_passkeys(self):
        self.passkeys.clear()  # delete-orphan: each one is deleted

    @property
    def has_two_step(self):
        """Two-step verification is on: an authenticator app, or at least one passkey."""
        return bool(self.mfa_enabled or self.passkeys)

    @property
    def recovery_codes_left(self):
        return len(json.loads(self.recovery_codes or '[]'))

    @property
    def found_easter_eggs(self):
        return json.loads(self.easter_eggs or '[]')



class User(*_USER_EXTRAS, KantoUser, UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    # The account ID (id) is what everything links to. The username is just a sign-in name, so it can be changed
    username = db.Column(db.String(100), unique=True, nullable=False)
    full_name = db.Column(db.String(150))  # shown instead of the username where it's set
    email = db.Column(db.String(254), unique=True)  # optional, stored in lower case; also works as a sign-in name
    avatar = db.Column(db.String(30))  # a key of AVATARS; their initials if blank
    avatar_colour = db.Column(db.String(30))  # a key of AVATAR_COLOURS, the circle behind it
    password_hash = db.Column(db.String(200), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())  # False: can't sign in
    must_change_password = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=utcnow)
    # Two-step verification with an authenticator app (TOTP)
    mfa_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    totp_secret = db.Column(db.Text)  # encrypted (see encrypt_secret)
    mfa_pending_secret = db.Column(db.Text)  # encrypted; set during setup until a code confirms it
    mfa_last_step = db.Column(db.Integer)  # last accepted 30-second step, so a code can't be reused
    recovery_codes = db.Column(db.Text)  # JSON list of keyed hashes of unused recovery codes
    display_prefs = db.Column(db.Text)  # JSON: theme, text, font, motion, celebrations (kanto/static/js/display.js)
    easter_eggs = db.Column(db.Text)  # JSON list of easter eggs found, for profile badges
    hide_badges = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Part of the session ID; changing it signs this user out everywhere (password change, MFA reset, role change)
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    role_rows = db.relationship('UserRole', cascade='all, delete-orphan', lazy='selectin')


class UserRole(db.Model):
    """One role held by an account (see settings.ROLE_DEFS)."""
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    role = db.Column(db.String(30), primary_key=True)


class Passkey(db.Model):
    """A passkey (WebAuthn credential). The device asks for a fingerprint, face or PIN before using it,
    so signing in with one counts as two-step verification on its own."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    user = db.relationship('User', backref=db.backref('passkeys', order_by='Passkey.created_at',
                                                      cascade='all, delete-orphan'))
    credential_id = db.Column(db.String(1400), unique=True, nullable=False)  # base64url
    public_key = db.Column(db.LargeBinary, nullable=False)  # COSE-encoded; not secret
    sign_count = db.Column(db.Integer, nullable=False, default=0)
    transports = db.Column(db.Text)  # JSON list from the browser (usb, internal, hybrid…), passed back at sign-in
    synced = db.Column(db.Boolean)  # backed up to iCloud Keychain, Google Password Manager, etc.
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_used_at = db.Column(db.DateTime)

    @property
    def descriptor(self):
        transports = [AuthenticatorTransport(t) for t in json.loads(self.transports or '[]')]
        return PublicKeyCredentialDescriptor(id=base64url_to_bytes(self.credential_id), transports=transports or None)


class ActivityLog(*_LOG_EXTRAS, db.Model):
    """Append-only: names are copied in so entries still read correctly after renames."""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    username = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    action = db.Column(db.String(100), nullable=False)
    detail = db.Column(db.Text)
    # For actions done *to* a user account (e.g. an admin resetting someone's password)
    target_user_id = db.Column(db.Integer, index=True)
    target_username = db.Column(db.String(100))


class SignedOutSession(db.Model):
    """A session someone signed out of. The session lives in a signed cookie in the browser, so signing out
    can't delete it: a copy of the cookie (stolen, or a shared computer's) would still work until it expired.
    Its id is recorded here, and a cookie carrying it is refused. Rows go once the session would have ended anyway."""
    sid = db.Column(db.String(64), primary_key=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)


@login_manager.user_loader
def load_user(session_id):
    # A session that was signed out of: refused even though its cookie is still validly signed
    sid = session.get('sid')
    if sid and db.session.get(SignedOutSession, sid) is not None:
        return None
    # Session IDs are "<user id>:<session version>"; a stale version means the session was revoked
    user_id, _, version = (session_id or '').partition(':')
    user = db.session.get(User, int(user_id)) if user_id.isdigit() else None
    if user is None or not user.is_active or not version.isdigit() or int(version) != (user.session_version or 0):
        return None
    return user


if _extras is not None and hasattr(_extras, 'after_models'):
    _extras.after_models(User, ActivityLog)
