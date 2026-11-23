/**
 * AdversarialIQ V4.5 - Authentication, Session & User Management Module
 * Manages JWT tokens, header status, admin user provisioning, and Langfuse cloud telemetry checks.
 */

class AdversarialAuth {
  constructor() {
    this.tokenKey = 'adversarialiq_token';
    this.userKey = 'adversarialiq_user';
    this.currentUser = null;
    this.init();
  }

  init() {
    this.loadSession();
    this.bindEvents();
    this.checkSessionValidity();
    this.fetchLangfuseTelemetry();
  }

  getToken() {
    return localStorage.getItem(this.tokenKey);
  }

  setSession(token, user) {
    localStorage.setItem(this.tokenKey, token);
    localStorage.setItem(this.userKey, JSON.stringify(user));
    this.currentUser = user;
    this.updateUI();
  }

  clearSession() {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.userKey);
    this.currentUser = null;
    this.updateUI();
  }

  loadSession() {
    try {
      const userStr = localStorage.getItem(this.userKey);
      if (userStr) {
        this.currentUser = JSON.parse(userStr);
      }
    } catch (e) {
      this.clearSession();
    }
    this.updateUI();
  }

  async checkSessionValidity() {
    const token = this.getToken();
    if (!token) return;

    try {
      const res = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        if (data && data.user) {
          this.currentUser = data.user;
          localStorage.setItem(this.userKey, JSON.stringify(data.user));
          this.updateUI();
        }
      } else if (res.status === 401) {
        console.warn('Session expired, clearing credentials.');
        this.clearSession();
      }
    } catch (e) {
      console.debug('Auth check offline notice:', e);
    }
  }

  updateUI() {
    const label = document.getElementById('user-display-label');
    const loggedInBox = document.getElementById('auth-logged-in-box');
    const loginForm = document.getElementById('form-auth-login');
    const usersTabBtn = document.getElementById('tab-btn-auth-users');
    const activeUsername = document.getElementById('auth-active-username');
    const activeRole = document.getElementById('auth-active-role');

    if (this.currentUser && this.getToken()) {
      if (label) {
        label.textContent = `${this.currentUser.username.toUpperCase()} [${this.currentUser.role.toUpperCase()}]`;
      }
      if (loggedInBox) loggedInBox.style.display = 'block';
      if (loginForm) loginForm.style.display = 'none';
      if (activeUsername) activeUsername.textContent = this.currentUser.username;
      if (activeRole) {
        activeRole.textContent = this.currentUser.role.toUpperCase();
        activeRole.style.background = this.currentUser.role === 'admin' ? '#22c55e' : '#38bdf8';
      }

      // Show admin user tab only if role is admin
      if (usersTabBtn) {
        usersTabBtn.style.display = this.currentUser.role === 'admin' ? 'inline-block' : 'none';
      }
    } else {
      if (label) label.textContent = 'LOGIN';
      if (loggedInBox) loggedInBox.style.display = 'none';
      if (loginForm) loginForm.style.display = 'block';
      if (usersTabBtn) usersTabBtn.style.display = 'none';
    }
  }

  bindEvents() {
    const openBtn = document.getElementById('btn-open-auth');
    const closeBtn = document.getElementById('btn-close-auth');
    const modal = document.getElementById('auth-modal');
    const loginForm = document.getElementById('form-auth-login');
    const logoutBtn = document.getElementById('btn-auth-logout');
    const addUserForm = document.getElementById('form-add-user');

    if (openBtn && modal) {
      openBtn.addEventListener('click', () => {
        modal.classList.add('open');
        modal.classList.add('active');
        if (this.currentUser && this.currentUser.role === 'admin') {
          this.loadUsersTable();
        }
      });
    }

    if (closeBtn && modal) {
      closeBtn.addEventListener('click', () => {
        modal.classList.remove('open');
        modal.classList.remove('active');
      });
    }

    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          modal.classList.remove('open');
          modal.classList.remove('active');
        }
      });
    }

    // Modal tabs switching
    const tabBtns = modal ? modal.querySelectorAll('.settings-tab-btn') : [];
    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const targetId = btn.dataset.tab;
        modal.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');
        const targetPane = document.getElementById(targetId);
        if (targetPane) targetPane.style.display = 'block';

        if (targetId === 'tab-auth-users') {
          this.loadUsersTable();
        }
      });
    });

    // Login Form Submit
    if (loginForm) {
      loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('auth-login-username').value.trim();
        const password = document.getElementById('auth-login-password').value;
        const statusEl = document.getElementById('auth-login-status');
        const submitBtn = document.getElementById('btn-submit-login');

        if (statusEl) {
          statusEl.textContent = 'Authenticating with security vault...';
          statusEl.style.color = 'var(--cyan-primary)';
        }
        if (submitBtn) submitBtn.disabled = true;

        try {
          const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
          });

          const data = await res.json();
          if (res.ok && data.access_token) {
            this.setSession(data.access_token, data.user);
            if (statusEl) {
              statusEl.textContent = `✓ Access granted. Welcome back, ${data.user.username}!`;
              statusEl.style.color = 'var(--green-up)';
            }
            loginForm.reset();
            setTimeout(() => {
              if (modal) modal.classList.remove('active');
            }, 800);
          } else {
            if (statusEl) {
              statusEl.textContent = `✗ Authentication rejected: ${data.detail || 'Invalid username or password'}`;
              statusEl.style.color = 'var(--red-down)';
            }
          }
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = `✗ Network error during login: ${err.message}`;
            statusEl.style.color = 'var(--red-down)';
          }
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
    }

    // Logout
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        this.clearSession();
        const statusEl = document.getElementById('auth-login-status');
        if (statusEl) {
          statusEl.textContent = 'Logged out. Sign in below.';
          statusEl.style.color = 'var(--text-muted)';
        }
      });
    }

    // Add User Form (Admin only)
    if (addUserForm) {
      addUserForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('new-user-name').value.trim();
        const password = document.getElementById('new-user-pass').value;
        const role = document.getElementById('new-user-role').value;
        const statusEl = document.getElementById('add-user-status');
        const submitBtn = document.getElementById('btn-create-user');

        if (statusEl) {
          statusEl.textContent = 'Provisioning new account...';
          statusEl.style.color = 'var(--cyan-primary)';
        }
        if (submitBtn) submitBtn.disabled = true;

        try {
          const res = await fetch('/api/auth/users', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${this.getToken()}`
            },
            body: JSON.stringify({ username, password, role })
          });

          const data = await res.json();
          if (res.ok) {
            if (statusEl) {
              statusEl.textContent = `✓ User '${data.user.username}' (${data.user.role}) created successfully!`;
              statusEl.style.color = 'var(--green-up)';
            }
            addUserForm.reset();
            this.loadUsersTable();
          } else {
            if (statusEl) {
              statusEl.textContent = `✗ Failed: ${data.detail || 'Could not create user'}`;
              statusEl.style.color = 'var(--red-down)';
            }
          }
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = `✗ Error: ${err.message}`;
            statusEl.style.color = 'var(--red-down)';
          }
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
    }

    // Refresh Traces button also re-fetches Langfuse telemetry
    const refreshTracesBtn = document.getElementById('btn-refresh-traces');
    if (refreshTracesBtn) {
      refreshTracesBtn.addEventListener('click', () => {
        this.fetchLangfuseTelemetry();
      });
    }
  }

  async loadUsersTable() {
    const tbody = document.getElementById('auth-users-tbody');
    if (!tbody) return;

    try {
      const res = await fetch('/api/auth/users', {
        headers: {
          'Authorization': `Bearer ${this.getToken()}`
        }
      });

      if (!res.ok) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:12px; color:var(--red-down);">Admin authorization required to view users.</td></tr>`;
        return;
      }

      const data = await res.json();
      const users = data.users || [];

      if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:12px; color:var(--text-muted);">No users found.</td></tr>`;
        return;
      }

      tbody.innerHTML = users.map(u => {
        const isCurrent = this.currentUser && this.currentUser.username === u.username;
        const roleColor = u.role === 'admin' ? '#22c55e' : (u.role === 'trader' ? '#38bdf8' : '#f59e0b');
        const createdDate = u.created_at ? u.created_at.split('T')[0] : '--';

        return `
          <tr>
            <td style="color:var(--text-muted); font-size:10px;">${u.id}</td>
            <td style="font-weight:600; color:#fff;">
              ${u.username} ${isCurrent ? '<span style="color:var(--green-up); font-size:9px;">(YOU)</span>' : ''}
            </td>
            <td><span class="pill-badge" style="background:${roleColor}22; border:1px solid ${roleColor}55; color:${roleColor}; font-size:9.5px; padding:2px 6px;">${u.role.toUpperCase()}</span></td>
            <td style="font-size:10px; color:var(--text-muted);">${createdDate}</td>
            <td style="text-align:right;">
              ${!isCurrent ? `
                <button class="f-key btn-delete-user" data-username="${u.username}" style="border-color:#ef4444; color:#ef4444; font-size:9px; padding:2px 6px;">DELETE</button>
              ` : '<span style="color:var(--text-muted); font-size:9.5px;">ACTIVE</span>'}
            </td>
          </tr>
        `;
      }).join('');

      // Bind delete buttons
      tbody.querySelectorAll('.btn-delete-user').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          const username = btn.dataset.username;
          if (!confirm(`Are you sure you want to delete user account '${username}'?`)) return;

          try {
            const delRes = await fetch(`/api/auth/users/${encodeURIComponent(username)}`, {
              method: 'DELETE',
              headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });
            if (delRes.ok) {
              this.loadUsersTable();
            } else {
              const err = await delRes.json();
              alert(`Error deleting user: ${err.detail || 'Could not delete user'}`);
            }
          } catch (err) {
            alert(`Network error: ${err.message}`);
          }
        });
      });

    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:12px; color:var(--red-down);">Error loading user records: ${e.message}</td></tr>`;
    }
  }

  async fetchLangfuseTelemetry() {
    const pill = document.getElementById('langfuse-status-pill');
    const hostLabel = document.getElementById('langfuse-host-label');
    const pubLabel = document.getElementById('langfuse-pubkey-label');

    if (!pill) return;

    try {
      const res = await fetch('/api/observability/langfuse');
      if (res.ok) {
        const data = await res.json();
        if (hostLabel && data.host) hostLabel.textContent = data.host;
        if (pubLabel) pubLabel.textContent = data.public_key_preview || '--';

        if (data.connected) {
          pill.textContent = 'CLOUD CONNECTED';
          pill.style.background = '#22c55e';
          pill.style.color = '#000';
        } else if (data.configured) {
          pill.textContent = 'KEYS CONFIGURED';
          pill.style.background = '#38bdf8';
          pill.style.color = '#000';
        } else {
          pill.textContent = 'STANDBY / LOCAL';
          pill.style.background = '#475569';
          pill.style.color = '#cbd5e1';
        }
      }
    } catch (e) {
      if (pill) {
        pill.textContent = 'STANDBY';
        pill.style.background = '#475569';
      }
    }
  }
}

// Global instance initialized on DOM load
window.adversarialAuth = new AdversarialAuth();
