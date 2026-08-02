// CS-Style Event Feed Overlay
(function() {
    // Inject Event Feed CSS Styles
    const style = document.createElement('style');
    style.innerHTML = `
        .event-feed-overlay {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 8px;
            pointer-events: none;
            max-width: 380px;
            width: 100%;
        }

        .feed-item {
            background: rgba(19, 20, 27, 0.9);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 12px 16px;
            color: #f3f4f6;
            font-size: 13px;
            font-family: 'Inter', sans-serif;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
            display: flex;
            align-items: flex-start;
            gap: 12px;
            pointer-events: auto;
            transform: translateX(120%);
            opacity: 0;
            animation: slideInFeed 0.3s cubic-bezier(0.1, 0.8, 0.25, 1) forwards,
                       fadeOutFeed 0.5s ease forwards 5.5s;
        }

        .feed-icon {
            font-size: 18px;
            line-height: 1;
            flex-shrink: 0;
            margin-top: 1px;
        }

        .feed-text {
            line-height: 1.4;
            flex: 1;
        }

        .feed-text strong {
            color: #fff;
            font-weight: 700;
        }

        /* Event Specific Accents */
        .feed-item.punish {
            border-color: rgba(239, 68, 68, 0.25);
            background: rgba(239, 68, 68, 0.08);
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.05), 0 10px 30px rgba(0, 0, 0, 0.4);
        }

        .feed-item.trigger {
            border-color: rgba(245, 158, 11, 0.25);
            background: rgba(245, 158, 11, 0.08);
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.05), 0 10px 30px rgba(0, 0, 0, 0.4);
        }

        .feed-item.info {
            border-color: rgba(59, 130, 246, 0.25);
            background: rgba(59, 130, 246, 0.08);
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.05), 0 10px 30px rgba(0, 0, 0, 0.4);
        }

        @keyframes slideInFeed {
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes fadeOutFeed {
            to {
                opacity: 0;
                transform: translateY(-12px);
            }
        }
    `;
    document.head.appendChild(style);
})();

// Floating Feed manager
function pushFeedItem(type, icon, htmlContent) {
    let feedContainer = document.getElementById('event-feed-container');
    if (!feedContainer) {
        feedContainer = document.createElement('div');
        feedContainer.id = 'event-feed-container';
        feedContainer.className = 'event-feed-overlay';
        document.body.appendChild(feedContainer);
    }

    const item = document.createElement('div');
    item.className = `feed-item ${type}`;
    item.innerHTML = `
        <span class="feed-icon">${icon}</span>
        <div class="feed-text">${htmlContent}</div>
    `;

    feedContainer.appendChild(item);

    // Auto-remove element from DOM after fadeOut animation finishes (6 seconds total)
    setTimeout(() => {
        item.remove();
    }, 6000);
}
