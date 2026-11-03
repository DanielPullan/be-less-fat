// Display settings (theme, text size, font, motion, celebrations), saved in this browser.
// Adapted from SecureMy.School. Loaded in <head> without defer so the saved theme
// applies before the page is drawn.
(function () {
    const KEY = 'blf-display';
    const DEFAULTS = { theme: 'system', text: 'default', font: 'standard', motion: 'system', celebrations: 'on' };
    // Seasonal and occasion themes are only offered at their time of year (blf_app/seasons.py); a saved one that
    // isn't offered today falls back to Match my device
    const extra = document.querySelector('meta[name="blf-extra-themes"]');
    const THEMES = ['system', 'light', 'dark', 'contrast'].concat(extra ? extra.content.split(' ').filter(Boolean) : []);
    const FONT_URLS = {
        readable: 'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700&display=swap',
        fira: 'https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap',
    };
    const root = document.documentElement;
    const matches = function (q) { return !!(window.matchMedia && window.matchMedia(q).matches); };

    function load() {
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(KEY)); } catch (e) { /* private mode or bad data */ }
        const prefs = Object.assign({}, DEFAULTS, saved || {});
        if (THEMES.indexOf(prefs.theme) < 0) prefs.theme = DEFAULTS.theme;
        return prefs;
    }
    function save(prefs) {
        try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (e) { /* still applies for this page */ }
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
        root.dataset.motion = prefs.motion === 'reduce' || matches('(prefers-reduced-motion: reduce)') ? 'reduce' : 'system';
        root.dataset.celebrations = prefs.celebrations === 'off' ? 'off' : 'on';
        if (FONT_URLS[prefs.font] && !document.getElementById(prefs.font + '-font')) {
            const link = document.createElement('link');
            link.id = prefs.font + '-font';
            link.rel = 'stylesheet';
            link.href = FONT_URLS[prefs.font];
            document.head.appendChild(link);
        }
    }

    let prefs = load();
    apply(prefs);
    // For the easter eggs (konami.js): change one setting as if picked in the menu
    window.blfDisplay = {
        set: function (name, value) {
            prefs = Object.assign({}, prefs, { [name]: value });
            save(prefs);
            apply(prefs);
            document.querySelectorAll('[data-display-options] input[data-pref]').forEach(function (input) {
                input.checked = prefs[input.dataset.pref] === input.value;
            });
        },
    };

    // Follow the device when set to "Match my device"
    ['(prefers-color-scheme: dark)', '(prefers-contrast: more)', '(prefers-reduced-motion: reduce)'].forEach(function (q) {
        if (!window.matchMedia) return;
        const mq = window.matchMedia(q);
        const onChange = function () { apply(prefs); };
        if (mq.addEventListener) mq.addEventListener('change', onChange); else if (mq.addListener) mq.addListener(onChange);
    });

    document.addEventListener('DOMContentLoaded', function () {
        const inputs = function () { return document.querySelectorAll('[data-display-options] input[data-pref]'); };
        const sync = function () { inputs().forEach(function (input) { input.checked = prefs[input.dataset.pref] === input.value; }); };
        sync();
        inputs().forEach(function (input) {
            input.addEventListener('change', function () {
                prefs = Object.assign({}, prefs, { [input.dataset.pref]: input.value });
                save(prefs);
                apply(prefs);
                sync();
            });
        });
        const reset = document.querySelector('[data-display-reset]');
        if (reset) reset.addEventListener('click', function () {
            prefs = Object.assign({}, DEFAULTS);
            save(prefs);
            apply(prefs);
            sync();
        });
    });
})();
