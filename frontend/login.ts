const AUTH_API_BASE: string = 'http://127.0.0.1:8000/api';

const authForm = document.getElementById('auth-form') as HTMLFormElement;
const usernameInput = document.getElementById('username') as HTMLInputElement;
const passwordInput = document.getElementById('password') as HTMLInputElement;
const submitBtn = document.getElementById('submit-btn') as HTMLButtonElement;
const toggleLink = document.getElementById('toggle-link') as HTMLAnchorElement;
const toggleText = document.getElementById('toggle-text') as HTMLSpanElement;
const headerTitle = document.querySelector('.auth-header h1') as HTMLHeadingElement;
const errorMsg = document.getElementById('error-msg') as HTMLDivElement;

let isLoginMode = true;

toggleLink.addEventListener('click', () => {
    isLoginMode = !isLoginMode;
    if (isLoginMode) {
        headerTitle.textContent = 'Login';
        submitBtn.textContent = 'LOGIN';
        toggleText.textContent = "Don't have an account?";
        toggleLink.textContent = 'Register';
    } else {
        headerTitle.textContent = 'Register';
        submitBtn.textContent = 'CREATE ACCOUNT';
        toggleText.textContent = "Already have an account?";
        toggleLink.textContent = 'Login';
    }
    errorMsg.style.display = 'none';
});

authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    
    if (!username || !password) return;
    
    submitBtn.disabled = true;
    errorMsg.style.display = 'none';
    
    try {
        if (isLoginMode) {
            const res = await fetch(`${AUTH_API_BASE}/auth/login`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Login failed');
            
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('username', data.username);
            window.location.href = 'chat.html';
        } else {
            const res = await fetch(`${AUTH_API_BASE}/auth/register`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Registration failed');
            
            // Switch to login mode on success
            isLoginMode = true;
            headerTitle.textContent = 'Login';
            submitBtn.textContent = 'LOGIN';
            toggleText.textContent = "Don't have an account?";
            toggleLink.textContent = 'Register';
            errorMsg.style.color = 'green';
            errorMsg.textContent = 'Registration successful! Please login.';
            errorMsg.style.display = 'block';
        }
    } catch (err: any) {
        errorMsg.style.color = 'var(--crisis)';
        errorMsg.textContent = err.message;
        errorMsg.style.display = 'block';
    } finally {
        submitBtn.disabled = false;
    }
});
