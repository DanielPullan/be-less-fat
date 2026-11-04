import os
import re

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ['DATABASE_URL'] = 'sqlite://'  # in memory

from kanto import app as flask_app  # noqa: E402

flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
import app  # noqa: E402,F401  (your models and pages)
from kanto import db  # noqa: E402
from kanto.models import User  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

PASSWORD = 'correct-horse-battery'


@pytest.fixture
def kanto_app(tmp_path):
    flask_app.instance_path = str(tmp_path)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(kanto_app):
    return kanto_app.test_client()


@pytest.fixture
def make_user(kanto_app):
    def make(username='dan', roles=('member',), password=PASSWORD, **kwargs):
        user = User(username=username, password_hash=generate_password_hash(password), roles=set(roles), **kwargs)
        db.session.add(user)
        db.session.commit()
        return user
    return make


def sign_in(client, username='dan', password=PASSWORD):
    return client.post('/login', data={'username': username, 'password': password})


def give_two_step(user):
    """Turn on an authenticator app for USER without the browser, returning its secret."""
    import pyotp
    from kanto import encrypt_secret
    secret = pyotp.random_base32()
    user.totp_secret, user.mfa_enabled = encrypt_secret(secret), True
    db.session.commit()
    return secret


def sign_in_with_code(client, user, secret):
    import pyotp
    sign_in(client, user.username)
    user.mfa_last_step = None
    db.session.commit()
    return client.post('/login/verify', data={'code': pyotp.TOTP(secret).now()})


def flashes(html):
    return re.findall(r'data-flash="\w+"[^>]*>([^<]*)<', html)
