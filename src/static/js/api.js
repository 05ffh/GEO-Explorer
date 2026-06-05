/* GEO Explorer — Unified API client + toast + confirm utilities */

/**
 * Unified fetch wrapper. Automatically injects auth token,
 * handles 401/403/5xx uniformly, and parses JSON.
 */
async function geoFetch(url, options = {}) {
    const token = localStorage.getItem('geo_token');
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
        ...(token ? { 'Authorization': 'Bearer ' + token } : {}),
    };

    let res;
    try {
        res = await fetch(url, { ...options, headers });
    } catch (err) {
        showToast('网络错误，请检查连接', 'error');
        throw err;
    }

    if (res.status === 401) {
        localStorage.removeItem('geo_token');
        localStorage.removeItem('geo_user');
        window.location.href = '/login';
        throw new Error('未登录或登录已过期');
    }

    if (res.status === 403) {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || '没有权限执行该操作', 'error');
        throw new Error(data.detail || '没有权限');
    }

    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const msg = data.detail || '请求失败 (' + res.status + ')';
        showToast(msg, 'error');
        throw new Error(msg);
    }

    return await res.json();
}

/**
 * Show a toast notification.
 * @param {string} message
 * @param {'error'|'success'|'info'} type
 */
function showToast(message, type) {
    var container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed bottom-4 right-4 z-50 space-y-2';
        document.body.appendChild(container);
    }
    var colors = {
        error: 'bg-red-100 border-red-300 text-red-800',
        success: 'bg-green-100 border-green-300 text-green-800',
        info: 'bg-blue-100 border-blue-300 text-blue-800',
    };
    var toast = document.createElement('div');
    toast.className = (colors[type] || colors.info) + ' border px-4 py-2 rounded-lg shadow text-sm';
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 5000);
}

/**
 * Show a confirmation dialog and execute action on confirm.
 * @param {string} message
 * @param {string} reasonLabel - label for the required reason input
 * @returns {Promise<{confirmed: boolean, reason: string}>}
 */
function confirmAction(message, reasonLabel) {
    return new Promise(function (resolve) {
        var reason = reasonLabel ? prompt(message + '\n\n' + reasonLabel + ':') : confirm(message);
        if (reasonLabel) {
            resolve({ confirmed: reason !== null && reason.trim() !== '', reason: reason || '' });
        } else {
            resolve({ confirmed: !!reason, reason: '' });
        }
    });
}

/**
 * Escape HTML entities to prevent XSS when rendering user content.
 */
function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Safely set text content of an element (XSS-safe).
 */
function safeText(el, text) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (el) el.textContent = text;
}
