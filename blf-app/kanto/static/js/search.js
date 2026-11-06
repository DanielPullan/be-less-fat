// The header's search box (kanto/search.py): open with the search button, "/" or Ctrl+K (Cmd+K on a Mac). Results
// come from the app's /search.json as you type, grouped, and only ever include what you can open. ↑ ↓ move, Enter
// opens. From SecureMy.School's search.
(function () {
    const dialog = document.getElementById('search-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;  // very old browsers: the button opens /search
    const input = dialog.querySelector('[data-search-input]');
    const list = dialog.querySelector('[data-search-results]');
    const hint = dialog.querySelector('[data-search-hint]');
    const hintText = hint.innerHTML;
    let options = [];
    let active = -1;
    let timer = null;
    let controller = null;
    const jsonUrl = dialog.dataset.searchUrl || '/search.json';
    const pageUrl = dialog.dataset.searchPage || '/search';

    function open() {
        if (dialog.open) return;
        dialog.showModal();
        input.focus();
        input.select();
    }

    document.querySelectorAll('[data-search-open]').forEach(function (button) {
        button.addEventListener('click', function (e) { e.preventDefault(); open(); });
    });
    document.addEventListener('keydown', function (e) {
        const typing = e.target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);
        if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) { e.preventDefault(); open(); }
        else if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); open(); }
    });
    // Clicking the dimmed background closes it
    dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });

    function setActive(index) {
        options.forEach(function (o, i) {
            o.setAttribute('aria-selected', i === index ? 'true' : 'false');
            o.classList.toggle('bg-slate-100', i === index);
        });
        active = index;
        if (index >= 0) {
            input.setAttribute('aria-activedescendant', options[index].id);
            options[index].scrollIntoView({ block: 'nearest' });
        } else {
            input.removeAttribute('aria-activedescendant');
        }
    }

    function render(data) {
        list.textContent = '';
        options = [];
        active = -1;
        input.removeAttribute('aria-activedescendant');
        (data.groups || []).forEach(function (group) {
            const heading = document.createElement('div');
            heading.className = 'px-4 pt-3 pb-1 text-xs font-bold uppercase tracking-wider text-slate-500';
            heading.setAttribute('role', 'presentation');
            heading.textContent = group.name;
            list.appendChild(heading);
            group.items.forEach(function (item) {
                const a = document.createElement('a');
                a.href = item.url;
                a.id = 'search-option-' + options.length;
                a.setAttribute('role', 'option');
                a.setAttribute('aria-selected', 'false');
                a.className = 'block px-4 py-2 hover:bg-slate-100';
                const title = document.createElement('span');
                title.className = 'block text-sm font-semibold text-slate-900';
                title.textContent = item.title;
                a.appendChild(title);
                if (item.detail) {
                    const detail = document.createElement('span');
                    detail.className = 'block text-xs text-slate-500';
                    detail.textContent = item.detail;
                    a.appendChild(detail);
                }
                const index = options.length;
                a.addEventListener('mousemove', function () { if (active !== index) setActive(index); });
                options.push(a);
                list.appendChild(a);
            });
        });
        input.setAttribute('aria-expanded', options.length ? 'true' : 'false');
        if (options.length) {
            setActive(0);
            hint.innerHTML = '';
            const all = document.createElement('a');
            all.href = pageUrl + '?q=' + encodeURIComponent(data.q);
            all.className = 'font-semibold text-forest-700 hover:underline';
            all.textContent = 'See all results';
            hint.appendChild(all);
        } else {
            const none = document.createElement('p');
            none.className = 'px-4 py-6 text-sm text-slate-500 text-center';
            none.textContent = 'Nothing found. Try fewer or shorter words.';
            list.appendChild(none);
            hint.innerHTML = hintText;
        }
    }

    input.addEventListener('input', function () {
        clearTimeout(timer);
        const q = input.value.trim();
        if (q.length < 2) {
            list.textContent = '';
            options = [];
            input.setAttribute('aria-expanded', 'false');
            hint.innerHTML = hintText;
            return;
        }
        timer = setTimeout(function () {
            if (controller) controller.abort();
            controller = new AbortController();
            fetch(jsonUrl + '?q=' + encodeURIComponent(q), { credentials: 'same-origin', signal: controller.signal })
                .then(function (r) { return r.ok ? r.json() : { q: q, groups: [] }; })
                .then(function (data) { if (input.value.trim() === q) render(data); })
                .catch(function () { /* superseded by a newer search, or offline */ });
        }, 150);
    });

    input.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown' && options.length) { e.preventDefault(); setActive((active + 1) % options.length); }
        else if (e.key === 'ArrowUp' && options.length) { e.preventDefault(); setActive((active - 1 + options.length) % options.length); }
        else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); window.location.href = options[active].href; }
    });
})();
