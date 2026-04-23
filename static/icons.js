/**
 * Icon System - SVG Icons แทน Emoji
 * ใช้งาน: Icons.dashboard(), Icons.chart(), etc.
 */

const Icons = {
    // Navigation Icons
    dashboard: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1"></rect>
            <rect x="14" y="3" width="7" height="7" rx="1"></rect>
            <rect x="14" y="14" width="7" height="7" rx="1"></rect>
            <rect x="3" y="14" width="7" height="7" rx="1"></rect>
        </svg>
    `,

    chart: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
    `,

    history: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 3h18"></path>
            <path d="M3 9h18"></path>
            <path d="M3 15h18"></path>
            <path d="M3 21h18"></path>
        </svg>
    `,

    agent: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="8" r="4"></circle>
            <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"></path>
        </svg>
    `,

    log: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
        </svg>
    `,

    bulb: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 18h6"></path>
            <path d="M10 22h4"></path>
            <path d="M15 8a5 5 0 1 0-6 0c0 3 2 4 2 4v2h2v-2s2-1 2-4z"></path>
        </svg>
    `,

    settings: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M12 1v6m0 6v6M5.64 5.64l4.24 4.24m4.24 4.24l4.24 4.24M1 12h6m6 0h6M5.64 18.36l4.24-4.24m4.24-4.24l4.24-4.24"></path>
        </svg>
    `,

    // Mode Icons
    paper: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
    `,

    micro: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="10" fill="#ffaa00"/>
            <text x="12" y="16" text-anchor="middle" fill="#000" font-size="10" font-weight="bold">μ</text>
        </svg>
    `,

    live: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="10" fill="#00ff88"/>
            <circle cx="12" cy="12" r="6" fill="#000"/>
            <circle cx="12" cy="12" r="3" fill="#00ff88"/>
        </svg>
    `,

    // Control Icons
    play: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
    `,

    pause: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16"></rect>
            <rect x="14" y="4" width="4" height="16"></rect>
        </svg>
    `,

    emergency: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-10-5z" fill="#ff4444"/>
            <path d="M10 17l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="#fff"/>
        </svg>
    `,

    // Data Source Icons
    mt5: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <rect x="4" y="6" width="4" height="12" fill="#00ff88"/>
            <rect x="10" y="3" width="4" height="15" fill="#00ff88"/>
            <rect x="16" y="9" width="4" height="9" fill="#00ff88"/>
        </svg>
    `,

    tv: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="7" width="20" height="13" rx="2"></rect>
            <polyline points="17 2 12 7 7 2"></polyline>
        </svg>
    `,

    yfinance: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#00aaff" stroke-width="2" fill="none"/>
        </svg>
    `,

    auto: () => `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"></polyline>
            <polyline points="1 20 1 14 7 14"></polyline>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
        </svg>
    `,

    // Agent Avatars (ใช้จาก sprite sheet)
    agentAvatar: (agentType) => `
        <svg class="agent-avatar" viewBox="0 0 64 64">
            <use href="/static/agent-avatars.svg#${agentType}"></use>
        </svg>
    `,
};

// Helper function สำหรับสร้าง icon element
function icon(name, className = '') {
    const div = document.createElement('div');
    div.innerHTML = Icons[name]();
    const svg = div.firstElementChild;
    if (className) {
        svg.classList.add(...className.split(' '));
    }
    return svg.outerHTML;
}

// Export for Alpine.js
window.Icons = Icons;
window.icon = icon;
