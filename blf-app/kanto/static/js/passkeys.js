// Passkeys (WebAuthn): adding one on the profile page, and signing in with one.
// The server sends options with binary fields as base64url; the browser API wants bytes, and back again.
(function () {
    const supported = window.PublicKeyCredential && window.isSecureContext;

    const toBytes = (text) => {
        const b64 = text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - text.length % 4) % 4);
        return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    };
    const toText = (buffer) => btoa(String.fromCharCode(...new Uint8Array(buffer)))
        .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    // Go to the address the server sent. When it's this same page with only a different #part (e.g. /profile#security
    // from the profile), setting location.href would just scroll, keeping the old page: its messages, its list of
    // passkeys and its form tokens (the session was renewed), so reload it instead.
    function go(url) {
        const target = new URL(url, window.location.href);
        if (target.pathname === window.location.pathname && target.search === window.location.search) {
            window.location.hash = target.hash;
            window.location.reload();
        } else {
            window.location.href = target.href;
        }
    }

    async function post(url, body) {
        const csrf = document.querySelector('meta[name="csrf-token"]');
        const response = await fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf ? csrf.content : '' },
            body: JSON.stringify(body || {}),
        });
        let data = {};
        try { data = await response.json(); } catch (e) { /* not JSON, e.g. an error page */ }
        if (!response.ok) {
            if (data.redirect) go(data.redirect);
            throw new Error(data.error || 'Something went wrong. Reload the page and try again.');
        }
        return data;
    }

    // signingIn: the browser reports "not allowed" when someone cancels, when the prompt can't open (Windows allows
    // one passkey window at a time), and when this device has no passkey for the site, so say what to try next
    function showError(box, error, signingIn) {
        if (!box) return;
        if (error.name === 'NotAllowedError' && signingIn) {
            box.textContent = 'No passkey was used. If a passkey or Windows Security window is already open somewhere, ' +
                'close it and try again. If your passkey is on another device, such as your phone, choose ' +
                '"Use a phone or tablet" in the prompt and scan the code (this computer needs Bluetooth on).' +
                (box.dataset.passkeyFallback ? ' ' + box.dataset.passkeyFallback : '');
        } else if (error.name === 'NotAllowedError') {
            box.textContent = 'Cancelled, or the passkey prompt timed out.';
        } else if (error.name === 'InvalidStateError') {
            box.textContent = 'This device already has a passkey for your account.';
        } else {
            box.textContent = error.message;
        }
        box.classList.remove('hidden');
    }

    // Show the passkey controls only where the browser can use them
    document.querySelectorAll('[data-passkey-supported]').forEach((el) => el.classList.toggle('hidden', !supported));
    document.querySelectorAll('[data-passkey-unsupported]').forEach((el) => el.classList.toggle('hidden', !!supported));
    if (!supported) return;

    const addForm = document.querySelector('form[data-passkey-add]');
    if (addForm) {
        addForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const button = addForm.querySelector('button');
            const errorBox = addForm.querySelector('[data-passkey-error]');
            errorBox.classList.add('hidden');
            button.disabled = true;
            try {
                const options = await post(addForm.dataset.optionsUrl);
                options.challenge = toBytes(options.challenge);
                options.user.id = toBytes(options.user.id);
                (options.excludeCredentials || []).forEach((c) => { c.id = toBytes(c.id); });
                const created = await navigator.credentials.create({ publicKey: options });
                const credential = {
                    id: created.id, rawId: toText(created.rawId), type: created.type,
                    authenticatorAttachment: created.authenticatorAttachment,
                    clientExtensionResults: created.getClientExtensionResults(),
                    response: {
                        clientDataJSON: toText(created.response.clientDataJSON),
                        attestationObject: toText(created.response.attestationObject),
                        transports: created.response.getTransports ? created.response.getTransports() : [],
                    },
                };
                const result = await post(addForm.action, { credential, name: addForm.elements.name.value });
                go(result.redirect);
            } catch (error) {
                showError(errorBox, error);
                button.disabled = false;
            }
        });
    }

    document.querySelectorAll('button[data-passkey-login]').forEach((button) => {
        const errorBox = document.querySelector('[data-passkey-error]');
        button.addEventListener('click', async () => {
            if (errorBox) errorBox.classList.add('hidden');
            button.disabled = true;
            try {
                const options = await post(button.dataset.optionsUrl, { second_step: 'secondStep' in button.dataset });
                options.challenge = toBytes(options.challenge);
                (options.allowCredentials || []).forEach((c) => { c.id = toBytes(c.id); });
                const signed = await navigator.credentials.get({ publicKey: options });
                const result = await post(button.dataset.url, {
                    id: signed.id, rawId: toText(signed.rawId), type: signed.type,
                    authenticatorAttachment: signed.authenticatorAttachment,
                    clientExtensionResults: signed.getClientExtensionResults(),
                    response: {
                        clientDataJSON: toText(signed.response.clientDataJSON),
                        authenticatorData: toText(signed.response.authenticatorData),
                        signature: toText(signed.response.signature),
                        userHandle: signed.response.userHandle ? toText(signed.response.userHandle) : null,
                    },
                });
                go(result.redirect);
            } catch (error) {
                showError(errorBox, error, true);
                button.disabled = false;
            }
        });
    });
})();
