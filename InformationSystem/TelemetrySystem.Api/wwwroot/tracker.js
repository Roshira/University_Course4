(function () {
    const backendUrl = window.TeleBackendUrl || "https://localhost:7236/api/telemetry/track";
    const appId = window.TeleAppId;

    let sessionId = sessionStorage.getItem("telemetry_session");
    if (!sessionId) {
        sessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2);
        sessionStorage.setItem("telemetry_session", sessionId);
    }

    function isUkrainian(text) {
        return /[а-щА-ЩЬьЮюЯяЇїІіЄєҐґ]/.test(text);
    }

    function sendEvent(eventType, elementTag = null) {
        if (!appId || !elementTag) return;
        fetch(backendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                appId: appId,
                sessionId: sessionId,
                eventType: eventType,
                url: window.location.pathname,
                elementTag: elementTag
            })
        }).catch(e => console.error("Telemetry error:", e));
    }

    sendEvent("page_view", "Перегляд сторінки");

    document.addEventListener("click", function (e) {
        let target = e.target;
        let resultName = "";

        const btnOrLink = target.closest('button, a');
        if (btnOrLink) {
            resultName = btnOrLink.innerText.trim();
        }

        if (!resultName && target.tagName === 'INPUT') {
            const parent = target.closest('.form-group');
            const label = parent ? parent.querySelector('label') : null;

            if (label) {
                resultName = "Поле: " + label.innerText.trim();
            } else {
                resultName = "Поле: " + (target.placeholder || target.name || "без назви");
            }
        }

        if (!resultName && target.tagName === 'LABEL') {
            resultName = target.innerText.trim();
        }

        if (!resultName || !isUkrainian(resultName) || resultName.startsWith('.') || resultName.length > 50) {
            return;
        }

        resultName = resultName.replace(/\s\s+/g, ' ').replace(/\n/g, ' ');

        console.log("%c [TELEMETRY] Відправлено клік: " + resultName, "color: #1a237e; font-weight: bold");
        sendEvent("click", resultName);
    }, true);
})();