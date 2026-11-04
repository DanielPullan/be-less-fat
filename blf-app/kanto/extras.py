"""Base classes for an app's own parts of the Users pages and the activity log. Subclass them (in a module of yours,
e.g. accounts.py) and name your class in settings.py: ACCOUNT_FIELDS = 'accounts:SchoolFields',
ACTIVITY_EXTRAS = 'accounts:AuditLogExtras'. Nothing here imports the rest of Kanto, so it's safe to import early."""
import importlib


def load(value, default):
    """settings.X as an object: an instance, a class, or 'module:Class' (made once Kanto's models exist)."""
    if not value:
        return default()
    if isinstance(value, str):
        module, _, name = value.partition(':')
        value = getattr(importlib.import_module(module), name)
    return value() if isinstance(value, type) else value


class AccountFields:
    """Your app's own fields on accounts, edited with the roles on the Users pages and in the users CSV
    (SecureMy.School: which schools a school login belongs to). Subclass this and name it in settings.py
    (ACCOUNT_FIELDS = 'accounts:SchoolFields'). Values are whatever your app likes (a list of schools, say).

    Templates: put your form fields in templates/_account_fields.html (inside the add and change forms, after the
    roles: `user` is set on the change form), table cells in _account_columns_head.html and _account_columns.html
    (one <th>/<td> each per `columns`, with `u` the row's user), CSV help in _account_csv_help.html (<li>s), and a short line about a new account in the CSV
    upload's results in _account_summary.html (`u`)."""
    columns = 0                 # extra table columns on the Users and View as pages
    csv_columns = []            # extra CSV columns, after the roles
    csv_blank_note = 'role columns'   # "In the ___, a blank cell means none"
    less_access_note = 'a role'       # "Removing ___ or disabling the account signs them out everywhere"

    def roles_from_other_form(self, form, before):
        """Roles from a form without role tick boxes (e.g. an older form your app still accepts), or None.
        BEFORE is the account's current roles (empty for a new account)."""
        return None

    def from_form(self, roles, user=None):
        """Values from the add (USER None) or change form for an account with ROLES: (values, error or None)."""
        return None, None

    def from_csv(self, row, present, user, roles):
        """Values from a CSV ROW (a dict by column; PRESENT is the set of columns in the file) for USER (None for a
        new account) with ROLES: (values, error or None). Keep the account's values when your columns are absent."""
        return None, None

    def csv_values(self, user):
        """USER's cells for csv_columns."""
        return ['' for _ in self.csv_columns]

    def changes(self, user, values):
        """Log lines for changing USER to VALUES (none: nothing changes)."""
        return []

    def less_access(self, user, values):
        """True if VALUES give USER less access, so their other sessions are signed out."""
        return False

    def apply(self, user, values):
        """Set VALUES on USER (a new account is already added to the session)."""

    def created_detail(self, values):
        """Added to the log when an account is created, e.g. '; schools: Oak Primary'."""
        return ''

    def context(self):
        """Extra template variables for the Users pages (e.g. every school to pick from)."""
        return {}


class ActivityExtras:
    """Your app's own parts of the activity log, for columns you've added to ActivityLog (SecureMy.School: the
    area, and which audit an entry is about). Subclass this and name it in settings.py
    (ACTIVITY_EXTRAS = 'accounts:AuditLogExtras').

    Templates: _activity_filters_top.html and _activity_filters.html go in the filter form (at the start, and before
    the search box), _activity_what.html under each entry's action, _activity_columns_head.html and
    _activity_columns.html are <th>/<td>s after it (one each per `columns`; `entry` is the row, also on a user's
    page), and _activity_intro.html replaces the line under the heading."""
    filters = ()                # extra query-string filters, e.g. ('area', 'audit_id'): in `filters` on the page
    columns = 0
    csv_columns = []            # extra CSV columns, after 'About user'
    search_hint = 'Details or username'
    good_actions = ('Logged in', 'User created')   # shown in green

    def filter(self, query, filters):
        """QUERY narrowed by your FILTERS (all of them, as strings; blank when not set)."""
        return query

    def search(self, like):
        """Extra conditions for the search box, any of which matches: e.g. [ActivityLog.audit_name.ilike(like)]."""
        return []

    def csv_values(self, entry):
        return ['' for _ in self.csv_columns]

    def context(self, filters):
        """Extra template variables for the activity page."""
        return {}
