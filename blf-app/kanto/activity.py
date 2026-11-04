"""The activity log page: everything done in the app, filterable, and as a CSV. For admins and global admins."""
import io
from datetime import date, datetime, timedelta

import settings
from flask import Response, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from . import SafeCSVWriter, app, db, localtime, log_action
from .admin import file_slug, log_viewer_required
from .extras import ActivityExtras, load
from .models import ActivityLog, User



ACTIVITY_EXTRAS = load(getattr(settings, 'ACTIVITY_EXTRAS', None), ActivityExtras)


@app.template_global()
def activity_extras():
    return ACTIVITY_EXTRAS


ACTIVITY_COLUMNS = ['Time (UK)', 'User', 'Viewing as', 'Action', 'About user', *ACTIVITY_EXTRAS.csv_columns,
                    'Details', 'IP address']


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def activity_query():
    """Log entries matching the Activity page's filters, newest first, and the filters themselves."""
    f = {k: request.args.get(k, '').strip() for k in ('user', 'about', 'action', 'q', 'from', 'to',
                                                       *ACTIVITY_EXTRAS.filters)}
    query = ActivityLog.query
    # A name that's an account's current username also finds that account's entries under earlier usernames
    accounts = {u.username: u.id for u in User.query.filter(User.username.in_([f['user'], f['about']]))}
    if f['user']:  # their own entries, and anything they did while viewing as someone ("dan as steve")
        query = query.filter(or_(ActivityLog.username == f['user'], ActivityLog.username.like(f"{f['user']} as %"),
                                 ActivityLog.user_id == accounts.get(f['user'], -1)))
    if f['about']:
        query = query.filter(or_(ActivityLog.target_username == f['about'],
                                 ActivityLog.target_user_id == accounts.get(f['about'], -1)))
    if f['action']:
        query = query.filter(ActivityLog.action == f['action'])
    if f['q']:
        like = f"%{f['q']}%"
        query = query.filter(or_(ActivityLog.detail.ilike(like), ActivityLog.username.ilike(like),
                                 ActivityLog.target_username.ilike(like), *ACTIVITY_EXTRAS.search(like)))
    if day := parse_date(f['from']):
        query = query.filter(ActivityLog.timestamp >= datetime.combine(day, datetime.min.time()))
    if day := parse_date(f['to']):
        query = query.filter(ActivityLog.timestamp < datetime.combine(day + timedelta(days=1), datetime.min.time()))
    query = ACTIVITY_EXTRAS.filter(query, f)
    return query.order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc()), f


def split_viewer(username):
    """('dan', 'steve') for an entry recorded while dan was viewing as steve, else (username, None)."""
    actor, sep, viewed = (username or '').partition(' as ')
    return (actor, viewed) if sep else (username, None)


@app.template_filter('split_viewer')
def split_viewer_filter(username):
    return split_viewer(username)


@app.template_filter('dict_without')
def dict_without(d, key):
    return {k: v for k, v in d.items() if k != key}


@app.template_filter('dict_with')
def dict_with(d, key, value):
    return {**d, key: value}


@app.template_filter('link_args')
def link_args(args):
    """Query-string values to carry into a link with url_for. Names starting with _ are url_for's own settings
    (_scheme, _external, _anchor), so a crafted address could otherwise change where the link goes."""
    return {k: v for k, v in args.items() if not k.startswith('_')}


@app.route('/activity')
@login_required
@log_viewer_required
def activity():
    # Keep the address tidy: drop empty filters (the form sends every field)
    if any(v == '' for v in request.args.values()):
        return redirect(url_for('activity', **{k: v for k, v in request.args.items() if v and not k.startswith('_')}))
    query, filters = activity_query()
    page = query.paginate(per_page=50, error_out=False)
    usernames = sorted({split_viewer(u)[0] for (u,) in db.session.query(ActivityLog.username).distinct() if u},
                       key=str.lower)
    targets = [u for (u,) in db.session.query(ActivityLog.target_username).distinct()
               .order_by(ActivityLog.target_username) if u]
    actions = [a for (a,) in db.session.query(ActivityLog.action).distinct().order_by(ActivityLog.action) if a]
    return render_template('kanto/activity.html', page=page, usernames=usernames, targets=targets, actions=actions,
                           filters=filters, user_ids={u.username: u.id for u in User.query.all()},
                           **ACTIVITY_EXTRAS.context(filters))


@app.route('/activity.csv')
@login_required
@log_viewer_required
def activity_csv():
    """The Activity page's entries, with its filters, as a spreadsheet."""
    query, _ = activity_query()
    out = io.StringIO()
    writer = SafeCSVWriter(out)
    writer.writerow(ACTIVITY_COLUMNS)
    rows = query.limit(50000).all()
    for e in rows:
        actor, viewed = split_viewer(e.username)
        writer.writerow([localtime(e.timestamp), actor or '', viewed or '', e.action, e.target_username or '',
                         *ACTIVITY_EXTRAS.csv_values(e), e.detail or '', e.ip_address or ''])
    log_action('Activity log exported (CSV)', detail=f'{len(rows)} entr{"y" if len(rows) == 1 else "ies"}')
    db.session.commit()
    return Response('﻿' + out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{file_slug()}-activity-{date.today().isoformat()}.csv"'})
