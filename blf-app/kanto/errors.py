"""Error pages that say what happened and what to do about it, rather than a bare "403 Forbidden".

A view can give the reason and the fix for its own refusal, which the page shows instead of the general one:

    abort(403, description='Only coordinators can set tasks. Ask a coordinator to set it for you.')

For a refusal the page also names who can help (the app's admins), and for a fault on the server it gives a
reference to quote, which is in the app's log next to what went wrong. Requests that expect JSON (passkeys and
other scripts) get {"error": "..."} instead of a page.
"""
import secrets

from flask import render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from markupsafe import escape
from werkzeug.exceptions import HTTPException

from . import app, db, local_referrer, localtime, utcnow
from .models import User

# code -> (heading, what happened, what to do)
GENERAL = {
    400: ('That didn\'t work', 'The page sent something the site didn\'t expect, perhaps because it was open from an '
          'older version of the site.', 'Go back, reload the page, and try again.'),
    403: ('You can\'t do that', 'Your account doesn\'t have the role this needs.',
          'If you need to, ask an admin to change your roles.'),
    404: ('Not found', 'There\'s nothing at this address. It may have been deleted, the link may be mistyped, or it '
          'may belong to something your account can\'t see.',
          'Check the link, or ask whoever sent it. Your home page has everything you can see.'),
    405: ('That didn\'t work', 'That address can\'t be used like that, e.g. a form\'s address opened as a page.',
          'Go back to the page the form is on and use it from there.'),
    429: ('Too many tries', 'There have been too many attempts in a short time.', 'Wait a few minutes, then try again.'),
    500: ('Something went wrong on our side', 'The site hit a problem it couldn\'t handle. It isn\'t anything you did.',
          'Try again in a minute. If it keeps happening, tell an admin what you were doing, and the reference below.'),
}
CSRF = ('This page had expired', 'For safety, every form carries a check that lasts as long as your sign-in. This '
        'one didn\'t match: perhaps you signed out and in again, or the page was open from before.',
        'Go back, reload the page, and send it again. You may need to type what you entered again.')


def admins():
    """The people who can sort out a refusal: active admins, as (name, email or None)."""
    try:
        return [(u.display_name, u.email) for u in User.query.order_by(User.username).all() if u.can_admin][:5]
    except Exception:  # the database itself may be what's broken
        db.session.rollback()
        return []


def wants_json():
    return request.is_json or request.accept_mimetypes.best == 'application/json'


def error_page(code, heading, why, fix, reference=None):
    if wants_json():
        return {'error': f'{why} {fix}'.strip()}, code
    helpers = admins() if code in (403, 500) else []
    try:
        return render_template('kanto/error.html', code=code, heading=heading, why=why, fix=fix, reference=reference,
                               helpers=[h for h in helpers if not (current_user.is_authenticated and
                                                                   h[0] == current_user.display_name)],
                               when=localtime(utcnow()), back=local_referrer()), code
    except Exception:  # e.g. the database is down and the page's header needs it: a plain page instead
        app.logger.exception('The error page itself failed')
        return (f'<!doctype html><title>{escape(heading)}</title><h1>{escape(heading)}</h1><p>{escape(why)}</p>'
                f'<p>{escape(fix)}</p>' + (f'<p>Reference: {reference}</p>' if reference else '')), code


@app.errorhandler(HTTPException)
def http_error(e):
    if e.code in (401, 413) or e.code < 400:
        return e  # sign-in and big uploads are handled elsewhere (Flask-Login, security.too_large)
    heading, why, fix = GENERAL.get(e.code, GENERAL[400] if e.code < 500 else GENERAL[500])
    custom = e.description if e.description and e.description != type(e).description else None
    if custom:  # the view's own reason, which includes its fix
        why, fix = custom, ''
    return error_page(e.code, heading, why, fix)


@app.errorhandler(CSRFError)
def csrf_error(e):
    return error_page(400, *CSRF)


@app.errorhandler(Exception)
def server_error(e):
    if isinstance(e, HTTPException):
        return http_error(e)
    if app.debug or app.testing:
        raise e  # the debugger, or the test, shows the real error
    reference = secrets.token_hex(3).upper()
    app.logger.exception(f'Unhandled error, reference {reference}, on {request.method} {request.path}')
    try:
        db.session.rollback()
    except Exception:
        pass
    return error_page(500, *GENERAL[500], reference=reference)
