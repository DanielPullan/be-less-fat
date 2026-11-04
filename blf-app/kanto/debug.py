"""The debug menu: press ? anywhere outside a text box (kanto/static/js/debug.js). Who you are (and who you're
viewing as), who's been active, the server's load and memory, the database, and how long recent requests took.
Admins and global admins can open it; on staging anyone signed in can."""
import os
import socket
import sys
import threading
import time
from collections import deque
from datetime import timedelta

from flask import abort, g, jsonify, request, session
from flask_login import current_user, login_required

from . import SESSION_MAX_HOURS, STAGING, app, db, utcnow
from .models import User

# Each gunicorn worker keeps its own figures, so the request numbers are for the worker that answered.
_debug_started = time.time()
_debug_lock = threading.Lock()
_debug_requests = deque(maxlen=512)  # (finished at, milliseconds, endpoint, status)
_debug_total = 0
_debug_seen = {}  # account ID → last request time


def start_request_timer():
    g.request_started = time.perf_counter()


app.before_request_funcs.setdefault(None, []).insert(0, start_request_timer)  # first, so the timing covers the rest


@app.after_request
def record_request_time(response):
    global _debug_total
    started = g.get('request_started')
    if started is None:
        return response
    ms = (time.perf_counter() - started) * 1000
    # How long the server took, for the debug menu's page timings (the browser reads it from the navigation entry)
    response.headers['Server-Timing'] = f'app;dur={ms:.1f}'
    if request.endpoint not in ('static', 'kanto.static', 'favicon', 'debug_info'):
        who = g.get('viewing_admin') or (current_user if current_user.is_authenticated else None)
        with _debug_lock:
            _debug_requests.append((time.time(), ms, request.endpoint or '(not found)', response.status_code))
            _debug_total += 1
            if who is not None:
                _debug_seen[who.id] = time.time()
    return response


def can_debug():
    if not current_user.is_authenticated:
        return False
    who = g.get('viewing_admin') or current_user
    return who.is_active and (who.can_view_log or STAGING)


@app.context_processor
def inject_can_debug():
    return {'can_debug': can_debug}


def _ago(t):
    d = time.time() - t
    if t <= 0:
        return 'unknown'
    if d < 60:
        return 'just now'
    if d < 3600:
        return f'{int(d // 60)} min ago'
    if d < 48 * 3600:
        return f'{int(d // 3600)}h {int(d % 3600 // 60)}m ago'
    return f'{int(d // 86400)} days ago'


def _proc_field(path, key):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith(key):
                    return float(line.split()[1])
    except OSError:
        pass
    return 0


def _debug_person(user, me):
    out = {'account_id': user.id, 'username': user.username, 'name': user.display_name,
           'roles': user.role_labels, 'two_step': user.has_two_step}
    if me:
        out['signed_in'] = _ago(session.get('login_at', 0))
        out['passkey_confirmed'] = bool(session.get('passkey_ok'))
    return out


@app.route('/debug.json')
@login_required
def debug_info():
    if not can_debug():
        abort(404)
    admin = g.get('viewing_admin')
    now = time.time()
    with _debug_lock:
        for uid, t in list(_debug_seen.items()):
            if now - t > SESSION_MAX_HOURS * 3600:
                del _debug_seen[uid]
        recent_ids = {uid: t for uid, t in _debug_seen.items() if now - t <= 15 * 60}
        samples, total = list(_debug_requests), _debug_total
    recent = sorted(({'name': u.display_name, 'username': u.username, 'ago': _ago(recent_ids[u.id]),
                      'at': int(recent_ids[u.id])}
                     for u in User.query.filter(User.id.in_(recent_ids)).all()) if recent_ids else [],
                    key=lambda p: -p['at'])
    signed_in = db.session.execute(db.text(
        "SELECT count(DISTINCT user_id) FROM activity_log WHERE action = 'Logged in' AND timestamp > :since"),
        {'since': utcnow() - timedelta(hours=SESSION_MAX_HOURS)}).scalar()

    server = {'host': socket.gethostname(), 'cpus': os.cpu_count(), 'staging': STAGING, 'up': _ago(_debug_started),
              'runtime': f'Python {sys.version.split()[0]}, worker {os.getpid()}, {threading.active_count()} threads'}
    try:
        with open('/proc/loadavg') as f:
            server['load'] = [float(x) for x in f.read().split()[:3]]
    except OSError:
        pass
    if rss := _proc_field('/proc/self/status', 'VmRSS:'):
        server['process_mb'] = round(rss / 1024, 1)
    else:  # not Linux: the peak, which is what this platform offers
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        server['process_mb'] = round(peak / (1 << 20 if sys.platform == 'darwin' else 1024), 1)
    if total_kb := _proc_field('/proc/meminfo', 'MemTotal:'):
        server['memory_total_mb'] = round(total_kb / 1024, 1)
        server['memory_available_mb'] = round(_proc_field('/proc/meminfo', 'MemAvailable:') / 1024, 1)
        server['swap_used_mb'] = round((_proc_field('/proc/meminfo', 'SwapTotal:')
                                        - _proc_field('/proc/meminfo', 'SwapFree:')) / 1024, 1)

    started = time.perf_counter()
    database = {}
    try:
        size = db.session.execute(db.text('SELECT pg_database_size(current_database())')).scalar()
        database['size_mb'] = round(size / (1 << 20), 1)
    except Exception:
        db.session.rollback()
    database['query_ms'] = round((time.perf_counter() - started) * 1000, 1)
    pool = db.engine.pool
    if hasattr(pool, 'checkedout'):
        database.update(connections_in_use=pool.checkedout(), connections_idle=pool.checkedin(),
                        connections_max=pool.size() + pool._max_overflow)

    durations = sorted(s[1] for s in samples)
    pick = lambda p: round(durations[int(p * (len(durations) - 1) + 0.5)], 1) if durations else 0
    last_minute = sum(1 for s in samples if now - s[0] <= 60)
    by_page = {}
    for _, ms, endpoint, _ in samples:
        n, t = by_page.get(endpoint, (0, 0))
        by_page[endpoint] = (n + 1, t + ms)
    slowest = sorted(({'page': e, 'avg_ms': round(t / n, 1), 'count': n} for e, (n, t) in by_page.items()),
                     key=lambda p: -p['avg_ms'])[:5]
    requests_info = {'since_start': total, 'sampled': len(samples), 'last_minute': last_minute,
                     'per_second': round(last_minute / 60, 1), 'errors': sum(1 for s in samples if s[3] >= 500),
                     'median_ms': pick(0.5), 'p95_ms': pick(0.95), 'max_ms': pick(1), 'slowest_pages': slowest,
                     'scope': 'this worker'}

    response = jsonify({
        'you': _debug_person(admin or current_user, True),
        'viewing_as': _debug_person(current_user, False) if admin else None,
        'active': {'last_15_minutes': recent, 'signed_in_within_session_limit': signed_in,
                   'session_limit_hours': SESSION_MAX_HOURS, 'tracking_since': _ago(_debug_started)},
        'server': server, 'database': database, 'requests': requests_info,
    })
    response.headers['Cache-Control'] = 'no-store'
    return response
