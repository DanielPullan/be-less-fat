// Small page behaviours, kept out of inline onclick/onchange attributes so the
// Content Security Policy can forbid inline event handlers.
document.addEventListener('DOMContentLoaded', function () {
    // Filter dropdowns that submit their form as soon as they change
    document.querySelectorAll('select[data-autosubmit]').forEach(function (select) {
        select.addEventListener('change', function () { select.form.submit(); });
    });

    // Print buttons
    document.querySelectorAll('[data-print]').forEach(function (button) {
        button.addEventListener('click', function () { window.print(); });
    });

});

// Forms and buttons that need a confirmation first
document.addEventListener('DOMContentLoaded', function () {
    // Buttons that need a confirmation first (data-confirm="message")
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!window.confirm(form.dataset.confirm)) e.preventDefault();
        });
    });
    document.querySelectorAll('button[data-confirm]').forEach(function (button) {
        button.addEventListener('click', function (e) {
            if (!window.confirm(button.dataset.confirm)) e.preventDefault();
        });
    });

    // Copy buttons: <button data-copy="#element-id"> copies that element's text (or each row's, for a list)
    document.querySelectorAll('[data-copy]').forEach(function (button) {
        button.addEventListener('click', async function () {
            const source = document.querySelector(button.dataset.copy);
            const status = document.querySelector(button.dataset.copyStatus || '#copy-status');
            const items = source.querySelectorAll('[data-copy-item]');
            const text = items.length ? [...items].map(function (el) { return el.textContent.trim(); }).join('\n') : source.textContent.trim();
            try { await navigator.clipboard.writeText(text); if (status) status.textContent = 'Copied.'; }
            catch (e) { if (status) status.textContent = 'Copying isn\'t allowed here; select the text and copy it instead.'; }
        });
    });
});

// Header drop-down menus: close when clicking elsewhere or pressing Escape
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('details[data-menu]').forEach(function (menu) {
        document.addEventListener('click', function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
        });
    });
});
