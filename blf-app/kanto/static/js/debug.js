// Debug menu: press ? anywhere outside a text box. Shows who you are (and who you're viewing as), who's active,
// server load, the database, recent request timings and this page's load times. Only loaded for people allowed to
// see it; the data comes from /debug.json when the menu opens, and refreshes every 5 seconds while it's open.
(function () {
    let dialog, body, timer;

    function typing(el) {
        if (!el) return false;
        const tag = el.tagName;
        return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
    }

    document.addEventListener('keydown', function (e) {
        if (e.key !== '?' || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
        if (document.querySelector('dialog[open]:not(#debug-dialog)')) return;
        e.preventDefault();
        if (dialog && dialog.open) dialog.close(); else open();
    });

    function el(tag, cls, text) {
        const n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined && text !== null) n.textContent = text;
        return n;
    }

    function build() {
        dialog = el('dialog', 'w-[min(44rem,calc(100vw-2rem))] mt-16 p-0 rounded-2xl border border-slate-200 bg-white text-slate-800 shadow-2xl backdrop:bg-slate-900/40');
        dialog.id = 'debug-dialog';
        dialog.setAttribute('aria-label', 'Debug');
        const head = el('div', 'flex items-center justify-between gap-4 px-5 py-3 border-b border-slate-100');
        head.appendChild(el('h2', 'font-bold text-slate-900', 'Debug'));
        const close = el('button', 'text-sm font-semibold text-slate-500 hover:text-slate-800', 'Close');
        close.type = 'button';
        close.addEventListener('click', function () { dialog.close(); });
        head.appendChild(close);
        body = el('div', 'max-h-[75vh] overflow-y-auto px-5 py-4 space-y-5 text-sm');
        dialog.appendChild(head);
        dialog.appendChild(body);
        dialog.addEventListener('close', function () { clearInterval(timer); });
        dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });
        document.body.appendChild(dialog);
    }

    function open() {
        if (!dialog) build();
        body.replaceChildren(el('p', 'text-slate-500', 'Loading…'));
        dialog.showModal();
        load();
        timer = setInterval(load, 5000);
    }

    function load() {
        fetch('/debug.json', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
            .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
            .then(render)
            .catch(function (err) {
                body.replaceChildren(el('p', 'text-red-700', 'Couldn’t load the debug details (' + err.message + ').'));
            });
    }

    // A titled block of label/value rows; rows with an empty value are left out
    function section(title, rows, note) {
        const s = el('section');
        s.appendChild(el('h3', 'text-xs font-bold uppercase tracking-wide text-slate-500 mb-2', title));
        const dl = el('dl', 'grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-4 gap-y-1');
        rows.forEach(function (r) {
            if (r[1] === undefined || r[1] === null || r[1] === '') return;
            dl.appendChild(el('dt', 'text-slate-500', r[0]));
            dl.appendChild(el('dd', 'font-medium text-slate-800 tabular-nums break-words', String(r[1])));
        });
        s.appendChild(dl);
        if (note) s.appendChild(el('p', 'mt-2 text-xs text-slate-500', note));
        return s;
    }

    function person(p) {
        return [
            ['Name', p.name],
            ['Username', p.username],
            ['Account ID', p.account_id],
            ['Roles', (p.roles || []).join(', ') || 'None'],
            ['Two-step', p.two_step ? 'On' : 'Off'],
            ['Signed in', p.signed_in],
            ['Passkey confirmed', p.passkey_confirmed === undefined ? '' : (p.passkey_confirmed ? 'Yes' : 'No')],
        ];
    }

    const ms = function (v) { return v === undefined || v === null ? '' : Math.round(v * 10) / 10 + ' ms'; };
    const mb = function (v) { return v === undefined || v === null ? '' : v + ' MB'; };

    function pageTimings() {
        const nav = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
        if (!nav) return [['Timings', 'Not available in this browser']];
        const server = (nav.serverTiming || []).find(function (t) { return t.name === 'app'; });
        return [
            ['Server', server ? ms(server.duration) : ''],
            ['First byte', ms(nav.responseStart - nav.startTime)],
            ['Page ready', ms(nav.domContentLoadedEventEnd - nav.startTime)],
            ['Fully loaded', nav.loadEventEnd ? ms(nav.loadEventEnd - nav.startTime) : 'Still loading'],
            ['Page size', nav.transferSize ? Math.round(nav.transferSize / 102.4) / 10 + ' KB transferred' : 'From cache'],
            ['Files loaded', performance.getEntriesByType('resource').length],
        ];
    }

    function render(d) {
        const parts = [];
        parts.push(section('You', person(d.you)));
        if (d.viewing_as) {
            const v = section('Viewing as (read-only)', person(d.viewing_as));
            v.classList.add('p-3', 'rounded-xl', 'bg-amber-50', 'border', 'border-amber-200');
            parts.push(v);
        } else {
            parts.push(section('Viewing as', [['Impersonation', 'Not active']]));
        }

        const a = d.active;
        const act = section('Who’s active', [
            ['Signed in (' + a.session_limit_hours + 'h)', a.signed_in_within_session_limit + (a.signed_in_within_session_limit === 1 ? ' person' : ' people')],
            ['Last 15 minutes', a.last_15_minutes.length ? a.last_15_minutes.length + (a.last_15_minutes.length === 1 ? ' person:' : ' people:') : 'Nobody'],
        ], 'Activity is counted since the server started (' + a.tracking_since + '). Sign-ins last up to '
            + a.session_limit_hours + ' hours, so some may have closed the tab since.');
        if (a.last_15_minutes.length) {
            const ul = el('ul', 'mt-1 mb-1 space-y-0.5');
            a.last_15_minutes.forEach(function (p) {
                const li = el('li', 'flex justify-between gap-4');
                li.appendChild(el('span', 'font-medium text-slate-800', p.name + (p.name !== p.username ? ' (' + p.username + ')' : '')));
                li.appendChild(el('span', 'text-slate-500', p.ago));
                ul.appendChild(li);
            });
            act.insertBefore(ul, act.querySelector('p'));
        }
        parts.push(act);

        parts.push(section('This page', pageTimings()));

        const s = d.server;
        parts.push(section('Server', [
            ['Load (1, 5, 15 min)', s.load ? s.load.join(', ') + ' on ' + s.cpus + ' CPU' + (s.cpus === 1 ? '' : 's') : ''],
            ['Memory free', s.memory_total_mb ? mb(s.memory_available_mb) + ' of ' + mb(s.memory_total_mb) : ''],
            ['Swap in use', mb(s.swap_used_mb)],
            ['This app', s.process_mb ? mb(s.process_mb) + (s.runtime ? ' (this worker)' : '') : mb(s.go_total_mb) + ' (from Go)'],
            ['Go heap', mb(s.go_heap_mb)],
            ['Up', s.up],
            ['Host', s.host + (s.staging ? ' (staging)' : '')],
            ['Runtime', s.runtime || (s.go + ', ' + s.goroutines + ' goroutines, ' + s.gc_runs + ' GC runs')],
        ]));

        const db = d.database;
        parts.push(section('Database', [
            ['Query time', ms(db.query_ms)],
            ['Connections', db.connections_in_use + ' in use, ' + db.connections_idle + ' idle, ' + db.connections_max + ' max'],
            ['Size', mb(db.size_mb)],
        ]));

        const r = d.requests;
        const req = section('Requests' + (r.scope ? ' (' + r.scope + ')' : ''), [
            ['Last minute', r.last_minute + ' (' + r.per_second + ' a second)'],
            ['Since start', r.since_start],
            ['Time (last ' + r.sampled + ')', r.sampled ? 'median ' + ms(r.median_ms) + ', 95% under ' + ms(r.p95_ms) + ', slowest ' + ms(r.max_ms) : ''],
            ['Server errors', r.errors],
        ]);
        if (r.slowest_pages.length) {
            req.appendChild(el('p', 'mt-2 mb-1 text-xs font-semibold text-slate-500', 'Slowest pages on average'));
            const ul = el('ul', 'space-y-0.5');
            r.slowest_pages.forEach(function (p) {
                const li = el('li', 'flex justify-between gap-4');
                li.appendChild(el('span', 'font-mono text-xs text-slate-700', p.page));
                li.appendChild(el('span', 'text-slate-500 tabular-nums', ms(p.avg_ms) + ' × ' + p.count));
                ul.appendChild(li);
            });
            req.appendChild(ul);
        }
        parts.push(req);

        parts.push(el('p', 'text-xs text-slate-400', 'Press ? or Esc to close. Refreshes every 5 seconds.'));
        body.replaceChildren.apply(body, parts);
    }
})();
