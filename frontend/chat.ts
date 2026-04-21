// Type declaration for marked
declare const marked: any;

// Configuration
const API_BASE: string = 'http://127.0.0.1:8000/api';
let currentSessionId: string | null = null;

const chatEl = document.getElementById('chat') as HTMLDivElement;
const inputEl = document.getElementById('msg-input') as HTMLTextAreaElement;
const listEl = document.getElementById('session-list') as HTMLDivElement;
const titleEl = document.getElementById('chat-title') as HTMLHeadingElement;
const newBtn = document.getElementById('new-btn') as HTMLButtonElement;
const sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
const crisisBanner = document.getElementById('crisis-banner') as HTMLDivElement;

interface Session {
  _id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'crisis';
  content: string;
  crisis_triggered?: boolean;
}

// ── UI Helpers ────────────────────────────────────────────────────────

function scrollToBottom(): void {
  chatEl.scrollTop = chatEl.scrollHeight;
}

function appendMessage(role: string, content: string, isCrisis: boolean = false): void {
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

function showTyping(): string {
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

function createNewSession(): void {
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

async function loadSessions(): Promise<Session[]> {
  try {
    const res = await fetch(`${API_BASE}/sessions`);
    const data = await res.json();
    return data.sessions || [];
  } catch (e) { 
    console.error(e); 
    return []; 
  }
}

async function renderSidebar(): Promise<void> {
  const sessions = await loadSessions();
  listEl.innerHTML = '';
  sessions.forEach(s => {
    const div = document.createElement('div');
    div.className = `session-item ${s._id === currentSessionId ? 'active' : ''}`;
    div.textContent = s.title || "Untitled Chat";
    div.onclick = () => loadSessionHistory(s._id, s.title);
    listEl.appendChild(div);
  });
}

async function loadSessionHistory(sid: string, title: string): Promise<void> {
  currentSessionId = sid;
  titleEl.textContent = title || "Chat";
  chatEl.innerHTML = '';
  
  try {
    const res = await fetch(`${API_BASE}/sessions/${sid}/messages`);
    const data = await res.json();
    data.messages.forEach((m: ChatMessage) => {
      appendMessage(m.role, m.content, m.crisis_triggered);
    });
    scrollToBottom();
    renderSidebar();
  } catch (e) {
    console.error(e);
  }
}

async function sendMessage(): Promise<void> {
  const text = inputEl.value.trim();
  if (!text) return;

  // Optimistic UI update
  inputEl.value = '';
  appendMessage('user', text);

  // Create session on first message if needed
  if (!currentSessionId) {
    try {
      const sRes = await fetch(`${API_BASE}/sessions/new`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: text.substring(0, 30)})
      });
      const sData = await sRes.json();
      currentSessionId = sData.session_id;
    } catch (e) {
      console.error("Failed to create session", e);
      return;
    }
  }

  const typingId = showTyping();

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        session_id: currentSessionId,
        message: text
      })
    });
    
    const data = await res.json();
    document.getElementById(typingId)?.remove();
    
    appendMessage('assistant', data.response, data.crisis_triggered);
    
    if (data.crisis_triggered) {
      crisisBanner.style.display = 'flex';
    }
    
    renderSidebar(); // Update titles
    
  } catch (e) {
    document.getElementById(typingId)?.remove();
    appendMessage('assistant', "I'm having trouble connecting to the server. Please try again.");
  }
}

// ── Event Listeners ───────────────────────────────────────────────────

newBtn.addEventListener('click', createNewSession);
sendBtn.addEventListener('click', sendMessage);

inputEl.addEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Expose dismiss function for the crisis banner's inline onclick
(window as any).dismissCrisis = () => {
    crisisBanner.style.display = 'none';
};

// Initial load
renderSidebar();
