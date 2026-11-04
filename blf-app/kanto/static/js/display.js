// Display settings (theme, text size, font, motion, celebrations).
// Signed in: saved to the account (and mirrored in this browser so pages draw in the right theme
// straight away). Signed out: saved in this browser only.
// Loaded in <head> without defer so the saved theme applies before the page is drawn.
(function () {
    const KEY = 'kanto-display';
    const metaContent = function (name) { const el = document.querySelector('meta[name="' + name + '"]'); return el ? el.content : null; };
    // The app's extra settings (settings.EXTRA_DISPLAY), e.g. Simple or Full detail view: {name: default}. They're drawn
    // by the server, so changing one reloads the page, and they belong to the account: never stored in this browser.
    let EXTRA = {};
    try { EXTRA = JSON.parse(metaContent('kanto-extra-display') || '{}'); } catch (e) { /* none */ }
    const DEFAULTS = Object.assign({ theme: 'system', text: 'default', font: 'standard', motion: 'system', celebrations: 'on' }, EXTRA);
    function withoutExtra(p) { const copy = Object.assign({}, p); Object.keys(EXTRA).forEach(function (k) { delete copy[k]; }); return copy; }
    const FONT_URLS = {
        readable: 'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700&display=swap',
        fira: 'https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap',
    };
    const root = document.documentElement;
    const matches = function (q) { return !!(window.matchMedia && window.matchMedia(q).matches); };

    const meta = function (name) { const el = document.querySelector('meta[name="' + name + '"]'); return el ? el.content : null; };
    const account = meta('kanto-account-display');  // null when signed out, '' when signed in with nothing saved yet
    // Themes offered now (seasonal ones only at their time of year): a saved one that isn't falls back to Match my device
    const THEMES = ['system', 'light', 'dark', 'contrast'].concat((meta('kanto-extra-themes') || '').split(' ').filter(Boolean));

    function local() {
        try { const saved = JSON.parse(localStorage.getItem(KEY)); return saved ? withoutExtra(saved) : null; } catch (e) { return null; }
    }
    function load() {
        let saved = local();
        if (account) {
            try { saved = JSON.parse(account); } catch (e) { /* fall back to this browser's copy */ }
        }
        const prefs = Object.assign({}, DEFAULTS, saved || {});
        if (THEMES.indexOf(prefs.theme) < 0) prefs.theme = DEFAULTS.theme;
        return prefs;
    }
    function saveToAccount(prefs) {
        if (account === null) return Promise.resolve();
        return fetch('/profile/display', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': meta('csrf-token') || '' },
            body: JSON.stringify(prefs),
            credentials: 'same-origin',
        }).catch(function () { /* offline: this browser still has them */ });
    }
    function save(prefs) {
        try { localStorage.setItem(KEY, JSON.stringify(withoutExtra(prefs))); } catch (e) { /* private mode: still applies for this page */ }
        return saveToAccount(prefs);
    }

    function apply(prefs) {
        let theme = prefs.theme;
        if (theme === 'system') {
            theme = matches('(prefers-contrast: more)') ? 'contrast'
                  : matches('(prefers-color-scheme: dark)') ? 'dark' : 'light';
        }
        root.dataset.theme = theme;
        root.dataset.text = prefs.text;
        root.dataset.font = prefs.font;
        root.dataset.celebrations = prefs.celebrations === 'off' ? 'off' : 'on';
        Object.keys(EXTRA).forEach(function (k) { root.dataset[k] = prefs[k]; });
        root.dataset.motion = prefs.motion === 'reduce' || matches('(prefers-reduced-motion: reduce)') ? 'reduce' : 'system';
        if (FONT_URLS[prefs.font] && !document.getElementById(prefs.font + '-font')) {
            const link = document.createElement('link');
            link.id = prefs.font + '-font';
            link.rel = 'stylesheet';
            link.href = FONT_URLS[prefs.font];
            document.head.appendChild(link);
        }
    }

    const hadLocal = local() !== null;
    let prefs = load();
    apply(prefs);
    try { localStorage.setItem(KEY, JSON.stringify(withoutExtra(prefs))); } catch (e) {}
    // First sign-in after choosing settings on this device: adopt them for the account
    if (account === '' && hadLocal) saveToAccount(withoutExtra(prefs));

    // Follow the device when set to System
    ['(prefers-color-scheme: dark)', '(prefers-contrast: more)', '(prefers-reduced-motion: reduce)'].forEach(function (q) {
        if (!window.matchMedia) return;
        const mq = window.matchMedia(q);
        const onChange = function () { apply(prefs); };
        if (mq.addEventListener) mq.addEventListener('change', onChange); else if (mq.addListener) mq.addListener(onChange);
    });

    // Wire up every set of options (the header's Display menu and the profile page) and keep them in step
    document.addEventListener('DOMContentLoaded', function () {
        const inputs = function () { return document.querySelectorAll('[data-display-options] input[data-pref]'); };
        const sync = function () { inputs().forEach(function (input) { input.checked = prefs[input.dataset.pref] === input.value; }); };
        sync();
        inputs().forEach(function (input) {
            input.addEventListener('change', function () {
                prefs = Object.assign({}, prefs, { [input.dataset.pref]: input.value });
                const saved = save(prefs);
                apply(prefs);
                sync();
                if (input.dataset.pref in EXTRA) saved.finally(function () { window.location.reload(); });
            });
        });
        const menu = document.getElementById('display-menu');
        if (!menu) return;
        const reset = menu.querySelector('[data-display-reset]');
        if (reset) reset.addEventListener('click', function () {
            const extraChanged = Object.keys(EXTRA).some(function (k) { return prefs[k] !== DEFAULTS[k]; });
            prefs = Object.assign({}, DEFAULTS);
            const saved = save(prefs);
            apply(prefs);
            sync();
            if (extraChanged) saved.finally(function () { window.location.reload(); });
        });
        // Close when clicking elsewhere or pressing Escape
        document.addEventListener('click', function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
        });
    });
})();
