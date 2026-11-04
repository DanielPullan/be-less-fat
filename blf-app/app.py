"""Be Less Fat, built on Kanto (kanto/): sign-in, passkeys, two-step verification, users, roles, the activity log,
themes and celebrations come from there; food, weight and goals are here (models.py, pages.py, nutrition.py).

Run it:  uv run flask --app app run --port 5050      (then open http://127.0.0.1:5050)
"""
from kanto import app, db, prepare_database  # noqa: F401

import models  # noqa: F401,E402
import pages  # noqa: F401,E402
import old_data  # noqa: F401,E402  (flask --app app import-old-blf)

prepare_database()

if __name__ == '__main__':
    import os
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5050')),  # 5000 is taken by AirPlay on macOS
            debug=os.environ.get('FLASK_DEBUG', '').strip().lower() in ('1', 'true', 'yes'))
