"""Command-line tools: flask --app app create-user, set-role, reset-mfa, copy-from-sqlite."""
import os

import click
from sqlalchemy import create_engine, func, select
from sqlalchemy import inspect as sa_inspect
from werkzeug.security import generate_password_hash

import settings
from . import USING_SQLITE, app, db, log_action
from .models import ROLE_DEFS, User


@app.cli.command('create-user')
@click.argument('username')
@click.option('--role', 'role_values', multiple=True, type=click.Choice(list(ROLE_DEFS)),
              help='A role to give (repeat for several), e.g. --role member --role admin. New users get '
                   'settings.DEFAULT_ROLES unless you say. For an existing user, replaces their roles.')
@click.password_option()
def create_user(username, password, role_values):
    """Create a login, or reset the password (and optionally roles) if USERNAME already exists."""
    user = User.query.filter_by(username=username).first()
    roles = set(role_values) if role_values else (user.roles if user else set(settings.DEFAULT_ROLES))
    if user:
        user.password_hash = generate_password_hash(password)
        user.end_other_sessions()
        log_action('Password reset (CLI)', user=user, detail='All sessions signed out')
        if roles != user.roles:
            log_action('Roles changed (CLI)', user=user, detail=', '.join(user.role_labels) + ' → '
                       + ', '.join(ROLE_DEFS[r].label for r in ROLE_DEFS if r in roles))
            user.set_roles(roles)
        click.echo(f'Password updated for {username} ({", ".join(user.role_labels)}).')
    else:
        user = User(username=username, password_hash=generate_password_hash(password), roles=roles)
        db.session.add(user)
        db.session.flush()
        log_action('User created (CLI)', user=user, detail='Roles: ' + ', '.join(user.role_labels))
        click.echo(f'User {username} created ({", ".join(user.role_labels)}).')
    db.session.commit()


@app.cli.command('set-role')
@click.argument('username')
@click.argument('role', type=click.Choice(list(ROLE_DEFS)))
@click.option('--off', is_flag=True, help='Remove the role instead.')
def set_role(username, role, off):
    """Give a user one role, or remove it with --off. Use it for the first admin or global admin: after that,
    they can give roles from the Users page."""
    user = User.query.filter_by(username=username).first()
    if user is None:
        raise click.ClickException(f'No user called {username}. Check the spelling (usernames are lower case), or '
                                   'make the account with create-user.')
    roles = user.roles - {role} if off else user.roles | {role}
    if not roles:
        raise click.ClickException(f'{username} would have no roles left. Give them another role first, '
                                   f'e.g. set-role {username} OTHER_ROLE.')
    user.set_roles(roles)
    if off:
        user.end_other_sessions()
    log_action(f'Role {"removed" if off else "added"} (CLI)', user=user, target=user, detail=ROLE_DEFS[role].label)
    db.session.commit()
    click.echo(f'{username} now has: {", ".join(user.role_labels)}.'
               + ('' if off or role != 'admin' or user.has_two_step else
                  ' They need two-step verification on before the Users page will open.'))


@app.cli.command('reset-mfa')
@click.argument('username', required=False)
@click.option('--all', 'everyone', is_flag=True, help='Reset everyone (needed after changing SECRET_KEY).')
def reset_mfa(username, everyone):
    """Turn off two-step verification for a user who has lost their phone and recovery codes.

    For one user this removes their authenticator app and passkeys. --all only resets authenticator apps
    (what changing SECRET_KEY breaks); passkeys don't depend on SECRET_KEY, so they're kept."""
    if everyone == bool(username):
        raise click.ClickException('Give a USERNAME, or --all for everyone: e.g. reset-mfa dan.')
    users = User.query.all() if everyone else User.query.filter_by(username=username).all()
    if not users:
        raise click.ClickException(f'No user called {username}. Check the spelling (usernames are lower case).')
    for user in users:
        if user.mfa_enabled or user.totp_secret or user.mfa_pending_secret or (user.passkeys and not everyone):
            user.clear_mfa()
            if not everyone:
                user.remove_passkeys()
            user.end_other_sessions()
            log_action('Two-step verification reset (CLI)', user=user, detail='All sessions signed out')
    db.session.commit()
    click.echo(f'Two-step verification is off for {"everyone" if everyone else username}. '
               'They can set it up again from their profile.')


@app.cli.command('copy-from-sqlite')
@click.argument('sqlite_path', type=click.Path(exists=True, dir_okay=False))
def copy_from_sqlite(sqlite_path):
    """One-off move to PostgreSQL: copy every row from an SQLite database into this app's empty PostgreSQL
    database (DATABASE_URL), keeping every id. The SQLite file isn't changed. Run `flask db upgrade` on both first."""
    if USING_SQLITE:
        raise click.ClickException('Set DATABASE_URL to the PostgreSQL database to copy into first, e.g. in .env: '
                                   'DATABASE_URL=postgresql://user:password@localhost/myapp')
    tables = db.metadata.sorted_tables  # parents before children, so foreign keys are satisfied
    with db.engine.connect() as conn:
        filled = [t.name for t in tables if conn.execute(select(func.count()).select_from(t)).scalar()]
    if filled:
        raise click.ClickException('The PostgreSQL database already has data in: ' + ', '.join(filled)
                                   + '. This only copies into an empty database: make a new one (createdb) and run '
                                     '`flask db upgrade` on it, then this again.')
    source = create_engine(f'sqlite:///{os.path.abspath(sqlite_path)}')
    inspector = sa_inspect(source)
    for t in tables:
        have = {c['name'] for c in inspector.get_columns(t.name)} if inspector.has_table(t.name) else set()
        if missing := {c.name for c in t.columns} - have:
            raise click.ClickException(f'{t.name} in the SQLite database is missing {", ".join(sorted(missing))}. '
                                       'Run `flask db upgrade` on it first.')
    counts = {}
    with source.connect() as src, db.engine.begin() as dest:  # one transaction: all or nothing
        for t in tables:
            rows = [dict(r) for r in src.execute(select(t)).mappings()]
            for row in rows:  # SQLite never enforced text lengths; PostgreSQL does
                for c in t.columns:
                    limit = getattr(c.type, 'length', None)
                    if limit and isinstance(row.get(c.name), str) and len(row[c.name]) > limit:
                        row[c.name] = row[c.name][:limit]
            for i in range(0, len(rows), 500):
                dest.execute(t.insert(), rows[i:i + 500])
            counts[t.name] = len(rows)
        # New rows carry on from the highest copied id
        for t in tables:
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].name == 'id' and isinstance(pk[0].type, db.Integer):
                dest.execute(db.text(f"""SELECT setval(pg_get_serial_sequence('"{t.name}"', 'id'),
                                        COALESCE((SELECT MAX(id) FROM "{t.name}"), 1),
                                        (SELECT MAX(id) FROM "{t.name}") IS NOT NULL)"""))
    for name, n in counts.items():
        click.echo(f'  {name:<20} {n}')
    click.echo(f'Copied {sum(counts.values())} rows from {sqlite_path}.')
