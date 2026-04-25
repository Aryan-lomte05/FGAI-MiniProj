// Type declaration for marked
declare const marked: any;

const API_BASE: string = 'http://127.0.0.1:8000/api';

if (!localStorage.getItem('token')) {
    window.location.href = 'login.html';
}

function getAuthHeaders(isJson = true): any {
    const h: any = { 'Authorization': `Bearer ${localStorage.getItem('token')}` };
    if (isJson) h['Content-Type'] = 'application/json';
    return h;
}

function handle401(res: Response) {
    if (res.status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        window.location.href = 'login.html';
        throw new Error('Unauthorized');
    }
}

let currentSessionId: string | null = null;

const chatEl = document.getElementById('chat') as HTMLDivElement;
const inputEl = document.getElementById('msg-input') as HTMLTextAreaElement;
const listEl = document.getElementById('session-list') as HTMLDivElement;
const titleEl = document.getElementById('chat-title') as HTMLHeadingElement;
const newBtn = document.getElementById('new-btn') as HTMLButtonElement;
const sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
const crisisBanner = document.getElementById('crisis-banner') as HTMLDivElement;
const micBtn = document.getElementById('mic-btn') as HTMLButtonElement;
const langSelect = document.getElementById('lang-select') as HTMLSelectElement;

let mediaRecorder: MediaRecorder | null = null;
let audioChunks: BlobPart[] = [];
let isRecording = false;
let currentAudio: HTMLAudioElement | null = null;

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

function appendMessage(role: string, content: string, isCrisis: boolean = false): HTMLElement {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role} ${isCrisis ? 'crisis' : ''} fade-in`;
  
  const sender = role === 'user' ? 'YOU' : (isCrisis ? 'SYSTEM RESPONSE' : 'MINDBRIDGE');
  
  // Use marked to parse markdown for assistant/crisis replies
  const htmlContent = (role === 'user') 
    ? `<p>${content.replace(/\n/g, '<br>')}</p>` 
    : marked.parse(content);

  wrapper.innerHTML = `
    <div class="msg-sender">
      ${sender}
      ${role !== 'user' ? `<button class="read-aloud-btn" title="Read Aloud" aria-label="Read Aloud">🔊</button>` : ''}
    </div>
    <div class="msg-bubble">${htmlContent}</div>
  `;
  chatEl.appendChild(wrapper);

  if (role !== 'user') {
    const btn = wrapper.querySelector('.read-aloud-btn') as HTMLButtonElement;
    if (btn) {
      btn.onclick = () => readAloud(content, btn);
    }
  }

  scrollToBottom();
  return wrapper;
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

// ── Voice Interactions ──────────────────────────────────────────────────

async function toggleRecording(): Promise<void> {
  if (isRecording && mediaRecorder) {
    mediaRecorder.stop();
    return;
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    
    mediaRecorder.onstop = async () => {
      isRecording = false;
      micBtn.classList.remove('listening');
      micBtn.style.animation = 'pulse 1.5s infinite'; // pulsing while uploading
      
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('file', audioBlob, 'audio.webm');
      
      try {
        const res = await fetch(`${API_BASE}/stt`, {
          method: 'POST',
          headers: getAuthHeaders(false),
          body: formData
        });
        handle401(res);
        
        if (!res.ok) {
          const err = await res.json();
          alert("STT Error: " + (err.detail || "Transcription failed"));
        } else {
          const data = await res.json();
          const transcript = data.text || '';
          if (transcript) {
            inputEl.value = inputEl.value + (inputEl.value && !inputEl.value.endsWith(' ') ? ' ' : '') + transcript;
            inputEl.focus();
          }
        }
      } catch (e) {
        console.error("STT Fetch Error:", e);
      } finally {
        micBtn.style.animation = ''; // stop pulse
        stream.getTracks().forEach(track => track.stop());
        mediaRecorder = null;
      }
    };
    
    mediaRecorder.start();
    isRecording = true;
    micBtn.classList.add('listening');
    
  } catch (err) {
    console.error("Error accessing mic:", err);
    alert("Microphone access is required for speech-to-text.");
  }
}

async function readAloud(text: string, btnElement?: HTMLButtonElement): Promise<void> {
  // Stop any currently playing audio
  if (currentAudio) {
    const wasPlaying = currentAudio;
    currentAudio.pause();
    currentAudio = null;
    document.querySelectorAll('.read-aloud-btn').forEach(btn => {
      btn.classList.remove('playing');
      (btn as HTMLElement).style.animation = '';
    });
    
    // If the same button was clicked to stop it
    if (btnElement && btnElement.classList.contains('playing')) {
      return; 
    }
  }
  
  // Clean markdown for speech
  const cleanText = text.replace(/[*#`~>_-]/g, '').trim();
  if (!cleanText) return;
  
  if (btnElement) {
    btnElement.classList.add('playing');
    btnElement.style.animation = 'pulse 1.5s infinite'; // visual feedback while fetching
  }

  try {
    const res = await fetch(`${API_BASE}/tts`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ text: cleanText })
    });
    handle401(res);

    if (!res.ok) {
      const err = await res.json();
      console.error("TTS Error:", err);
      alert(err.detail || "Could not generate audio. Ensure ElevenLabs API key is configured.");
      if (btnElement) {
        btnElement.classList.remove('playing');
        btnElement.style.animation = '';
      }
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    
    currentAudio = new Audio(url);
    currentAudio.onended = () => {
      if (btnElement) {
        btnElement.classList.remove('playing');
        btnElement.style.animation = '';
      }
      URL.revokeObjectURL(url);
      currentAudio = null;
    };
    currentAudio.onerror = () => {
      if (btnElement) {
        btnElement.classList.remove('playing');
        btnElement.style.animation = '';
      }
      URL.revokeObjectURL(url);
      currentAudio = null;
    };

    if (btnElement) btnElement.style.animation = ''; // stop pulse
    await currentAudio.play();
    
  } catch (e) {
    console.error(e);
    if (btnElement) {
      btnElement.classList.remove('playing');
      btnElement.style.animation = '';
    }
  }
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
    const res = await fetch(`${API_BASE}/sessions`, { headers: getAuthHeaders() });
    handle401(res);
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
    const res = await fetch(`${API_BASE}/sessions/${sid}/messages`, { headers: getAuthHeaders() });
    handle401(res);
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
  const userMsgEl = appendMessage('user', text);

  // Create session on first message if needed
  if (!currentSessionId) {
    try {
      const sRes = await fetch(`${API_BASE}/sessions/new`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({title: text.substring(0, 30)})
      });
      handle401(sRes);
      const sData = await sRes.json();
      currentSessionId = sData.session_id;
    } catch (e) {
      console.error("Failed to create session", e);
      return;
    }
  }

  const typingId = showTyping();

  try {
    const languageText = langSelect.options[langSelect.selectedIndex].text;
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        session_id: currentSessionId,
        message: text,
        language: languageText
      })
    });
    handle401(res);
    
    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }
    
    const data = await res.json();
    document.getElementById(typingId)?.remove();
    
    if (data.emotion) {
      const senderDiv = userMsgEl.querySelector('.msg-sender');
      if (senderDiv) {
        const badge = document.createElement('span');
        badge.className = 'emotion-badge fade-in';
        badge.textContent = `${data.emotion}`;
        senderDiv.appendChild(badge);
      }
    }
    
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
if (micBtn) micBtn.addEventListener('click', toggleRecording);
if (langSelect) langSelect.addEventListener('change', () => {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
  }
});

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

// Expose logout
(window as any).logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    window.location.href = 'login.html';
};
