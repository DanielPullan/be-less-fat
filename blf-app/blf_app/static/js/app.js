// Menus (<details data-menu> and the display menu): close when clicking elsewhere or pressing Escape.
document.addEventListener('DOMContentLoaded', function () {
    const menus = function () { return document.querySelectorAll('details[data-menu]'); };
    document.addEventListener('click', function (e) {
        menus().forEach(function (menu) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        menus().forEach(function (menu) {
            if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
        });
    });
    // Buttons that ask first: <button data-confirm="Delete this?">
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
        el.addEventListener('click', function (e) { if (!window.confirm(el.dataset.confirm)) e.preventDefault(); });
    });
});
