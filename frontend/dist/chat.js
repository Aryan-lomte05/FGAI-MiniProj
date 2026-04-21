"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
// Configuration
const API_BASE = 'http://127.0.0.1:8000/api';
let currentSessionId = null;
const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('msg-input');
const listEl = document.getElementById('session-list');
const titleEl = document.getElementById('chat-title');
const newBtn = document.getElementById('new-btn');
const sendBtn = document.getElementById('send-btn');
const crisisBanner = document.getElementById('crisis-banner');
// ── UI Helpers ────────────────────────────────────────────────────────
function scrollToBottom() {
    chatEl.scrollTop = chatEl.scrollHeight;
}
function appendMessage(role, content, isCrisis = false) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role} ${isCrisis ? 'crisis' : ''} fade-in`;
    const sender = role === 'user' ? 'YOU' : (isCrisis ? 'SYSTEM RESPONSE' : 'MINDBRIDGE');
    // Use marked to parse markdown for assistant/crisis replies
    const htmlContent = (role === 'user')
        ? `<p>${content.replace(/\n/g, '<br>')}</p>`
        : marked.parse(content);
    wrapper.innerHTML = `
    <div class="msg-sender">${sender}</div>
    <div class="msg-bubble">${htmlContent}</div>
  `;
    chatEl.appendChild(wrapper);
    scrollToBottom();
}
function showTyping() {
    const id = 'typing-' + Date.now();
    const wrapper = document.createElement('div');
    wrapper.className = 'message assistant fade-in';
    wrapper.id = id;
    wrapper.innerHTML = `
    <div class="msg-sender">MINDBRIDGE</div>
    <div class="msg-bubble typing-dots">
      <span></span><span></span><span></span>
    </div>
  `;
    chatEl.appendChild(wrapper);
    scrollToBottom();
    return id;
}
// ── API Interactions ──────────────────────────────────────────────────
function createNewSession() {
    currentSessionId = null;
    titleEl.textContent = "New Conversation";
    chatEl.innerHTML = `
    <div class="message assistant fade-in">
      <div class="msg-sender">MindBridge Core</div>
      <div class="msg-bubble">
        <p>Hi there. I'm MindBridge. I'm an AI designed to listen, help you figure out what you're feeling, and share some tools that might help.</p>
        <p>What's going on for you today?</p>
      </div>
    </div>
  `;
    renderSidebar();
}
function loadSessions() {
    return __awaiter(this, void 0, void 0, function* () {
        try {
            const res = yield fetch(`${API_BASE}/sessions`);
            const data = yield res.json();
            return data.sessions || [];
        }
        catch (e) {
            console.error(e);
            return [];
        }
    });
}
function renderSidebar() {
    return __awaiter(this, void 0, void 0, function* () {
        const sessions = yield loadSessions();
        listEl.innerHTML = '';
        sessions.forEach(s => {
            const div = document.createElement('div');
            div.className = `session-item ${s._id === currentSessionId ? 'active' : ''}`;
            div.textContent = s.title || "Untitled Chat";
            div.onclick = () => loadSessionHistory(s._id, s.title);
            listEl.appendChild(div);
        });
    });
}
function loadSessionHistory(sid, title) {
    return __awaiter(this, void 0, void 0, function* () {
        currentSessionId = sid;
        titleEl.textContent = title || "Chat";
        chatEl.innerHTML = '';
        try {
            const res = yield fetch(`${API_BASE}/sessions/${sid}/messages`);
            const data = yield res.json();
            data.messages.forEach((m) => {
                appendMessage(m.role, m.content, m.crisis_triggered);
            });
            scrollToBottom();
            renderSidebar();
        }
        catch (e) {
            console.error(e);
        }
    });
}
function sendMessage() {
    return __awaiter(this, void 0, void 0, function* () {
        var _a, _b;
        const text = inputEl.value.trim();
        if (!text)
            return;
        // Optimistic UI update
        inputEl.value = '';
        appendMessage('user', text);
        // Create session on first message if needed
        if (!currentSessionId) {
            try {
                const sRes = yield fetch(`${API_BASE}/sessions/new`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: text.substring(0, 30) })
                });
                const sData = yield sRes.json();
                currentSessionId = sData.session_id;
            }
            catch (e) {
                console.error("Failed to create session", e);
                return;
            }
        }
        const typingId = showTyping();
        try {
            const res = yield fetch(`${API_BASE}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: currentSessionId,
                    message: text
                })
            });
            const data = yield res.json();
            (_a = document.getElementById(typingId)) === null || _a === void 0 ? void 0 : _a.remove();
            appendMessage('assistant', data.response, data.crisis_triggered);
            if (data.crisis_triggered) {
                crisisBanner.style.display = 'flex';
            }
            renderSidebar(); // Update titles
        }
        catch (e) {
            (_b = document.getElementById(typingId)) === null || _b === void 0 ? void 0 : _b.remove();
            appendMessage('assistant', "I'm having trouble connecting to the server. Please try again.");
        }
    });
}
// ── Event Listeners ───────────────────────────────────────────────────
newBtn.addEventListener('click', createNewSession);
sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
// Expose dismiss function for the crisis banner's inline onclick
window.dismissCrisis = () => {
    crisisBanner.style.display = 'none';
};
// Initial load
renderSidebar();
