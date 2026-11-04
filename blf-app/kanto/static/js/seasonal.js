// Seasonal touches, by the server's date (meta[name="kanto-season"], see season() in kanto/display.py):
//  - With the Haunted theme chosen (any time of year): a 1 in 25 chance of a ghost drifting past on each page load
//  - With the Memes theme chosen: a 1 in 8 chance of air horns, a "YEEEEE BOIII" and sunglasses
//  - June, with the Pride theme chosen: a 1 in 25 chance of a poison apple dropping in, then bursting into sparkles
//  - Occasions (OCCASIONS in kanto/display.py): on the day, a 1 in 20 chance for everyone of that occasion's animation, and
//    while its theme is offered, a 1 in 25 chance with the theme chosen. Safer Internet Day: padlocks clicking
//    shut. World Book Day: farm animals squeezing into a little house. Pi Day: raspberries and π. 4 May: two
//    glowing energy blades clashing. Lunar New Year: lanterns. Diwali: diyas. Eid: a crescent moon and stars.
//  - December, with the Festive theme chosen: a 1 in 12 chance of snow on each page load
//  - Bonfire Night (5 November) and New Year's Eve: a 1 in 20 chance of fireworks, for everyone
//  - 24 June (a birthday): a 1 in 23 chance of balloons, for everyone
// The odds are the usual ones below unless an admin changed them (meta[name="kanto-odds"], CELEBRATIONS in kanto/display.py);
// 0 turns one off. Never with reduced motion. On staging, and for admins, ?celebrate=ghost, snow, fireworks,
// balloons, apple, safer, books, pi, space, lunar, diwali, eid or meme plays one straight away.
(function () {
    const ODDS = { ghost: 25, meme: 8, apple: 25, occasion_day: 20, occasion_theme: 25, snow: 12, fireworks: 20, balloons: 23 };
    try {
        Object.assign(ODDS, JSON.parse(document.querySelector('meta[name="kanto-odds"]').content));
    } catch (e) { /* the usual odds */ }
    const meta = document.querySelector('meta[name="kanto-season"]');
    if (!meta) return;
    const season = (meta.content || '').split(' ');
    const root = document.documentElement;
    const reduced = function () {
        return root.dataset.motion === 'reduce' ||
            !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    };
    // A 1 in ODDS[name] chance; 0 means never
    const chance = function (name) { return ODDS[name] > 0 && Math.floor(Math.random() * ODDS[name]) === 0; };
    let MESSAGES = {};  // settings.CELEBRATION_MESSAGES
    try { MESSAGES = JSON.parse(document.querySelector('meta[name="kanto-messages"]').content); } catch (e) { /* none */ }

    function snow() {
        const canvas = document.createElement('canvas');
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;z-index:9999;pointer-events:none;transition:opacity 1.5s;';
        document.body.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        function resize() {
            canvas.width = window.innerWidth * dpr;
            canvas.height = window.innerHeight * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }
        resize();
        window.addEventListener('resize', resize);
        const W = window.innerWidth, H = window.innerHeight;
        const flakes = [];
        const count = Math.round(Math.min(160, W * H / 9000));
        for (let i = 0; i < count; i++) {
            const r = 1.6 + Math.random() * 3.4;
            flakes.push({ x: Math.random() * W, y: -Math.random() * H, r: r, vy: 0.4 + r * 0.35,
                          sway: Math.random() * Math.PI * 2, swaySpeed: 0.01 + Math.random() * 0.02 });
        }
        const SHOW_MS = 9000;
        const start = performance.now();
        let faded = false;
        function frame(now) {
            ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
            for (const f of flakes) {
                f.sway += f.swaySpeed;
                f.x += Math.sin(f.sway) * 0.6;
                f.y += f.vy;
                // Keep falling while the show runs; afterwards let the last flakes fall off the page
                if (f.y > window.innerHeight + 5 && now - start < SHOW_MS) { f.y = -5; f.x = Math.random() * window.innerWidth; }
                ctx.beginPath();
                ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
                ctx.fillStyle = '#ffffff';
                ctx.shadowColor = 'rgba(70,100,150,.8)';
                ctx.shadowBlur = 5;
                ctx.fill();
            }
            if (now - start > SHOW_MS && !faded) {
                faded = true;
                canvas.style.opacity = '0';
                setTimeout(function () { window.removeEventListener('resize', resize); canvas.remove(); }, 1600);
            }
            if (!faded || canvas.isConnected) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    // A small friendly ghost (drawn here, so it's ours): drifts across the page, bobbing, then fades away
    const GHOST_SVG = '<svg viewBox="0 0 100 120" width="100%" height="100%" aria-hidden="true">' +
        '<defs><radialGradient id="kanto-ghost-body" cx="40%" cy="30%" r="75%"><stop offset="0" stop-color="#fbf8ff"/>' +
        '<stop offset=".7" stop-color="#e2d6f7"/><stop offset="1" stop-color="#bba5e6"/></radialGradient></defs>' +
        '<path d="M50 4C24 4 8 24 8 50v58c0 4 4 6 7 3l8-7 9 9c2 2 5 2 7 0l11-10 11 10c2 2 5 2 7 0l9-9 8 7c3 3 7 1 7-3V50C92 24 76 4 50 4z" fill="url(#kanto-ghost-body)"/>' +
        '<ellipse cx="36" cy="46" rx="7" ry="10" fill="#2a1d3d"/><ellipse cx="64" cy="46" rx="7" ry="10" fill="#2a1d3d"/>' +
        '<ellipse cx="38" cy="42" rx="2.4" ry="3.2" fill="#fff"/><ellipse cx="66" cy="42" rx="2.4" ry="3.2" fill="#fff"/>' +
        '<path d="M38 66q12 12 24 0" stroke="#2a1d3d" stroke-width="4" fill="none" stroke-linecap="round"/>' +
        '<ellipse cx="25" cy="60" rx="6" ry="3.5" fill="#f4a6c8" opacity=".55"/><ellipse cx="75" cy="60" rx="6" ry="3.5" fill="#f4a6c8" opacity=".55"/>' +
        '</svg>';

    function ghost() {
        const el = document.createElement('div');
        el.setAttribute('aria-hidden', 'true');
        const size = Math.round(Math.min(140, Math.max(80, window.innerWidth / 12)));
        const leftToRight = Math.random() < 0.5;
        const top = window.innerHeight * (0.3 + Math.random() * 0.4);
        el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;width:' + size + 'px;height:' + (size * 1.2) + 'px;' +
            'top:' + top + 'px;left:0;filter:drop-shadow(0 0 18px rgba(190,160,255,.75));will-change:transform,opacity;';
        el.innerHTML = GHOST_SVG;
        document.body.appendChild(el);
        const from = leftToRight ? -size - 20 : window.innerWidth + 20;
        const to = leftToRight ? window.innerWidth + 20 : -size - 20;
        const flip = leftToRight ? 1 : -1;  // faces the way it's going
        const frames = [];
        for (let i = 0; i <= 10; i++) {
            const t = i / 10;
            frames.push({
                transform: 'translate(' + (from + (to - from) * t) + 'px,' + (Math.sin(t * Math.PI * 4) * 18) + 'px) ' +
                           'scaleX(' + flip + ') rotate(' + (Math.sin(t * Math.PI * 4 + 1) * 6) + 'deg)',
                opacity: t < 0.1 ? t * 9 : t > 0.85 ? (1 - t) * 6 : 0.9,
            });
        }
        const anim = el.animate(frames, { duration: 7000, easing: 'ease-in-out' });
        anim.onfinish = function () { el.remove(); };
    }

    // Balloons on strings float up from the bottom of the page, swaying, and drift off the top
    const BALLOON_COLOURS = ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#a855f7', '#ec4899', '#14b8a6'];
    function balloons() {
        const count = Math.round(Math.min(18, Math.max(9, window.innerWidth / 90)));
        for (let i = 0; i < count; i++) {
            const colour = BALLOON_COLOURS[i % BALLOON_COLOURS.length];
            const size = 46 + Math.random() * 30;
            const el = document.createElement('div');
            el.setAttribute('aria-hidden', 'true');
            el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;bottom:0;left:' +
                (Math.random() * 92) + 'vw;width:' + size + 'px;height:' + (size * 2.1) + 'px;will-change:transform;';
            el.innerHTML = '<svg viewBox="0 0 50 105" width="100%" height="100%">' +
                '<path d="M25 58 q-4 12 3 22 t-3 24" stroke="#94a3b8" stroke-width="1.2" fill="none"/>' +
                '<path d="M25 2C11 2 3 14 3 27c0 15 11 27 22 31 11-4 22-16 22-31C47 14 39 2 25 2z" fill="' + colour + '"/>' +
                '<path d="M22 58l3-3 3 3z" fill="' + colour + '"/>' +
                '<ellipse cx="16" cy="18" rx="4" ry="7" fill="#fff" opacity=".45" transform="rotate(-20 16 18)"/></svg>';
            document.body.appendChild(el);
            const rise = window.innerHeight + size * 2.4;
            const sway = 20 + Math.random() * 30;
            const frames = [];
            for (let f = 0; f <= 8; f++) {
                const t = f / 8;
                frames.push({ transform: 'translate(' + (Math.sin(t * Math.PI * 3 + i) * sway) + 'px,' + (size * 2.2 - rise * t) + 'px) rotate(' +
                                         (Math.sin(t * Math.PI * 3 + i + 1) * 8) + 'deg)' });
            }
            const anim = el.animate(frames, { duration: 6000 + Math.random() * 3000, delay: Math.random() * 1800, easing: 'ease-in', fill: 'backwards' });
            anim.onfinish = function () { el.remove(); };
        }
    }

    // A glossy poison apple (drawn here): drops in, bounces, wobbles, then bursts into rainbow sparkles
    const APPLE_SVG = '<svg viewBox="0 0 100 110" width="100%" height="100%" aria-hidden="true">' +
        '<defs><radialGradient id="kanto-apple" cx="35%" cy="35%" r="75%"><stop offset="0" stop-color="#e0325a"/>' +
        '<stop offset=".55" stop-color="#9b1240"/><stop offset="1" stop-color="#4a0d4f"/></radialGradient></defs>' +
        '<path d="M50 28c-8-6-30-8-38 12-8 22 4 50 20 58 8 4 12 2 18-1 6 3 10 5 18 1 16-8 28-36 20-58-8-20-30-18-38-12z" fill="url(#kanto-apple)"/>' +
        '<path d="M50 28c0-8 2-16 8-22" stroke="#5b3a1e" stroke-width="4" fill="none" stroke-linecap="round"/>' +
        '<path d="M56 14c8-8 20-8 26-4-6 8-18 10-26 4z" fill="#3fa34d"/>' +
        '<ellipse cx="30" cy="44" rx="7" ry="12" fill="#fff" opacity=".35" transform="rotate(25 30 44)"/>' +
        '<path d="M66 86c0 6 4 10 4 14a4 4 0 0 1-8 0c0-4 4-8 4-14z" fill="#8be04e"/>' +
        '<circle cx="64" cy="78" r="5" fill="#8be04e" opacity=".9"/>' +
        '</svg>';
    const SPARKLE_COLOURS = ['#e40303', '#ff8c00', '#ffed00', '#008026', '#24408e', '#732982'];

    function apple() {
        const size = Math.round(Math.min(130, Math.max(80, window.innerWidth / 12)));
        const x = window.innerWidth * (0.25 + Math.random() * 0.5) - size / 2;
        const landY = window.innerHeight * 0.55;
        const el = document.createElement('div');
        el.setAttribute('aria-hidden', 'true');
        el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;left:' + x + 'px;top:0;width:' + size + 'px;height:' + (size * 1.1) + 'px;' +
            'filter:drop-shadow(0 0 14px rgba(139,224,78,.55)) drop-shadow(0 8px 10px rgba(0,0,0,.25));will-change:transform,opacity;';
        el.innerHTML = APPLE_SVG;
        document.body.appendChild(el);
        const at = function (y, extra) { return 'translateY(' + y + 'px) ' + (extra || ''); };
        const drop = el.animate([
            { transform: at(-size * 1.4), offset: 0 },
            { transform: at(landY), offset: 0.35, easing: 'ease-out' },
            { transform: at(landY - 60), offset: 0.47, easing: 'ease-in' },
            { transform: at(landY), offset: 0.58, easing: 'ease-out' },
            { transform: at(landY - 18), offset: 0.64, easing: 'ease-in' },
            { transform: at(landY), offset: 0.7 },
            { transform: at(landY, 'rotate(-10deg)'), offset: 0.76 },
            { transform: at(landY, 'rotate(10deg)'), offset: 0.82 },
            { transform: at(landY, 'rotate(-6deg)'), offset: 0.88 },
            { transform: at(landY, 'scale(1.15)'), offset: 0.96, opacity: 1 },
            { transform: at(landY, 'scale(1.35)'), offset: 1, opacity: 0 },
        ], { duration: 3600, easing: 'ease-in', fill: 'forwards' });
        drop.onfinish = function () {
            el.remove();
            // Burst into rainbow sparkles
            const cx = x + size / 2, cy = landY + size * 0.55;
            for (let i = 0; i < 40; i++) {
                const s = document.createElement('div');
                s.setAttribute('aria-hidden', 'true');
                const r = 5 + Math.random() * 6;
                s.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;left:' + (cx - r) + 'px;top:' + (cy - r) + 'px;width:' + (r * 2) +
                    'px;height:' + (r * 2) + 'px;border-radius:50%;background:' + SPARKLE_COLOURS[i % SPARKLE_COLOURS.length] + ';box-shadow:0 0 8px ' + SPARKLE_COLOURS[i % SPARKLE_COLOURS.length] + ';';
                document.body.appendChild(s);
                const angle = (Math.PI * 2 * i) / 40 + Math.random() * 0.3;
                const dist = 80 + Math.random() * 120;
                s.animate([{ transform: 'translate(0,0) scale(1)', opacity: 1 },
                           { transform: 'translate(' + Math.cos(angle) * dist + 'px,' + (Math.sin(angle) * dist + 40) + 'px) scale(.3)', opacity: 0 }],
                          { duration: 1100 + Math.random() * 600, easing: 'cubic-bezier(.2,.7,.4,1)' }).onfinish = function () { s.remove(); };
            }
        };
    }

    // ---- Occasions ----
    // Something that floats up from the bottom and off the top, swaying, like the balloons
    function floatUp(svg, count, sizeMin, sizeRange, ratio, onEach) {
        for (let i = 0; i < count; i++) {
            const size = sizeMin + Math.random() * sizeRange;
            const el = document.createElement('div');
            el.setAttribute('aria-hidden', 'true');
            el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;bottom:0;left:' + (Math.random() * 92) + 'vw;width:' +
                size + 'px;height:' + (size * ratio) + 'px;will-change:transform;';
            el.innerHTML = typeof svg === 'function' ? svg(i) : svg;
            document.body.appendChild(el);
            const rise = window.innerHeight + size * ratio * 1.2;
            const sway = 15 + Math.random() * 25;
            const frames = [];
            for (let f = 0; f <= 8; f++) {
                const t = f / 8;
                frames.push({ transform: 'translate(' + (Math.sin(t * Math.PI * 3 + i) * sway) + 'px,' + (size * ratio * 1.1 - rise * t) + 'px) rotate(' +
                                         (Math.sin(t * Math.PI * 3 + i + 1) * 7) + 'deg)' });
            }
            const delay = Math.random() * 1800;
            const anim = el.animate(frames, { duration: 6500 + Math.random() * 2500, delay: delay, easing: 'ease-in', fill: 'backwards' });
            anim.onfinish = function () { el.remove(); };
            if (onEach) onEach(el, delay);
        }
    }

    // Safer Internet Day: padlocks rise, and each clicks shut on the way up
    function safer() {
        const svg = '<svg viewBox="0 0 40 52" width="100%" height="100%"><path class="shackle" d="M11 22V14a9 9 0 0 1 18 0v8" stroke="#0e7c86" stroke-width="5" fill="none" stroke-linecap="round"/>' +
            '<rect x="4" y="22" width="32" height="26" rx="6" fill="#0b5cad"/><circle cx="20" cy="33" r="4" fill="#e6f0fb"/><rect x="18.5" y="34" width="3" height="7" rx="1.5" fill="#e6f0fb"/></svg>';
        floatUp(svg, 12, 34, 20, 1.3, function (el, delay) {
            el.querySelector('.shackle').animate([{ transform: 'translateY(-7px)' }, { transform: 'translateY(-7px)', offset: 0.35 }, { transform: 'translateY(0)', offset: 0.4 }, { transform: 'translateY(0)' }],
                                                 { duration: 7000, delay: delay, fill: 'both' });
        });
    }

    // Book Day: farm animals squeeze, one by one, into a little house that bulges, until they all tumble out again
    function books() {
        const animals = ['🐔', '🐐', '🐷', '🐄', '🐕', '🐈'];
        const stage = document.createElement('div');
        stage.setAttribute('aria-hidden', 'true');
        const w = 150, h = 130;
        const left = window.innerWidth / 2 - w / 2, top = window.innerHeight * 0.55;
        stage.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;left:' + left + 'px;top:' + top + 'px;width:' + w + 'px;height:' + h + 'px;';
        const house = document.createElement('div');
        house.style.cssText = 'position:absolute;inset:0;transform-origin:50% 100%;';
        house.innerHTML = '<svg viewBox="0 0 150 130" width="100%" height="100%"><path d="M10 60 75 8l65 52z" fill="#b5651d"/><path d="M10 60 75 8l65 52" stroke="#6e2e0e" stroke-width="5" fill="none" stroke-linejoin="round"/>' +
            '<rect x="22" y="58" width="106" height="68" rx="4" fill="#f2e2c4" stroke="#8a3b12" stroke-width="4"/><rect x="62" y="84" width="26" height="42" rx="3" fill="#8a3b12"/>' +
            '<rect x="34" y="72" width="20" height="18" fill="#9fd3f0" stroke="#8a3b12" stroke-width="3"/><rect x="96" y="72" width="20" height="18" fill="#9fd3f0" stroke="#8a3b12" stroke-width="3"/>' +
            '<rect x="102" y="18" width="14" height="26" fill="#8a3b12"/></svg>';
        stage.appendChild(house);
        document.body.appendChild(stage);
        stage.animate([{ opacity: 0, transform: 'translateY(20px)' }, { opacity: 1, transform: 'none' }], { duration: 400, fill: 'both' });
        const walkers = [];
        animals.forEach(function (emoji, i) {
            const a = document.createElement('div');
            a.textContent = emoji;
            a.style.cssText = 'position:fixed;z-index:10000;pointer-events:none;font-size:34px;line-height:1;left:0;top:' + (top + h - 40) + 'px;';
            document.body.appendChild(a);
            walkers.push(a);
            const from = i % 2 ? window.innerWidth + 20 : -60;
            const door = left + w / 2 - 17;
            a.animate([{ transform: 'translate(' + from + 'px,0)' }, { transform: 'translate(' + ((from + door) / 2) + 'px,-22px)', offset: 0.5 }, { transform: 'translate(' + door + 'px,0) scale(.4)', opacity: 1, offset: 0.92 }, { transform: 'translate(' + door + 'px,0) scale(.2)', opacity: 0 }],
                      { duration: 900, delay: 500 + i * 650, easing: 'ease-in-out', fill: 'both' });
            // The house squeezes a little more with every arrival
            house.animate([{ transform: 'scale(' + (1 + i * 0.07) + ',' + (1 - i * 0.03) + ')' }, { transform: 'scale(' + (1.12 + i * 0.07) + ',' + (0.93 - i * 0.03) + ')' }, { transform: 'scale(' + (1.07 + i * 0.07) + ',' + (0.97 - i * 0.03) + ')' }],
                          { duration: 300, delay: 500 + i * 650 + 820, fill: 'forwards', easing: 'ease-out' });
        });
        const burst = 500 + animals.length * 650 + 700;
        setTimeout(function () {
            house.animate([{ transform: 'scale(1.5,.8)' }, { transform: 'scale(.9,1.1)', offset: 0.3 }, { transform: 'scale(1)' }], { duration: 600, fill: 'forwards' });
            walkers.forEach(function (a, i) {
                const angle = Math.PI * (1.1 + 0.8 * i / (walkers.length - 1));
                const cx = left + w / 2 - 17, cy = top + h - 40;
                a.animate([{ transform: 'translate(' + cx + 'px,0) scale(.3)', opacity: 1 },
                           { transform: 'translate(' + (cx + Math.cos(angle) * 260) + 'px,' + (Math.sin(angle) * 220) + 'px) scale(1.1) rotate(' + (i * 60 - 150) + 'deg)', opacity: 1, offset: 0.7 },
                           { transform: 'translate(' + (cx + Math.cos(angle) * 320) + 'px,' + (Math.sin(angle) * 200 + 140) + 'px) scale(1)', opacity: 0 }],
                          { duration: 1600, easing: 'cubic-bezier(.2,.8,.4,1)', fill: 'forwards' }).onfinish = function () { a.remove(); };
            });
            setTimeout(function () { stage.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 600, fill: 'forwards' }).onfinish = function () { stage.remove(); }; }, 1400);
        }, burst);
    }

    // Pi Day: raspberries tumble down while π's digits slide across
    function pi() {
        const berry = '<svg viewBox="0 0 40 44" width="100%" height="100%"><path d="M20 8c-4-6-12-6-14-2 6 0 10 2 14 6 4-4 8-6 14-6-2-4-10-4-14 2z" fill="#75a928"/>' +
            [[14, 16], [26, 16], [20, 18], [10, 24], [20, 25], [30, 24], [14, 31], [26, 31], [20, 37]].map(function (p) {
                return '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="6" fill="#c51a4a"/><circle cx="' + (p[0] - 2) + '" cy="' + (p[1] - 2) + '" r="1.6" fill="#f08aa8"/>';
            }).join('') + '</svg>';
        for (let i = 0; i < 12; i++) {
            const size = 30 + Math.random() * 22;
            const el = document.createElement('div');
            el.setAttribute('aria-hidden', 'true');
            el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;top:0;left:' + (Math.random() * 94) + 'vw;width:' + size + 'px;height:' + (size * 1.1) + 'px;';
            el.innerHTML = berry;
            document.body.appendChild(el);
            const spin = (Math.random() < 0.5 ? -1 : 1) * (180 + Math.random() * 360);
            el.animate([{ transform: 'translateY(-60px) rotate(0)' }, { transform: 'translateY(' + (window.innerHeight + 60) + 'px) rotate(' + spin + 'deg)' }],
                       { duration: 3500 + Math.random() * 2500, delay: Math.random() * 2000, easing: 'cubic-bezier(.4,0,.8,.6)', fill: 'backwards' }).onfinish = function () { el.remove(); };
        }
        const digits = document.createElement('div');
        digits.setAttribute('aria-hidden', 'true');
        digits.textContent = 'π = 3.14159 26535 89793 23846 26433 83279 50288 41971 69399 37510';
        digits.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;left:0;bottom:8vh;white-space:nowrap;font:700 28px/1 "Fira Code",ui-monospace,monospace;' +
            'color:#b0154a;text-shadow:0 2px 0 #fff,0 0 12px rgba(117,169,40,.5);';
        document.body.appendChild(digits);
        digits.animate([{ transform: 'translateX(' + window.innerWidth + 'px)' }, { transform: 'translateX(-110%)' }], { duration: 8000, easing: 'linear' }).onfinish = function () { digits.remove(); };
    }

    // Lunar New Year: red lanterns with gold bands and tassels float up
    function lunar() {
        const svg = '<svg viewBox="0 0 40 70" width="100%" height="100%"><path d="M20 0v6" stroke="#d4a017" stroke-width="2"/><rect x="12" y="6" width="16" height="4" rx="1" fill="#d4a017"/>' +
            '<ellipse cx="20" cy="27" rx="17" ry="17" fill="#d62828"/><path d="M20 10c-6 4-6 30 0 34M20 10c6 4 6 30 0 34M8 15c-3 8-3 16 0 24M32 15c3 8 3 16 0 24" stroke="#a4161a" stroke-width="1.5" fill="none"/>' +
            '<rect x="12" y="43" width="16" height="4" rx="1" fill="#d4a017"/><path d="M20 47v18M17 50v12M23 50v12" stroke="#f2c45a" stroke-width="1.6"/>' +
            '<ellipse cx="14" cy="21" rx="3" ry="6" fill="#ff8f6b" opacity=".45"/></svg>';
        floatUp(svg, 12, 34, 22, 1.75, function (el) { el.style.filter = 'drop-shadow(0 0 10px rgba(255, 170, 60, .7))'; });
    }

    // Diwali: a row of diyas appears along the bottom, their flames flickering, as golden sparks rise
    function diwali() {
        const n = Math.max(5, Math.min(11, Math.round(window.innerWidth / 130)));
        const els = [];
        for (let i = 0; i < n; i++) {
            const el = document.createElement('div');
            el.setAttribute('aria-hidden', 'true');
            el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;bottom:3vh;left:' + ((i + 0.5) / n * 100) + 'vw;width:56px;height:56px;margin-left:-28px;';
            el.innerHTML = '<svg viewBox="0 0 56 56" width="100%" height="100%"><path class="flame" d="M28 6c6 8 7 14 0 20-7-6-6-12 0-20z" fill="#ffcc4d" style="transform-origin:28px 26px"/>' +
                '<path d="M28 13c3 4 3 8 0 11-3-3-3-7 0-11z" fill="#fff3b0"/><path d="M4 30c4 16 44 16 48 0z" fill="#c2410c"/><path d="M4 30h48" stroke="#f59e2a" stroke-width="3" stroke-linecap="round"/>' +
                '<circle cx="16" cy="38" r="2" fill="#ffd27a"/><circle cx="28" cy="41" r="2" fill="#ffd27a"/><circle cx="40" cy="38" r="2" fill="#ffd27a"/></svg>';
            el.style.filter = 'drop-shadow(0 0 12px rgba(255, 190, 70, .8))';
            document.body.appendChild(el);
            els.push(el);
            el.animate([{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none', offset: 0.1 }, { opacity: 1, offset: 0.85 }, { opacity: 0 }],
                       { duration: 7000, delay: i * 180, fill: 'both' }).onfinish = function () { el.remove(); };
            el.querySelector('.flame').animate([{ transform: 'scale(1,1) rotate(-3deg)' }, { transform: 'scale(.9,1.15) rotate(3deg)' }, { transform: 'scale(1.05,.95) rotate(-2deg)' }],
                                               { duration: 380 + Math.random() * 200, iterations: 20, direction: 'alternate' });
        }
        for (let i = 0; i < 30; i++) {
            const sp = document.createElement('div');
            sp.setAttribute('aria-hidden', 'true');
            const r = 2 + Math.random() * 3;
            sp.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;bottom:8vh;left:' + (Math.random() * 100) + 'vw;width:' + (r * 2) + 'px;height:' + (r * 2) +
                'px;border-radius:50%;background:#ffd27a;box-shadow:0 0 8px #ffb347;';
            document.body.appendChild(sp);
            sp.animate([{ transform: 'translateY(0)', opacity: 0 }, { opacity: 1, offset: 0.2 }, { transform: 'translate(' + ((Math.random() - 0.5) * 80) + 'px,-' + (180 + Math.random() * 300) + 'px)', opacity: 0 }],
                       { duration: 2500 + Math.random() * 2000, delay: 600 + Math.random() * 4000, fill: 'both' }).onfinish = function () { sp.remove(); };
        }
    }

    // Eid: a crescent moon rises and stars twinkle in around it
    function eid() {
        const size = Math.round(Math.min(150, Math.max(90, window.innerWidth / 10)));
        const moon = document.createElement('div');
        moon.setAttribute('aria-hidden', 'true');
        moon.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;right:12vw;top:18vh;width:' + size + 'px;height:' + size + 'px;filter:drop-shadow(0 0 18px rgba(246,221,143,.8));';
        moon.innerHTML = '<svg viewBox="0 0 100 100" width="100%" height="100%"><path d="M62 8a44 44 0 1 0 30 70A38 38 0 1 1 62 8z" fill="#f6dd8f"/></svg>';
        document.body.appendChild(moon);
        moon.animate([{ transform: 'translateY(50vh) rotate(-20deg)', opacity: 0 }, { transform: 'none', opacity: 1, offset: 0.3 }, { transform: 'translateY(-6px)', opacity: 1, offset: 0.8 }, { transform: 'translateY(-10px)', opacity: 0 }],
                     { duration: 7000, easing: 'ease-out', fill: 'both' }).onfinish = function () { moon.remove(); };
        for (let i = 0; i < 18; i++) {
            const st = document.createElement('div');
            st.setAttribute('aria-hidden', 'true');
            const r = 10 + Math.random() * 14;
            st.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;left:' + (35 + Math.random() * 62) + 'vw;top:' + (5 + Math.random() * 45) + 'vh;width:' + r + 'px;height:' + r + 'px;';
            st.innerHTML = '<svg viewBox="0 0 20 20" width="100%" height="100%"><path d="M10 0l2.4 7.6L20 10l-7.6 2.4L10 20l-2.4-7.6L0 10l7.6-2.4z" fill="#f6dd8f"/></svg>';
            document.body.appendChild(st);
            st.animate([{ opacity: 0, transform: 'scale(.2)' }, { opacity: 1, transform: 'scale(1)', offset: 0.2 }, { opacity: .4, transform: 'scale(.7)', offset: 0.45 }, { opacity: 1, transform: 'scale(1)', offset: 0.7 }, { opacity: 0, transform: 'scale(.3)' }],
                       { duration: 3500 + Math.random() * 2000, delay: 800 + Math.random() * 2500, fill: 'both' }).onfinish = function () { st.remove(); };
        }
    }

    // 4 May: two glowing energy blades, one blue and one red, ignite, swing in and clash three times, then part
    function space() {
        const scale = Math.min(1, window.innerWidth / 760);
        const length = 270 * scale, hiltH = 56 * scale, gap = 165 * scale;
        const cx = window.innerWidth / 2, pivotY = window.innerHeight * 0.62 + 120 * scale;
        function blade(colour, side) {
            const el = document.createElement('div');
            el.setAttribute('aria-hidden', 'true');
            el.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;width:' + (14 * scale + 4) + 'px;height:' + (length + hiltH) + 'px;' +
                'left:' + (cx + side * gap - 7 * scale) + 'px;top:' + (pivotY - length - hiltH) + 'px;transform-origin:50% 100%;';
            const glow = document.createElement('div');
            glow.style.cssText = 'position:absolute;left:50%;bottom:' + (hiltH - 2) + 'px;width:' + (8 * scale + 2) + 'px;height:' + length + 'px;margin-left:-' + (4 * scale + 1) + 'px;' +
                'border-radius:999px;background:#fff;transform-origin:50% 100%;box-shadow:0 0 6px #fff,0 0 14px ' + colour + ',0 0 30px ' + colour + ',0 0 60px ' + colour + ';';
            const hilt = document.createElement('div');
            hilt.style.cssText = 'position:absolute;left:0;right:0;bottom:0;height:' + hiltH + 'px;border-radius:4px;' +
                'background:linear-gradient(90deg,#4b5563,#e5e7eb 40%,#9ca3af 60%,#374151);box-shadow:inset 0 ' + (10 * scale) + 'px 0 -' + (6 * scale) + 'px #111,0 2px 6px rgba(0,0,0,.5);';
            el.append(glow, hilt);
            document.body.appendChild(el);
            return { el: el, glow: glow };
        }
        const left = blade('#3b9dff', -1), right = blade('#ff2b3a', 1);
        const pose = function (angle) { return { transform: 'rotate(' + angle + 'deg)' }; };
        // Angles lean each blade towards the middle; about 42 degrees is where the tips cross
        const swing = [[-25, 0], [-25, 0.12], [42, 0.3], [28, 0.37], [45, 0.48], [30, 0.55], [42, 0.66], [40, 0.72], [43, 0.78], [18, 0.88], [12, 1]];
        const timing = { duration: 4400, easing: 'ease-in-out', fill: 'both' };
        const anims = [];
        [[left, 1], [right, -1]].forEach(function (pair) {
            const b = pair[0], dir = pair[1];
            anims.push(b.el.animate(swing.map(function (p) { return Object.assign(pose(p[0] * dir), { offset: p[1], opacity: p[1] === 1 ? 0 : 1 }); }), timing));
            b.glow.animate([{ transform: 'scaleY(0)' }, { transform: 'scaleY(0)', offset: 0.04 }, { transform: 'scaleY(1)', offset: 0.13 }, { transform: 'scaleY(1)', offset: 0.86 }, { transform: 'scaleY(0)' }],
                           { duration: 4400, fill: 'both' });
        });
        anims[0].onfinish = function () { left.el.remove(); right.el.remove(); };
        // A flash and sparks where they meet
        const meetY = pivotY - hiltH - Math.cos(42 * Math.PI / 180) * length * 0.82;
        [0.3, 0.48, 0.66].forEach(function (when) {
            setTimeout(function () {
                const flash = document.createElement('div');
                flash.setAttribute('aria-hidden', 'true');
                const size = 120 * scale;
                flash.style.cssText = 'position:fixed;z-index:10000;pointer-events:none;left:' + (cx - size / 2) + 'px;top:' + (meetY - size / 2) + 'px;width:' + size + 'px;height:' + size +
                    'px;border-radius:50%;background:radial-gradient(circle,#fff 0,rgba(255,255,255,.9) 18%,rgba(190,170,255,.5) 40%,transparent 70%);';
                document.body.appendChild(flash);
                flash.animate([{ transform: 'scale(.3)', opacity: 1 }, { transform: 'scale(1.3)', opacity: 0 }], { duration: 380, easing: 'ease-out' }).onfinish = function () { flash.remove(); };
                for (let i = 0; i < 14; i++) {
                    const sp = document.createElement('div');
                    sp.setAttribute('aria-hidden', 'true');
                    sp.style.cssText = 'position:fixed;z-index:10000;pointer-events:none;left:' + cx + 'px;top:' + meetY + 'px;width:3px;height:3px;border-radius:50%;background:' +
                        (i % 2 ? '#ffe9a8' : '#ffffff') + ';box-shadow:0 0 6px #ffd27a;';
                    document.body.appendChild(sp);
                    const angle = Math.random() * Math.PI * 2, dist = 30 + Math.random() * 70;
                    sp.animate([{ transform: 'translate(0,0)', opacity: 1 }, { transform: 'translate(' + Math.cos(angle) * dist + 'px,' + (Math.sin(angle) * dist + 30) + 'px)', opacity: 0 }],
                               { duration: 400 + Math.random() * 300, easing: 'ease-out' }).onfinish = function () { sp.remove(); };
                }
            }, when * 4400);
        });
    }

    // Memes: air horns blast in from both sides, "YEEEEE BOIII" slams onto the screen and shakes, and a pair of
    // sunglasses drops onto the page heading ("deal with it"). Emoji and text only.
    function meme() {
        const IMPACT = 'font-family:Impact,"Anton","Arial Black",sans-serif;color:#fff;-webkit-text-stroke:2px #000;paint-order:stroke fill;' +
            'text-shadow:3px 3px 0 #000;pointer-events:none;position:fixed;z-index:9999;';
        const parts = [];
        const add = function (text, css) {
            const el = document.createElement('div');
            el.setAttribute('aria-hidden', 'true');
            el.textContent = text;
            el.style.cssText = css;
            document.body.appendChild(el);
            parts.push(el);
            return el;
        };
        [-1, 1].forEach(function (side) {
            const horn = add('📯', 'position:fixed;z-index:9999;pointer-events:none;top:38vh;font-size:clamp(48px,9vw,96px);' +
                             (side < 0 ? 'left:2vw;transform:scaleX(-1);' : 'right:2vw;'));
            horn.animate([{ transform: 'translateX(' + side * 40 + 'vw)' + (side < 0 ? ' scaleX(-1)' : '') },
                          { transform: 'translateX(0)' + (side < 0 ? ' scaleX(-1)' : ''), offset: .25 },
                          { transform: 'translateX(' + side * -8 + 'px)' + (side < 0 ? ' scaleX(-1)' : '') + ' rotate(' + side * 6 + 'deg)', offset: .35 },
                          { transform: 'translateX(0)' + (side < 0 ? ' scaleX(-1)' : ''), offset: .45 },
                          { transform: 'translateX(' + side * 40 + 'vw)' + (side < 0 ? ' scaleX(-1)' : '') }],
                         { duration: 2600, easing: 'ease-in-out', fill: 'both' });
        });
        const yee = add('YEEEEE BOIII', IMPACT + 'left:50%;top:40vh;font-size:clamp(40px,10vw,120px);white-space:nowrap;');
        const shake = [{ transform: 'translate(-50%,-50%) scale(3)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1)', opacity: 1, offset: .15 }];
        for (let i = 0; i < 8; i++) {
            shake.push({ transform: 'translate(calc(-50% + ' + (Math.random() * 16 - 8) + 'px),calc(-50% + ' + (Math.random() * 12 - 6) + 'px)) rotate(' + (Math.random() * 6 - 3) + 'deg)', offset: .2 + i * .07 });
        }
        shake.push({ transform: 'translate(-50%,-50%) scale(1.05)', opacity: 0 });
        yee.animate(shake, { duration: 2600, easing: 'linear', fill: 'both' });
        // Sunglasses drop onto the page heading, with "DEAL WITH IT" underneath
        const heading = document.querySelector('main h1, h1');
        const box = heading ? heading.getBoundingClientRect() : { left: window.innerWidth / 2 - 40, top: 120, width: 80, height: 40 };
        const top = Math.max(8, Math.min(box.top, window.innerHeight - 120));
        const shades = add('🕶️', 'position:fixed;z-index:9999;pointer-events:none;font-size:56px;left:' + (box.left + Math.min(box.width, 260) / 2 - 28) + 'px;top:' + top + 'px;');
        shades.animate([{ transform: 'translateY(-' + (top + 80) + 'px)' }, { transform: 'translateY(-' + (top + 80) + 'px)', offset: .45 },
                        { transform: 'translateY(0)', offset: .75 }, { transform: 'translateY(0)' }],
                       { duration: 4200, easing: 'ease-in', fill: 'both' });
        const deal = add('DEAL WITH IT', IMPACT + 'font-size:28px;-webkit-text-stroke:1px #000;text-shadow:2px 2px 0 #000;left:' +
                         Math.max(8, box.left) + 'px;top:' + (top + 64) + 'px;');
        deal.animate([{ opacity: 0 }, { opacity: 0, offset: .75 }, { opacity: 1, offset: .8 }, { opacity: 1 }], { duration: 4200, fill: 'both' });
        setTimeout(function () {
            parts.forEach(function (el) {
                el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 500, fill: 'forwards' }).onfinish = function () { el.remove(); };
            });
        }, 5600);
    }

    const OCCASION_ANIMATIONS = { safer: safer, books: books, pi: pi, space: space, lunar: lunar, diwali: diwali, eid: eid };

    function fireworks() {
        const celebrate = window.kantoCelebrate;
        if (!celebrate) return;
        celebrate.fireworks(function () {});
        const today = season.indexOf('december') >= 0 ? 'nye' : 'bonfire';
        celebrate.toast(MESSAGES[today]);
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (reduced() || root.dataset.celebrations === 'off') return;
        const asked = meta.dataset.preview ? new URLSearchParams(window.location.search).get('celebrate') : null;
        if (asked === 'ghost') return ghost();
        if (asked === 'snow') return snow();
        if (asked === 'fireworks') return fireworks();
        if (asked === 'balloons') return balloons();
        if (asked === 'apple') return apple();
        if (asked === 'meme') return meme();
        if (OCCASION_ANIMATIONS[asked]) return OCCASION_ANIMATIONS[asked]();
        // Wait a moment so the page has drawn first
        setTimeout(function () {
            if (season.indexOf('balloons') >= 0 && chance('balloons')) balloons();
            else if (season.indexOf('fireworks') >= 0 && chance('fireworks')) fireworks();
            else if (season.indexOf('december') >= 0 && root.dataset.theme === 'festive' && chance('snow')) snow();
            else if (root.dataset.theme === 'haunted' && chance('ghost')) ghost();
            else if (root.dataset.theme === 'meme' && chance('meme')) meme();
            else if (season.indexOf('june') >= 0 && root.dataset.theme === 'pride' && chance('apple')) apple();
            else if (OCCASION_ANIMATIONS[root.dataset.theme] && chance('occasion_theme')) OCCASION_ANIMATIONS[root.dataset.theme]();
            else {
                const today = season.filter(function (p) { return p.indexOf('day-') === 0 && OCCASION_ANIMATIONS[p.slice(4)]; })[0];
                if (today && chance('occasion_day')) OCCASION_ANIMATIONS[today.slice(4)]();
            }
        }, 600);
    });
})();
