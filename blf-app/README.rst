Be Less Fat (Flask app)
=======================

Track your weight and food, see your BMI and daily calories.

Running it
----------

Needs `uv <https://docs.astral.sh/uv/>`_. It installs the right Python and dependencies for you.

::

    cd blf-app
    uv run blf                                       # http://127.0.0.1:5050

Then go to ``/register`` to create an account, and ``/settings`` to add your height and goal weight.

Configuration (environment variables)
-------------------------------------

``BLF_SECRET_KEY``
    Signs the login session cookie. **Set this to a long random value anywhere other than your own machine.**
``BLF_DATABASE``
    Path to the SQLite database file (default ``blf_app/blf.sqlite3``). Tables are created automatically.
``BLF_PORT`` / ``BLF_HOST``
    Where ``uv run blf`` listens (default ``127.0.0.1:5050``; 5000 clashes with AirPlay on macOS).
``BLF_DEBUG``
    Set to ``1`` for Flask debug mode (auto-reload and error pages).

Tests
-----

::

    uv run pytest
