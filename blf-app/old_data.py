"""Bring accounts, details, weigh-ins and food across from the Be Less Fat database used before Kanto
(blf_app/blf.sqlite3). Passwords carry over (same hashing); pins are dropped, as sign-in no longer uses them."""
import sqlite3

import click

from kanto import app, db, log_action
from kanto.models import User
from models import BodyDetails, FoodEntry, WeighIn


@app.cli.command('import-old-blf')
@click.argument('path', type=click.Path(exists=True, dir_okay=False))
@click.option('--admin', 'admins', multiple=True, help='A username to make an admin and global admin (repeatable).')
def import_old_blf(path, admins):
    """Copy everything from the old Be Less Fat SQLite database at PATH. Accounts already here are skipped."""
    old = sqlite3.connect(path)
    old.row_factory = sqlite3.Row
    tables = {r['name'] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'users' not in tables:
        raise click.ClickException(f'{path} has no users table: is it the old Be Less Fat database?')
    columns = {t: {r['name'] for r in old.execute(f'PRAGMA table_info({t})')} for t in ('users', 'weight', 'calories') if t in tables}
    get = lambda row, col, table='users': row[col] if col in columns.get(table, ()) else None
    users = weigh_ins = foods = skipped = 0
    for row in old.execute('SELECT * FROM users ORDER BY id'):
        if User.query.filter(db.func.lower(User.username) == row['username'].lower()).first():
            click.echo(f'  Skipped {row["username"]}: already here')
            skipped += 1
            continue
        roles = {'member'} | ({'admin', 'global_admin'} if row['username'] in admins else set())
        user = User(username=row['username'], password_hash=row['password_hash'], roles=roles)
        db.session.add(user)
        db.session.flush()
        if any(get(row, c) for c in ('height', 'goalweight', 'birthdate', 'sex', 'activity')):
            db.session.add(BodyDetails(user_id=user.id, height=get(row, 'height'), goalweight=get(row, 'goalweight'),
                                       birthdate=get(row, 'birthdate'), sex=get(row, 'sex'), activity=get(row, 'activity')))
        if 'weight' in tables:
            for w in old.execute('SELECT * FROM weight WHERE user_id = ? ORDER BY id', (row['id'],)):
                db.session.add(WeighIn(user_id=user.id, logdate=w['logdate'], weight=w['weight'],
                                       import_id=get(w, 'import_id', 'weight')))
                weigh_ins += 1
        if 'calories' in tables:
            for f in old.execute('SELECT * FROM calories WHERE user_id = ? ORDER BY id', (row['id'],)):
                db.session.add(FoodEntry(user_id=user.id, logdate=f['logdate'], food=f['food'], calories=f['calories'],
                                         meal=f['meal'], protein=get(f, 'protein', 'calories'),
                                         fibre=get(f, 'fibre', 'calories'), portion=get(f, 'portion', 'calories')))
                foods += 1
        log_action('User created (old Be Less Fat database)', user=user, detail='Roles: ' + ', '.join(user.role_labels))
        users += 1
    db.session.commit()
    click.echo(f'{users} account(s), {weigh_ins} weigh-in(s) and {foods} food entr{"y" if foods == 1 else "ies"} copied'
               + (f'; {skipped} account(s) skipped' if skipped else '') + '.')
    click.echo('Everyone signs in with their old username and password (no pin any more).')
