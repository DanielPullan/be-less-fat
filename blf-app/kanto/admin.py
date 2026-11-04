"""User admin (the Users page): adding, changing and disabling accounts, roles, temporary passwords, resetting
two-step verification, unlocking, signing out everywhere, bulk changes from a CSV, viewing as a user (global admins),
and the themes and celebrations panel."""
import csv
import io
import json
import os
import re
import secrets
from datetime import date
from functools import wraps

from flask import Response, abort, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload
from werkzeug.security import generate_password_hash

import settings
from . import STAGING, SEASON_DATE, SafeCSVWriter, app, db, log_action, no_store
from .auth import (EMAIL_PATTERN, MIN_PASSWORD, USERNAME_PATTERN, clear_username_lockouts, email_error, rename_user,
                   start_session, throttle_clear, throttle_wait, username_error, username_ip_key, username_key,
                   username_lockouts)
from .display import (CELEBRATION_BUTTONS, CELEBRATION_ODDS_FILE, CELEBRATIONS, SEASON_DATE_FILE, THEME_LABELS,
                      celebration_odds, limited_themes, save_theme, season_date, season_date_shortcuts,
                      staging_season_date, themes_on)
from .models import PROTECTED_ROLES, ROLE_DEFS, ActivityLog, Throttle, User
from .extras import AccountFields, load
from .security import PROTECTED_NAME, confirm_first, needs_passkey_redirect, passkey_confirmed, view_as_refusal

SIGN_IN_ACTIONS = ['Logged in', 'Failed login', 'Failed verification code', 'Failed passkey sign-in',
                   'Sign-in blocked (too many attempts)', 'Sign-in refused (account disabled)']
PASSKEY_FOR_ROLES = f'Confirm it\'s you with a passkey before giving or removing {PROTECTED_NAME} or Global admin roles.'


ACCOUNT_FIELDS = load(getattr(settings, 'ACCOUNT_FIELDS', None), AccountFields)


@app.template_global()
def account_fields():
    return ACCOUNT_FIELDS


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.can_admin:
            abort(403)
        if not current_user.has_two_step:
            flash('User admin needs two-step verification on your own account. Set it up below first.', 'error')
            return redirect(url_for('profile') + '#security')
        return view(*args, **kwargs)
    return wrapped


def log_viewer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.can_view_log:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def active_admin_count(excluding=None):
    return sum(1 for u in User.query.filter_by(active=True).all() if 'admin' in u.roles and u != excluding)


def lock_state(user):
    """Seconds until each lockout on USER clears (only the ones currently in force)."""
    state = {}
    for record in username_lockouts(user.username):
        if wait := throttle_wait(record.key):
            label = 'Wrong passwords' if record.key == username_key(user.username) else \
                f'Wrong passwords from {record.key.rsplit("|", 1)[1]}'
            state[label] = wait
    if wait := throttle_wait(f'mfa:{user.id}'):
        state['Wrong codes'] = wait
    if wait := throttle_wait(f'password:{user.id}'):
        state['Wrong password re-entered'] = wait
    return state


def locked_users(users):
    """IDs of USERS with a lockout in force, from one query."""
    from . import utcnow
    keys = [r.key for r in Throttle.query.filter(Throttle.locked_until > utcnow())]
    return {u.id for u in users
            if any(k == username_key(u.username) or k.startswith(username_ip_key(u.username, ''))
                   or k in (f'mfa:{u.id}', f'password:{u.id}') for k in keys)}


def last_sign_in(user):
    entry = (ActivityLog.query.filter_by(user_id=user.id, action='Logged in')
             .order_by(ActivityLog.timestamp.desc()).first())
    return entry.timestamp if entry else None


def last_sign_ins():
    """{user id: last sign-in time} for everyone, from one query."""
    return dict(db.session.query(ActivityLog.user_id, db.func.max(ActivityLog.timestamp))
                .filter(ActivityLog.action == 'Logged in', ActivityLog.user_id.isnot(None))
                .group_by(ActivityLog.user_id).all())


def temporary_password():
    # Easy to read out or type: four groups of four, no look-alike characters
    alphabet = 'abcdefghjkmnpqrstuvwxyz23456789'
    return '-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def issue_temporary_password(user):
    password = temporary_password()
    user.password_hash = generate_password_hash(password)
    user.must_change_password = True
    user.end_other_sessions()
    clear_username_lockouts(user.username)
    throttle_clear(f'password:{user.id}')
    return password


def roles_from_form(user=None):
    """Roles ticked on a Users page form, checked against what the current admin may change.
    Returns (roles, error message or None)."""
    chosen = {r for r in request.form.getlist('roles') if r in ROLE_DEFS}
    before = user.roles if user else set()
    if not chosen and (other := ACCOUNT_FIELDS.roles_from_other_form(request.form, before)) is not None:
        chosen = set(other)
    if error := role_change_error(chosen, before):
        return before, error
    return chosen, None


def role_change_error(chosen, before=frozenset()):
    """Why the current admin can't change roles BEFORE to CHOSEN, or None."""
    if (chosen ^ before) & PROTECTED_ROLES and not current_user.has_protected_role:
        return f'Only someone with a {PROTECTED_NAME} role can give or remove {PROTECTED_NAME} roles.'
    if (chosen ^ before) & {'global_admin'} and 'global_admin' not in current_user.roles:
        return 'Only a global admin can give or remove the Global admin role.'
    if (chosen ^ before) & (PROTECTED_ROLES | {'global_admin'}) and not passkey_confirmed():
        return PASSKEY_FOR_ROLES
    if not chosen:
        return 'Give the account at least one role.'
    return None


def identity_changes(user, username, full_name, email):
    """Log lines for changing USER's username, full name or email."""
    changes = []
    if username != user.username:
        changes.append(f'Username changed: {user.username} → {username}')
    if (full_name or None) != user.full_name:
        changes.append(f'Name changed: {user.full_name or "(none)"} → {full_name or "(none)"}')
    if (email or None) != user.email:
        changes.append(f'Email changed: {user.email or "(none)"} → {email or "(none)"}')
    return changes


def set_identity(user, username, full_name, email):
    rename_user(user, username)
    user.full_name, user.email = full_name or None, email or None


def guard_account(user_id):
    """For confirm_first: the refusal guards_protected_account gives for this account, before asking."""
    return guards_protected_account(db.get_or_404(User, user_id))


def guards_protected_account(user):
    """An admin without a protected role can't change, reset the password of, or reset two-step verification for
    someone who has one: otherwise they could take over that account. Likewise for global admins.
    Returns a redirect to send instead, or None."""
    if user.has_protected_role and not current_user.has_protected_role:
        flash(f'{user.username} has a {PROTECTED_NAME} role, so only an admin who also has one can change '
              'their account, password or two-step verification.', 'error')
        return redirect(url_for('admin_user', user_id=user.id))
    if 'global_admin' in user.roles and 'global_admin' not in current_user.roles:
        flash(f'{user.username} is a global admin, so only another global admin can change '
              'their account, password or two-step verification.', 'error')
        return redirect(url_for('admin_user', user_id=user.id))
    if (user.has_protected_role or 'global_admin' in user.roles) and not passkey_confirmed():
        return needs_passkey_redirect(f'{user.username} has a {PROTECTED_NAME} or Global admin role. Confirm it\'s you '
                                      'with a passkey before changing their account, password or two-step verification.',
                                      url_for('admin_user', user_id=user.id))
    return None


# ---------------------------------------------------------------------------
# Viewing as a user
# ---------------------------------------------------------------------------

@app.route('/view-as')
@login_required
def view_as_list():
    """Global admins: pick someone to view the app as."""
    if 'global_admin' not in current_user.roles:
        abort(403)
    if not current_user.has_two_step:
        flash('Viewing as other users needs two-step verification on your own account. Set it up below first.', 'error')
        return redirect(url_for('profile') + '#security')
    if not passkey_confirmed():
        return needs_passkey_redirect('Viewing as other users needs you to confirm it\'s you with a passkey.',
                                      url_for('view_as_list'))
    search = request.args.get('q', '').strip()
    query = User.query.filter_by(active=True).order_by(db.func.lower(User.username))
    if search:
        query = query.filter(User.username.ilike(f'%{search}%'))
    rows = [{'user': u, 'refusal': view_as_refusal(current_user, u)} for u in query.all() if u != current_user]
    return render_template('kanto/view_as.html', rows=rows, search=search, **ACCOUNT_FIELDS.context())


@app.route('/view-as/<int:user_id>', methods=['POST'])
@login_required
def start_viewing_as(user_id):
    target = db.session.get(User, user_id)
    if refusal := view_as_refusal(current_user, target):
        flash(refusal, 'error')
        return redirect(url_for('view_as_list'))
    session['view_as'] = target.id
    session.pop('view_as_display', None)
    log_action('Started viewing as', target=target, detail=', '.join(target.role_labels))
    db.session.commit()
    flash(f'You\'re now viewing {settings.APP_NAME} as {target.username}. It\'s read-only; '
          'use Stop viewing in the purple bar to go back.', 'success')
    return redirect(url_for('home'))


@app.route('/view-as/stop', methods=['POST'])
@login_required
def stop_viewing_as():
    admin = g.pop('viewing_admin', None)
    target_id = session.pop('view_as', None)
    session.pop('view_as_display', None)
    if admin is not None:
        target = db.session.get(User, target_id) if target_id else None
        g._login_user = admin  # back to themselves for the rest of this request
        log_action('Stopped viewing as', user=admin, target=target)
        db.session.commit()
        flash(f'Stopped viewing as {target.username}.' if target else 'Stopped viewing as another user.', 'success')
    return redirect(url_for('view_as_list'))


# ---------------------------------------------------------------------------
# The Users page
# ---------------------------------------------------------------------------

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_users():
    if request.method == 'POST':
        # Create a user with a one-time temporary password
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()[:150]
        email = request.form.get('email', '').strip().lower()
        roles, error = roles_from_form()
        extra, extra_error = ACCOUNT_FIELDS.from_form(roles)
        if problem := username_error(username) or email_error(email):
            flash(problem, 'error')
        elif error == PASSKEY_FOR_ROLES:
            return needs_passkey_redirect(error, url_for('admin_users') + '#add-user')
        elif error or (error := extra_error):
            flash(error, 'error')
            return redirect(url_for('admin_users') + '#add-user')
        else:
            user = User(username=username, full_name=full_name or None, email=email or None, roles=roles, password_hash='')
            db.session.add(user)
            ACCOUNT_FIELDS.apply(user, extra)
            db.session.flush()
            password = issue_temporary_password(user)
            log_action('User created', target=user, detail=(f'Name: {full_name}; ' if full_name else '')
                       + (f'email: {email}; ' if email else '') + 'Roles: ' + ', '.join(user.role_labels)
                       + ACCOUNT_FIELDS.created_detail(extra))
            db.session.commit()
            return no_store(render_template('kanto/admin_password.html', user=user, password=password, created=True))

    search = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '')
    query = User.query.order_by(db.func.lower(User.username))
    if search:
        query = query.filter(db.or_(User.username.ilike(f'%{search}%'), User.full_name.ilike(f'%{search}%'),
                                    User.email.ilike(f'%{search}%')))
    users = [u for u in query.options(selectinload(User.passkeys)).all()
             if role_filter not in ROLE_DEFS or role_filter in u.roles]
    last, locked = last_sign_ins(), locked_users(users)
    rows = [{'user': u, 'last': last.get(u.id), 'locked': u.id in locked} for u in users]
    odds = celebration_odds()
    return render_template('kanto/admin_users.html', rows=rows, search=search, role_filter=role_filter,
                           season_shortcuts=season_date_shortcuts(), limited_themes=limited_themes(),
                           celebration_buttons=CELEBRATION_BUTTONS,
                           celebration_odds_rows=[(name, label, when, usual, odds[name])
                                                  for name, (label, when, usual) in CELEBRATIONS.items()],
                           my_theme=json.loads(current_user.display_prefs or '{}').get('theme'),
                           season_now=season_date(), season_set=staging_season_date(), **ACCOUNT_FIELDS.context())


# Users as a CSV, like Google Workspace's bulk upload: download a blank file or everyone, fill in or change rows,
# and upload it. Rows are matched to accounts by account_id (so usernames can be changed), or by username when it's
# blank; anything else is a new account. Existing accounts are changed to match their row. Columns left out of the
# file, and blank cells in the optional columns, change nothing. Rows left out of the file change nothing either.
USER_CSV_COLUMNS = ['account_id', 'username', 'full_name', 'email', *ROLE_DEFS, *ACCOUNT_FIELDS.csv_columns, 'active',
                    'first_password', 'reset_password', 'sign_out']
USER_CSV_INFO = ['two_step', 'last_sign_in']  # in the download for reference; ignored on upload
IMPORT_MAX_ROWS = 500
YES = {'yes', 'y', 'x', '1', 'true', '✓'}
NO = {'no', 'n', '0', 'false'}


def _username(user_id):
    user = db.session.get(User, user_id)
    return user.username if user else 'this user'


def file_slug():
    return re.sub(r'[^a-z0-9]+', '-', settings.APP_NAME.lower()).strip('-') or 'app'


def users_csv(users=()):
    """The users CSV: just the header for the blank file, or a row for each of USERS."""
    out = io.StringIO()
    writer = SafeCSVWriter(out)
    writer.writerow(USER_CSV_COLUMNS + USER_CSV_INFO)
    last = last_sign_ins() if users else {}
    for u in users:
        writer.writerow([u.id, u.username, u.full_name or '', u.email or '',
                         *('yes' if c in u.roles else '' for c in ROLE_DEFS), *ACCOUNT_FIELDS.csv_values(u),
                         'yes' if u.is_active else 'no', '', '', '',
                         'yes' if u.has_two_step else 'no',
                         last[u.id].strftime('%d/%m/%Y %H:%M') if u.id in last else ''])
    return out.getvalue()


def csv_download(text, filename):
    # BOM so Excel opens it as UTF-8
    return Response('﻿' + text, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.route('/admin/users/import-template.csv')
@login_required
@admin_required
def admin_users_import_template():
    return csv_download(users_csv(), f'{file_slug()}-users.csv')


@app.route('/admin/users.csv')
@login_required
@admin_required
def admin_users_csv():
    users = User.query.order_by(db.func.lower(User.username)).options(selectinload(User.passkeys)).all()
    log_action('Users exported (CSV)', detail=f'{len(users)} user{"s" if len(users) != 1 else ""}')
    db.session.commit()
    return no_store(csv_download(users_csv(users), f'{file_slug()}-users-{date.today().isoformat()}.csv'))


def sentence(message):
    """'Only someone with ...' → 'only someone with ...', for joining onto 'Row 3 (name): '."""
    return message[0].lower() + message[1:].rstrip('.')


def plan_import(file):
    """Read an uploaded users CSV and work out what it would do, without doing it.
    Returns (planned rows, problems, needs a passkey). Nothing should be applied if there are any problems."""
    try:
        text = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return [], ['The file isn\'t UTF-8 text. In Excel, save it as "CSV UTF-8".'], False
    reader = csv.DictReader(io.StringIO(text))
    # Headers may be role codes or role labels, in any case and order
    norm = lambda h: re.sub(r'[\s–-]+', '_', (h or '').strip().lower())
    names = {c: c for c in USER_CSV_COLUMNS + USER_CSV_INFO} | {norm(ROLE_DEFS[c].label): c for c in ROLE_DEFS} \
        | {'password': 'first_password', 'sign_out_everywhere': 'sign_out'}
    headers = {h: names.get(norm(h)) for h in reader.fieldnames or []}
    present = set(headers.values())
    if 'username' not in present:
        return [], ['There\'s no username column. Start from the blank CSV or the download of all users.'], False
    if unknown := [h for h, code in headers.items() if code is None and (h or '').strip()]:
        return [], [f'Unknown column{"s" if len(unknown) > 1 else ""}: {", ".join(unknown)}.'], False
    has_roles = bool(present & set(ROLE_DEFS))
    everyone = User.query.all()
    existing, by_id = {u.username.lower(): u for u in everyone}, {u.id: u for u in everyone}
    emails = {u.email: u for u in everyone if u.email}
    plans, problems, seen, seen_ids, seen_emails, needs_passkey = [], [], set(), set(), set(), False
    for n, raw in enumerate(reader, 2):
        row = {headers[k]: (v or '').strip() for k, v in raw.items() if k in headers and headers[k]}
        if not any(v for k, v in row.items() if k not in USER_CSV_INFO):
            continue
        if n - 1 > IMPORT_MAX_ROWS:
            return [], [f'Upload up to {IMPORT_MAX_ROWS} users at a time.'], False
        username, account_id = row.get('username', ''), row.get('account_id', '')
        error = None
        if account_id:
            user = by_id.get(int(account_id)) if account_id.isdigit() else None
            if user is None:
                error = f'no account with ID {account_id} (leave account_id blank for a new user)'
            elif user.id in seen_ids:
                error = f'account {account_id} is in the file twice'
        else:
            user = existing.get(username.lower())
        if user:
            seen_ids.add(user.id)
        full_name = row.get('full_name', '')[:150] if 'full_name' in present else (user.full_name or '' if user else '')
        email = row.get('email', '').lower() if 'email' in present else (user.email or '' if user else '')
        plan = {'username': username, 'user': user, 'full_name': full_name, 'email': email}
        flags = {}
        for col in ('active', 'reset_password', 'sign_out'):
            value = row.get(col, '').lower()
            flags[col] = True if value in YES or (col == 'active' and value == 'active') else \
                False if value in NO or (col == 'active' and value in ('disabled', 'suspended')) else None
            if value and flags[col] is None:
                error = f'{col} should be yes or no, not "{row[col]}"'
        roles = {c for c in ROLE_DEFS if row.get(c, '').lower() in YES} if has_roles else \
            (user.roles if user else set(settings.DEFAULT_ROLES))
        extra, extra_error = ACCOUNT_FIELDS.from_csv(row, present, user, roles)
        error = error or extra_error
        password = row.get('first_password', '')
        active = flags['active'] if flags['active'] is not None else (user.is_active if user else True)
        taken = existing.get(username.lower()) or emails.get(username.lower())
        email_taken = emails.get(email) or existing.get(email)
        if error:
            pass
        elif not USERNAME_PATTERN.fullmatch(username):
            error = 'usernames are 3–50 characters: letters, numbers, dots, dashes, underscores or @'
        elif username.lower() in seen:
            error = f'{username} is in the file twice'
        elif taken and taken != user:
            error = f'{username} is already used by another account'
        elif email and (len(email) > 254 or not EMAIL_PATTERN.fullmatch(email)):
            error = f'{email} doesn\'t look like an email address'
        elif email and ((email_taken and email_taken != user) or email in seen_emails or email in seen):
            error = f'{email} is already used by another account'
        elif password and len(password) < MIN_PASSWORD:
            error = f'a first password needs at least {MIN_PASSWORD} characters'
        elif password and flags['reset_password']:
            error = 'give a first_password or reset_password, not both'
        elif error := role_change_error(roles, user.roles if user else set()):
            needs_passkey |= error == PASSKEY_FOR_ROLES
            error = None if error == PASSKEY_FOR_ROLES else sentence(error)
        seen.add(username.lower())
        if email:
            seen_emails.add(email)
        plan |= {'roles': roles, 'extra': extra, 'active': active, 'password': password,
                 'reset': bool(flags['reset_password']), 'sign_out': bool(flags['sign_out'])}
        if user and not error:
            changes = account_changes(user, plan)
            plan['changes'] = changes
            if changes and user.has_protected_role and not current_user.has_protected_role:
                error = f'{username} has a {PROTECTED_NAME} role, so only an admin who also has one can change their account'
            elif changes and 'global_admin' in user.roles and 'global_admin' not in current_user.roles:
                error = f'{username} is a global admin, so only another global admin can change their account'
            elif user == current_user and (password or plan['reset']):
                error = 'change your own password from your profile'
            elif user == current_user and not ('admin' in roles and active):
                error = 'you can\'t remove your own admin role or disable your own account'
            elif user == current_user and (user.roles - roles) & PROTECTED_ROLES:
                error = f'you can\'t remove your own {PROTECTED_NAME} role'
            elif changes and (user.has_protected_role or 'global_admin' in user.roles) and not passkey_confirmed():
                needs_passkey = True
        if error:
            problems.append(f'Row {n} ({username or "no username"}): {error}.')
        elif not user or plan['changes']:
            plans.append(plan)
    if not problems:
        # There must always be an active admin left
        after = {p['user'].id: 'admin' in p['roles'] and p['active'] for p in plans if p['user']}
        if not any(after.get(u.id, u.can_admin) for u in existing.values()) and not \
                any('admin' in p['roles'] and p['active'] for p in plans if not p['user']):
            problems.append('This would leave no active admin. Keep at least one.')
        elif not plans and not seen:
            problems.append('The file has no users in it.')
    return ([] if problems else plans), problems, needs_passkey


def account_changes(user, plan):
    """What applying PLAN would change about an existing USER, as lines for the log."""
    changes = identity_changes(user, plan['username'], plan['full_name'], plan['email']) + \
        [f'Role added: {ROLE_DEFS[r].label}' for r in sorted(plan['roles'] - user.roles)] + \
        [f'Role removed: {ROLE_DEFS[r].label}' for r in sorted(user.roles - plan['roles'])] + \
        ACCOUNT_FIELDS.changes(user, plan['extra'])
    if plan['active'] != user.is_active:
        changes.append('Account ' + ('enabled' if plan['active'] else 'disabled'))
    if plan['password']:
        changes.append('First password set from the file')
    elif plan['reset']:
        changes.append('Temporary password issued')
    if plan['sign_out'] or plan['password'] or plan['reset']:
        changes.append('Signed out everywhere')
    return changes


@app.route('/admin/users/import', methods=['POST'])
@login_required
@admin_required
def admin_users_import():
    file = request.files.get('file')
    if not file or not file.filename:
        flash('Choose a CSV file to upload.', 'error')
        return redirect(url_for('admin_users') + '#import-users')
    plans, problems, needs_passkey = plan_import(file)
    if needs_passkey and not problems:
        return needs_passkey_redirect(f'The file changes {PROTECTED_NAME} or Global admin roles or accounts. Confirm it\'s you '
                                      'with a passkey, then upload it again.', url_for('admin_users') + '#import-users')
    if problems:
        return render_template('kanto/admin_import.html', problems=problems, created=[], updated=[])
    created, updated = [], []
    for p in plans:
        user, password = p['user'], None
        if user is None:
            user = User(username=p['username'], full_name=p['full_name'] or None, email=p['email'] or None,
                        roles=p['roles'], active=p['active'], password_hash='')
            db.session.add(user)
            ACCOUNT_FIELDS.apply(user, p['extra'])
            db.session.flush()
            if p['password']:
                user.password_hash, user.must_change_password = generate_password_hash(p['password']), True
            else:
                password = issue_temporary_password(user)
            log_action('User created', target=user, detail='From a CSV upload. Roles: ' + ', '.join(user.role_labels)
                       + ACCOUNT_FIELDS.created_detail(p['extra']) + ('' if user.is_active else '; disabled'))
            created.append({'user': user, 'password': password})
            continue
        less_access = (user.roles - p['roles']) or not p['active'] or ACCOUNT_FIELDS.less_access(user, p['extra'])
        set_identity(user, p['username'], p['full_name'], p['email'])
        user.set_roles(p['roles'])
        ACCOUNT_FIELDS.apply(user, p['extra'])
        user.active = p['active']
        if p['password']:
            user.password_hash, user.must_change_password = generate_password_hash(p['password']), True
            clear_username_lockouts(user.username)
            throttle_clear(f'password:{user.id}')
        elif p['reset']:
            password = issue_temporary_password(user)
        if less_access or p['sign_out'] or p['password'] or p['reset']:
            user.end_other_sessions()
            if user == current_user:
                start_session(current_user)  # keep this session
        log_action('User updated', target=user, detail='From a CSV upload:\n' + '\n'.join(p['changes']))
        updated.append({'user': user, 'password': password, 'changes': p['changes']})
    log_action('Users imported (CSV)', detail=f'{len(created)} created, {len(updated)} changed'
               + (': ' + ', '.join(x['user'].username for x in created + updated) if created or updated else ''))
    db.session.commit()
    return no_store(render_template('kanto/admin_import.html', problems=[], created=created, updated=updated))


@app.route('/admin/users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user(user_id):
    user = db.get_or_404(User, user_id)
    if request.method == 'POST':
        if blocked := guards_protected_account(user):
            return blocked
        roles, error = roles_from_form(user)
        extra, extra_error = ACCOUNT_FIELDS.from_form(roles, user)
        make_active = request.form.get('active') == 'on'
        username = request.form.get('username', user.username).strip()
        full_name = request.form.get('full_name', user.full_name or '').strip()[:150]
        email = request.form.get('email', user.email or '').strip().lower()
        # Guard rails: nobody locks themselves out, and there's always an admin left
        losing_admin = user.can_admin and not ('admin' in roles and make_active)
        if error == PASSKEY_FOR_ROLES:
            return needs_passkey_redirect(error, url_for('admin_user', user_id=user.id))
        if error or (error := extra_error or username_error(username, user) or email_error(email, user)):
            flash(error, 'error')
        elif user == current_user and losing_admin:
            flash('You can\'t remove your own admin role or disable your own account. Ask another admin.', 'error')
        elif losing_admin and active_admin_count(excluding=user) == 0:
            flash('This is the last admin. Make someone else an admin first.', 'error')
        elif user == current_user and (user.roles - roles) & PROTECTED_ROLES:
            flash(f'You can\'t remove your own {PROTECTED_NAME} role. Ask another admin who has one.', 'error')
        else:
            added_roles, removed_roles = roles - user.roles, user.roles - roles
            changes = identity_changes(user, username, full_name, email) + \
                [f'Role added: {ROLE_DEFS[r].label}' for r in sorted(added_roles)] + \
                [f'Role removed: {ROLE_DEFS[r].label}' for r in sorted(removed_roles)] + \
                ACCOUNT_FIELDS.changes(user, extra)
            if make_active != user.is_active:
                changes.append('Account ' + ('enabled' if make_active else 'disabled'))
            if changes:
                less_access = removed_roles or not make_active or ACCOUNT_FIELDS.less_access(user, extra)
                set_identity(user, username, full_name, email)
                user.set_roles(roles)
                ACCOUNT_FIELDS.apply(user, extra)
                user.active = make_active
                # Less access takes effect everywhere at once
                if less_access:
                    user.end_other_sessions()
                    if user == current_user:
                        start_session(current_user)
                log_action('User updated', target=user, detail='\n'.join(changes))
                db.session.commit()
                flash('User updated.', 'success')
        return redirect(url_for('admin_user', user_id=user.id))

    sign_ins = (ActivityLog.query.filter(ActivityLog.action.in_(SIGN_IN_ACTIONS))
                .filter(db.or_(ActivityLog.user_id == user.id, ActivityLog.username == user.username))
                .order_by(ActivityLog.timestamp.desc()).limit(25).all())
    page = (ActivityLog.query.filter(db.or_(ActivityLog.user_id == user.id, ActivityLog.target_user_id == user.id))
            .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc())
            .paginate(page=request.args.get('page', 1, type=int), per_page=50, error_out=False))
    return render_template('kanto/admin_user.html', user=user, locked=lock_state(user),
                           last=last_sign_in(user), sign_ins=sign_ins, page=page, **ACCOUNT_FIELDS.context())


@app.route('/admin/users/<int:user_id>/password', methods=['POST'])
@login_required
@admin_required
@confirm_first(lambda user_id: f'Reset {_username(user_id)}\'s password? They\'ll be signed out and need the '
               'temporary password you\'re given.', 'Yes, reset it', guard=guard_account)
def admin_reset_password(user_id):
    user = db.get_or_404(User, user_id)
    if blocked := guards_protected_account(user):
        return blocked
    if user == current_user:
        flash('Change your own password from your profile.', 'error')
        return redirect(url_for('admin_user', user_id=user.id))
    password = issue_temporary_password(user)
    log_action('Password reset by admin', target=user, detail='Temporary password issued; all sessions signed out')
    db.session.commit()
    return no_store(render_template('kanto/admin_password.html', user=user, password=password, created=False))


@app.route('/admin/users/<int:user_id>/mfa', methods=['POST'])
@login_required
@admin_required
@confirm_first(lambda user_id: f'Turn off two-step verification for {_username(user_id)}? Their authenticator app, '
               'recovery codes and passkeys stop working and they\'ll be signed out.', 'Yes, turn it off', guard=guard_account)
def admin_reset_mfa(user_id):
    user = db.get_or_404(User, user_id)
    if blocked := guards_protected_account(user):
        return blocked
    if user == current_user:
        flash('Manage your own two-step verification from your profile.', 'error')
    else:
        user.clear_mfa()
        user.remove_passkeys()
        user.end_other_sessions()
        throttle_clear(f'mfa:{user.id}')
        log_action('Two-step verification reset by admin', target=user,
                   detail='Authenticator app and passkeys removed; all sessions signed out')
        db.session.commit()
        flash(f'Two-step verification is off for {user.username}. They can set it up again from their profile.', 'success')
    return redirect(url_for('admin_user', user_id=user.id))


@app.route('/admin/users/<int:user_id>/unlock', methods=['POST'])
@login_required
@admin_required
def admin_unlock(user_id):
    user = db.get_or_404(User, user_id)
    # Unlocking lets password guessing carry on, so it's guarded like the account's password
    if blocked := guards_protected_account(user):
        return blocked
    clear_username_lockouts(user.username)
    throttle_clear(f'mfa:{user.id}')
    throttle_clear(f'password:{user.id}')
    log_action('Sign-in unlocked by admin', target=user)
    db.session.commit()
    flash(f'{user.username} can sign in again.', 'success')
    return redirect(url_for('admin_user', user_id=user.id))


@app.route('/admin/users/<int:user_id>/sign-out', methods=['POST'])
@login_required
@admin_required
@confirm_first(lambda user_id: f'Sign {_username(user_id)} out everywhere?', 'Yes, sign them out', guard=guard_account)
def admin_sign_out(user_id):
    user = db.get_or_404(User, user_id)
    user.end_other_sessions()
    log_action('Signed out everywhere by admin', target=user)
    if user == current_user:
        start_session(current_user)  # keep this session
    db.session.commit()
    flash(f'{user.username} has been signed out everywhere.', 'success')
    return redirect(url_for('admin_user', user_id=user.id))


# ---------------------------------------------------------------------------
# Themes and celebrations panel (on the Users page)
# ---------------------------------------------------------------------------

@app.route('/admin/try-theme', methods=['POST'])
@login_required
@admin_required
def try_theme():
    """Switch the admin's own theme to any limited theme, whoever and whenever it's normally for."""
    theme = request.form.get('theme')
    if theme not in THEME_LABELS:
        abort(400)
    save_theme(current_user, theme)
    db.session.commit()
    flash(f'Your theme is now {THEME_LABELS[theme]}, just for you. Choose another in the Aa menu to switch back.', 'success')
    return redirect(url_for('admin_users') + '#pretend-date')


@app.route('/admin/celebration-odds', methods=['POST'])
@login_required
@admin_required
def set_celebration_odds():
    """How often each celebration plays by itself, for everyone on the site: 1 in N, 0 for never."""
    if request.form.get('reset'):
        try:
            os.remove(CELEBRATION_ODDS_FILE)
        except FileNotFoundError:
            pass
        log_action('Celebration odds reset', detail='Back to the usual odds')
        db.session.commit()
        flash('Every celebration is back to its usual odds.', 'success')
        return redirect(url_for('admin_users') + '#pretend-date')
    odds = {}
    for name in CELEBRATIONS:
        value = request.form.get(f'odds_{name}', '').strip()
        if not value.isdigit() or int(value) > 1000:
            flash(f'{CELEBRATIONS[name][0]}: enter a whole number from 0 (never) to 1000.', 'error')
            return redirect(url_for('admin_users') + '#pretend-date')
        odds[name] = int(value)
    os.makedirs(app.instance_path, exist_ok=True)
    with open(CELEBRATION_ODDS_FILE, 'w') as f:
        json.dump(odds, f)
    changed = [f'{CELEBRATIONS[n][0]} 1 in {v}' if v else f'{CELEBRATIONS[n][0]} off'
               for n, v in odds.items() if v != CELEBRATIONS[n][2]]
    log_action('Celebration odds changed', detail=', '.join(changed) or 'All at the usual odds')
    db.session.commit()
    flash('Saved. The new odds apply to everyone from their next page.', 'success')
    return redirect(url_for('admin_users') + '#pretend-date')


@app.route('/admin/season-date', methods=['POST'])
@login_required
@admin_required
def set_season_date():
    """Set (or clear) the pretend date for the seasonal touches: on staging for everyone, otherwise just for the
    admin who sets it."""
    value = request.form.get('date', '').strip()
    who = 'Everyone now sees' if STAGING else 'You now see'
    if request.form.get('clear') or not value:
        if STAGING:
            try:
                os.remove(SEASON_DATE_FILE)
            except FileNotFoundError:
                pass
        session.pop('season_date', None)
        log_action('Pretend date cleared', detail='Seasonal touches follow the real date' + ('' if STAGING else ' (for this admin)'))
        flash('The seasonal touches follow the real date again' + (f' (or SEASON_DATE, {SEASON_DATE}).' if SEASON_DATE else '.'), 'success')
    else:
        try:
            day = date.fromisoformat(value)
        except ValueError:
            flash('That isn\'t a date.', 'error')
            return redirect(url_for('admin_users') + '#pretend-date')
        if STAGING:
            with open(SEASON_DATE_FILE, 'w') as f:
                f.write(day.isoformat())
        else:
            session['season_date'] = day.isoformat()
        log_action('Pretend date set', detail=f'Seasonal touches act as on {day.strftime("%d/%m/%Y")}' + ('' if STAGING else ' (for this admin)'))
        # Switch the admin who set it to that day's theme, so they see it straight away (others choose for themselves)
        offered = themes_on(day)
        message = f'{who} the seasonal touches for {day.strftime("%A %d %B %Y")}.'
        if offered:
            save_theme(current_user, offered[0])
            message += f' Your theme is now {THEME_LABELS[offered[0]]}' + ('; everyone else can choose it from the Aa menu.' if STAGING else '.')
        else:
            message += ' There\'s no theme for that day.'
        flash(message, 'success')
    db.session.commit()
    return redirect(url_for('admin_users') + '#pretend-date')
