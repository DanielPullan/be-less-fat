Be Less Fat (Flask app)
=======================

Track your weight and food, see your BMI and daily calories.

Running it
----------

::

    cd blf-app
    poetry install
    poetry run flask --app blf_app.app run          # http://127.0.0.1:5000

Then go to ``/register`` to create an account, and ``/settings`` to add your height and goal weight.

Configuration (environment variables)
-------------------------------------

``BLF_SECRET_KEY``
    Signs the login session cookie. **Set this to a long random value anywhere other than your own machine.**
``BLF_DATABASE``
    Path to the SQLite database file (default ``blf_app/blf.sqlite3``). Tables are created automatically.
``BLF_DEBUG``
    Set to ``1`` to enable Flask debug mode when running ``python app.py``.

Tests
-----

::

    poetry run pytest
