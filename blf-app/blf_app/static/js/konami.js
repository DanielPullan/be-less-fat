// Easter eggs, adapted from SecureMy.School:
//  - type ↑ ↑ ↓ ↓ ← → ← → B A anywhere (outside a form field) for fireworks
//  - type the new emergency number, 0118 999 881 999 119 725 3, to switch to the Frosted Glass theme
// Also shares fireworks() and toast() with seasonal.js (window.blfCelebrate).
(function () {
    const SEQUENCE = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
                      'ArrowLeft', 'ArrowRight', 'b', 'a'];
    const COLOURS = ['#ff5252', '#ffd740', '#69f0ae', '#40c4ff', '#e040fb', '#ffab40', '#ffffff'];
    const MESSAGES = [
        '30 extra lives granted. Calories unchanged.',
        'Cheat code accepted. Sadly it doesn\'t work on the scales.',
        'Achievement unlocked: knows the classics.',
        'Up, up, down, down… that\'s a lot of stairs. Well done.',
    ];
    const EMERGENCY = '01189998819991197253';
    let position = 0;
    let digits = '';
    let running = false;

    document.addEventListener('keydown', function (e) {
        const target = e.target;
        // Don't hijack typing: B and A are perfectly good letters in a food name
        if (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) {
            position = 0;
            digits = '';
            return;
        }
        const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
        digits = /^[0-9]$/.test(key) ? (digits + key).slice(-EMERGENCY.length) : '';
        if (digits === EMERGENCY) {
            digits = '';
            emergency();
        }
        if (key === SEQUENCE[position]) {
            position += 1;
            if (position === SEQUENCE.length) {
                position = 0;
                celebrate();
            }
        } else {
            position = key === SEQUENCE[0] ? 1 : 0;
        }
    });

    function emergency() {
        if (window.blfDisplay) window.blfDisplay.set('theme', 'vista');
        toast('Emergency services notified. Frosted Glass theme on: change it back in the Aa menu.');
    }

    function celebrate() {
        if (running) return;
        running = true;
        // The Display menu's "Reduce motion" sets data-motion on <html>; it also mirrors the device setting
        const reduced = document.documentElement.dataset.motion === 'reduce' ||
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        toast(MESSAGES[Math.floor(Math.random() * MESSAGES.length)]);
        if (reduced) {
            setTimeout(function () { running = false; }, 3000);
            return;
        }
        fireworks(function () { running = false; });
    }

    function toast(text) {
        const el = document.createElement('div');
        el.setAttribute('role', 'status');
        el.textContent = '🎆 ' + text;
        el.style.cssText = 'position:fixed;left:50%;bottom:32px;transform:translateX(-50%) translateY(20px);' +
            'z-index:10001;background:#0f172a;color:#fff;font:600 14px/1.4 system-ui,sans-serif;' +
            'padding:12px 18px;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.3);opacity:0;' +
            'transition:opacity .3s,transform .3s;max-width:calc(100vw - 32px);text-align:center;';
        document.body.appendChild(el);
        requestAnimationFrame(function () { el.style.opacity = '1'; el.style.transform = 'translateX(-50%)'; });
        setTimeout(function () {
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 400);
        }, 3800);
    }

    function fireworks(done) {
        const canvas = document.createElement('canvas');
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;z-index:10000;pointer-events:none;';
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

        const W = function () { return window.innerWidth; };
        const H = function () { return window.innerHeight; };
        const rockets = [];
        const sparks = [];
        const SHOW_MS = 4500;
        const start = performance.now();
        let nextLaunch = 0;

        function launch() {
            const x = W() * (0.15 + Math.random() * 0.7);
            rockets.push({
                x: x, y: H(), vx: (Math.random() - 0.5) * 1.5,
                vy: -(H() * 0.012 + Math.random() * 3 + 6),
                targetY: H() * (0.15 + Math.random() * 0.35),
                colour: COLOURS[Math.floor(Math.random() * COLOURS.length)],
            });
        }

        function explode(r) {
            const count = 70 + Math.floor(Math.random() * 40);
            const ring = Math.random() < 0.3;  // some bursts are neat rings
            const second = COLOURS[Math.floor(Math.random() * COLOURS.length)];
            for (let i = 0; i < count; i++) {
                const angle = (Math.PI * 2 * i) / count;
                const speed = ring ? 4.5 : 1 + Math.random() * 5;
                sparks.push({
                    x: r.x, y: r.y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
                    life: 1, decay: 0.012 + Math.random() * 0.012,
                    colour: Math.random() < 0.7 ? r.colour : second,
                    size: 1.5 + Math.random() * 1.5,
                });
            }
        }

        function frame(now) {
            const elapsed = now - start;
            if (elapsed < SHOW_MS && now >= nextLaunch) {
                launch();
                if (Math.random() < 0.35) launch();
                nextLaunch = now + 250 + Math.random() * 350;
            }
            ctx.clearRect(0, 0, W(), H());
            ctx.globalCompositeOperation = 'lighter';

            for (let i = rockets.length - 1; i >= 0; i--) {
                const r = rockets[i];
                r.x += r.vx;
                r.y += r.vy;
                r.vy += 0.12;
                ctx.fillStyle = r.colour;
                ctx.beginPath();
                ctx.arc(r.x, r.y, 2.5, 0, Math.PI * 2);
                ctx.fill();
                if (r.y <= r.targetY || r.vy >= 0) {
                    explode(r);
                    rockets.splice(i, 1);
                }
            }
            for (let i = sparks.length - 1; i >= 0; i--) {
                const s = sparks[i];
                s.vx *= 0.985;
                s.vy = s.vy * 0.985 + 0.06;
                s.x += s.vx;
                s.y += s.vy;
                s.life -= s.decay;
                if (s.life <= 0) {
                    sparks.splice(i, 1);
                    continue;
                }
                ctx.globalAlpha = s.life;
                ctx.fillStyle = s.colour;
                ctx.beginPath();
                ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.globalAlpha = 1;
            ctx.globalCompositeOperation = 'source-over';

            if (elapsed < SHOW_MS || rockets.length || sparks.length) {
                requestAnimationFrame(frame);
            } else {
                window.removeEventListener('resize', resize);
                canvas.remove();
                done();
            }
        }
        requestAnimationFrame(frame);
    }

    // Shared with seasonal.js (Bonfire Night and New Year's Eve)
    window.blfCelebrate = { fireworks: fireworks, toast: toast };
})();
