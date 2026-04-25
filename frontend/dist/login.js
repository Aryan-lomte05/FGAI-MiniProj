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
const AUTH_API_BASE = 'http://127.0.0.1:8000/api';
const authForm = document.getElementById('auth-form');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const submitBtn = document.getElementById('submit-btn');
const toggleLink = document.getElementById('toggle-link');
const toggleText = document.getElementById('toggle-text');
const headerTitle = document.querySelector('.auth-header h1');
const errorMsg = document.getElementById('error-msg');
let isLoginMode = true;
toggleLink.addEventListener('click', () => {
    isLoginMode = !isLoginMode;
    if (isLoginMode) {
        headerTitle.textContent = 'Login';
        submitBtn.textContent = 'LOGIN';
        toggleText.textContent = "Don't have an account?";
        toggleLink.textContent = 'Register';
    }
    else {
        headerTitle.textContent = 'Register';
        submitBtn.textContent = 'CREATE ACCOUNT';
        toggleText.textContent = "Already have an account?";
        toggleLink.textContent = 'Login';
    }
    errorMsg.style.display = 'none';
});
authForm.addEventListener('submit', (e) => __awaiter(void 0, void 0, void 0, function* () {
    e.preventDefault();
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!username || !password)
        return;
    submitBtn.disabled = true;
    errorMsg.style.display = 'none';
    try {
        if (isLoginMode) {
            const res = yield fetch(`${AUTH_API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = yield res.json();
            if (!res.ok)
                throw new Error(data.detail || 'Login failed');
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('username', data.username);
            window.location.href = 'chat.html';
        }
        else {
            const res = yield fetch(`${AUTH_API_BASE}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = yield res.json();
            if (!res.ok)
                throw new Error(data.detail || 'Registration failed');
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
    }
    catch (err) {
        errorMsg.style.color = 'var(--crisis)';
        errorMsg.textContent = err.message;
        errorMsg.style.display = 'block';
    }
    finally {
        submitBtn.disabled = false;
    }
}));
