Be Less Fat (Flask app)
=======================

Track your weight and food, see your BMI and daily calories.

Running it
----------

Needs `uv <https://docs.astral.sh/uv/>`_. It installs the right Python and dependencies for you.

::

    cd blf-app
    uv run blf                                       # http://127.0.0.1:5050

If ``uv run blf`` says ``No module named 'blf_app'``, run ``uv run python -m blf_app`` instead (from the
``blf-app`` folder). It does the same thing, and doesn't depend on the ``.pth`` file in ``.venv`` that
some macOS setups skip.

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

Styles
------

The pages use Tailwind CSS, built into ``blf_app/static/css/app.css`` (no CDN). After changing classes in a
template, rebuild it (needs Node.js)::

    npx tailwindcss@3.4.17 -i blf_app/static/css/tailwind.src.css -o blf_app/static/css/app.css --minify

Dark and high-contrast themes live in ``blf_app/static/css/themes.css``. They remap Tailwind's light colour
classes, so if a template starts using a new colour class, add it there too.

Tests
-----

::

    uv run pytest
