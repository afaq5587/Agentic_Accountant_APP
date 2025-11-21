const state = {
  role: null,
  adminId: null,
  adminPassword: null,
  members: [],
  filter: 'all',
  announcements: [],
  rules: []
};
let editingMemberId = null;

// DOM Elements
const loginScreen = document.getElementById('login-screen');
const loginUserBtn = document.getElementById('login-user');
const adminLoginForm = document.getElementById('admin-login-form');
const logoutBtn = document.getElementById('logout');
const roleBadge = document.getElementById('role-badge');
const toastContainer = document.getElementById('toast-container');
const membersGrid = document.getElementById('members-grid');
const membersTable = document.getElementById('members-table');
const metricMembers = document.getElementById('metric-members');
const metricPaid = document.getElementById('metric-paid');
const metricUnpaid = document.getElementById('metric-unpaid');
const barPaid = document.getElementById('bar-paid');
const barUnpaid = document.getElementById('bar-unpaid');

// Modals
const addMemberModal = document.getElementById('add-member-modal');
const openAddMemberBtn = document.getElementById('open-add-member');
const closeAddMemberBtn = document.getElementById('close-add-member');
const addMemberForm = document.getElementById('add-member-form');
const addMemberRole = document.getElementById('add-member-role');
const addMemberPasswordWrapper = document.getElementById('add-member-password');
const addMemberPhone = document.getElementById('add-member-phone');
const addMemberIdInput = document.getElementById('add-member-id');
const addMemberNameInput = document.getElementById('add-member-name');
const addMemberAmountInput = document.getElementById('add-member-amount');
const memberModalTitle = document.getElementById('member-modal-title');
const addMemberSubmitButton = addMemberForm ? addMemberForm.querySelector('button[type="submit"]') : null;

// Announcements
const announcementsList = document.getElementById('announcements-list');
const announcementsEmpty = document.getElementById('announcements-empty');
const addAnnouncementModal = document.getElementById('add-announcement-modal');
const openAddAnnouncementBtn = document.getElementById('open-add-announcement');
const closeAddAnnouncementBtn = document.getElementById('close-add-announcement');
const addAnnouncementForm = document.getElementById('add-announcement-form');
const announcementTitle = document.getElementById('announcement-title');
const announcementText = document.getElementById('announcement-text');
const announcementImageInput = document.getElementById('announcement-image-input');
const announcementImagePreview = document.getElementById('announcement-image-preview');
const announcementPreviewImg = document.getElementById('announcement-preview-img');
const removeAnnouncementImage = document.getElementById('remove-announcement-image');
const announcementImagePath = document.getElementById('announcement-image-path');
const announcementId = document.getElementById('announcement-id');
const announcementUploadStatus = document.getElementById('announcement-upload-status');
const announcementModalTitle = document.getElementById('announcement-modal-title');

// Rules
const rulesList = document.getElementById('rules-list');
const rulesEmpty = document.getElementById('rules-empty');
const addRuleModal = document.getElementById('add-rule-modal');
const openAddRuleBtn = document.getElementById('open-add-rule');
const closeAddRuleBtn = document.getElementById('close-add-rule');
const addRuleForm = document.getElementById('add-rule-form');
const ruleTitle = document.getElementById('rule-title');
const ruleText = document.getElementById('rule-text');
const ruleId = document.getElementById('rule-id');
const ruleModalTitle = document.getElementById('rule-modal-title');

// Settings
const settingsLocked = document.getElementById('settings-locked');
const passwordChangeForm = document.getElementById('password-change-form');

// Chatbot
const chatbotLauncher = document.getElementById('chatbot-launcher');
const chatbotPanel = document.getElementById('chatbot-panel');
const chatbotClose = document.getElementById('chatbot-close');
const chatbotForm = document.getElementById('chatbot-form');
const chatbotInput = document.getElementById('chatbot-input');
const chatbotMessages = document.getElementById('chatbot-messages');
const chatbotSendButton = chatbotForm ? chatbotForm.querySelector('.chatbot-send') : null;
let chatbotOpen = false;

// --- Utilities ---

function showToast(type, message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  
  let icon = '';
  if (type === 'success') {
    icon = `<div class="text-emerald-500"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg></div>`;
  } else if (type === 'error') {
    icon = `<div class="text-rose-500"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></div>`;
  } else {
    icon = `<div class="text-blue-500"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div>`;
  }

  toast.innerHTML = `
    ${icon}
    <div class="flex-1 text-sm text-slate-200">${message}</div>
    <button class="text-slate-500 hover:text-white transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
  `;
  
  toast.querySelector('button').addEventListener('click', () => toast.remove());
  toastContainer.prepend(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

function isValidPakistaniPhone(value) {
  if (!value) return true;
  const normalized = value.trim();
  if (!normalized) return true;
  return /^(\+92|0)3\d{9}$/.test(normalized);
}

function setButtonLoading(button, isLoading, text = 'Loading...') {
  if (!button) return;
  if (isLoading) {
    button.disabled = true;
    button.dataset.originalText = button.textContent;
    button.innerHTML = `<svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> ${text}`;
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalText || 'Submit';
  }
}

// --- API Interactions ---

async function adminPost(path, payload = {}) {
  if (state.role !== 'Admin' || !state.adminId || !state.adminPassword) {
    throw new Error('Admin privileges required');
  }
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      admin_id: state.adminId,
      admin_password: state.adminPassword,
      ...payload,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.status === 'error') {
    const detail = data.detail || data.message || 'Action failed';
    throw new Error(detail);
  }
  return data;
}

async function callAgent(message, options = {}) {
  const payload = {
    message,
    role: options.role || state.role || 'User',
    admin_id: options.adminId || state.adminId,
    admin_password: options.adminPassword || state.adminPassword
  };

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(detail.detail || 'Agent request failed');
  }

  return res.json();
}

// --- Data Refresh & Rendering ---

async function refreshMembers() {
  try {
    const res = await fetch('/api/members');
    const data = await res.json();
    state.members = data.members || [];
    renderMembers();
    renderMetrics();
    renderDirectoryTable();
  } catch (error) {
    console.error('Failed to refresh members:', error);
    showToast('error', 'Failed to load members data.');
  }
}

async function refreshAnnouncements() {
  try {
    const res = await fetch('/api/announcements');
    const data = await res.json();
    state.announcements = data.announcements || [];
    renderAnnouncements();
  } catch (error) {
    console.error('Failed to refresh announcements:', error);
  }
}

async function refreshRules() {
  try {
    const res = await fetch('/api/rules');
    const data = await res.json();
    state.rules = data.rules || [];
    renderRules();
  } catch (error) {
    console.error('Failed to refresh rules:', error);
  }
}

function renderMetrics() {
  const total = state.members.length;
  const paid = state.members.filter((m) => m.payment_status === 'Paid').length;
  const unpaid = total - paid;
  
  metricMembers.textContent = total;
  metricPaid.textContent = paid;
  metricUnpaid.textContent = unpaid;

  if (total > 0) {
    barPaid.style.width = `${(paid / total) * 100}%`;
    barUnpaid.style.width = `${(unpaid / total) * 100}%`;
  } else {
    barPaid.style.width = '0%';
    barUnpaid.style.width = '0%';
  }
}

function renderMembers() {
  const filtered = state.members.filter((member) => {
    if (state.filter === 'all') return true;
    return member.payment_status === state.filter;
  });

  if (filtered.length === 0) {
    membersGrid.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500">No members match the current filters.</div>';
    return;
  }

  membersGrid.innerHTML = filtered.map((member) => {
    const statusClass = member.payment_status === 'Paid' ? 'status-paid' : 'status-unpaid';
    const adminActions = state.role === 'Admin' ? `
      <div class="flex gap-2 mt-4 pt-4 border-t border-white/5">
        <button class="flex-1 py-2 rounded bg-white/5 hover:bg-white/10 text-xs font-medium transition-colors" data-action="edit" data-member="${member.member_id}">Edit</button>
        <button class="flex-1 py-2 rounded bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-medium transition-colors" data-action="delete" data-member="${member.member_id}">Delete</button>
      </div>
      <div class="flex gap-2 mt-2">
        <button class="flex-1 py-2 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-xs font-medium transition-colors" data-action="mark" data-status="Paid" data-member="${member.member_id}">Mark Paid</button>
        <button class="flex-1 py-2 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-medium transition-colors" data-action="mark" data-status="Unpaid" data-member="${member.member_id}">Mark Unpaid</button>
      </div>
    ` : '';
    
    return `
      <div class="glass-panel p-5 rounded-2xl card-hover flex flex-col h-full">
        <div class="flex items-start justify-between mb-2">
          <div>
            <h3 class="font-bold text-white text-lg">${member.name}</h3>
            <p class="text-xs text-slate-400 font-mono">${member.member_id}</p>
          </div>
          <span class="badge ${member.role === 'Admin' ? 'badge-gold' : 'bg-slate-800 text-slate-400'}">${member.role}</span>
        </div>
        
        <div class="space-y-2 mb-4 flex-1">
          ${member.phone ? `<div class="flex items-center gap-2 text-sm text-slate-400"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"></path></svg> ${member.phone}</div>` : ''}
          <div class="flex items-center justify-between mt-3">
            <span class="text-2xl font-bold text-white">₨${member.amount}</span>
            <span class="badge ${statusClass}">${member.payment_status}</span>
          </div>
        </div>
        
        ${adminActions}
      </div>
    `;
  }).join('');

  if (state.role === 'Admin') {
    membersGrid.querySelectorAll('button[data-action]').forEach((button) => {
      button.addEventListener('click', handleMemberCardAction);
    });
  }
}

function renderDirectoryTable() {
  if (state.members.length === 0) {
    membersTable.innerHTML = '<p class="text-sm text-slate-500 p-4">No members yet.</p>';
    return;
  }
  membersTable.innerHTML = `
    <table class="w-full text-left text-sm">
      <thead class="bg-white/5 text-slate-400 uppercase text-xs font-medium">
        <tr>
          <th class="px-6 py-4">Member</th>
          <th class="px-6 py-4">Role</th>
          <th class="px-6 py-4">Phone</th>
          <th class="px-6 py-4">Amount</th>
          <th class="px-6 py-4">Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-white/5">
        ${state.members.map((member) => `
          <tr class="hover:bg-white/5 transition-colors">
            <td class="px-6 py-4">
              <div class="font-medium text-white">${member.name}</div>
              <div class="text-xs text-slate-500 font-mono">${member.member_id}</div>
            </td>
            <td class="px-6 py-4"><span class="badge ${member.role === 'Admin' ? 'badge-gold' : 'bg-slate-800 text-slate-400'}">${member.role}</span></td>
            <td class="px-6 py-4 text-slate-400">${member.phone || '-'}</td>
            <td class="px-6 py-4 font-medium text-white">₨${member.amount}</td>
            <td class="px-6 py-4">
              <span class="badge ${member.payment_status === 'Paid' ? 'status-paid' : 'status-unpaid'}">${member.payment_status}</span>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderAnnouncements() {
  if (!announcementsList || !announcementsEmpty) return;
  
  if (state.announcements.length === 0) {
    announcementsList.innerHTML = '';
    announcementsEmpty.classList.remove('hidden');
    return;
  }
  
  announcementsEmpty.classList.add('hidden');
  announcementsList.innerHTML = state.announcements.map((announcement) => {
    const imageHtml = announcement.image_path 
      ? `<img src="${announcement.image_path}" alt="${announcement.title}" class="w-full h-64 object-cover rounded-xl mb-4 border border-white/10" />`
      : '';
    const adminActions = state.role === 'Admin' ? `
      <div class="flex gap-2 mt-4 pt-4 border-t border-white/5">
        <button class="btn-outline px-3 py-1.5 rounded-lg text-xs" data-action="edit" data-id="${announcement.id}">Edit</button>
        <button class="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors" data-action="delete" data-id="${announcement.id}">Delete</button>
      </div>
    ` : '';
    return `
      <article class="glass-panel p-6 rounded-2xl" data-announcement="${announcement.id}">
        ${imageHtml}
        <div class="flex items-start justify-between mb-2">
          <h3 class="text-xl font-bold text-white">${announcement.title}</h3>
          <span class="text-xs text-slate-500">${new Date(announcement.created_at).toLocaleDateString()}</span>
        </div>
        <p class="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">${announcement.text}</p>
        ${adminActions}
      </article>
    `;
  }).join('');

  if (state.role === 'Admin') {
    announcementsList.querySelectorAll('button[data-action]').forEach((button) => {
      button.addEventListener('click', handleAnnouncementAction);
    });
  }
}

function renderRules() {
  if (!rulesList || !rulesEmpty) return;
  
  if (state.rules.length === 0) {
    rulesList.innerHTML = '';
    rulesEmpty.classList.remove('hidden');
    return;
  }
  
  rulesEmpty.classList.add('hidden');
  rulesList.innerHTML = state.rules.map((rule) => {
    const adminActions = state.role === 'Admin' ? `
      <div class="flex gap-2 mt-4 pt-4 border-t border-white/5">
        <button class="btn-outline px-3 py-1.5 rounded-lg text-xs" data-action="edit" data-id="${rule.id}">Edit</button>
        <button class="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors" data-action="delete" data-id="${rule.id}">Delete</button>
      </div>
    ` : '';
    return `
      <article class="glass-panel p-6 rounded-2xl" data-rule="${rule.id}">
        <div class="flex items-start justify-between mb-2">
          <h3 class="text-lg font-bold text-gold">${rule.title}</h3>
          <span class="text-xs text-slate-500">${new Date(rule.created_at).toLocaleDateString()}</span>
        </div>
        <p class="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">${rule.text}</p>
        ${adminActions}
      </article>
    `;
  }).join('');

  if (state.role === 'Admin') {
    rulesList.querySelectorAll('button[data-action]').forEach((button) => {
      button.addEventListener('click', handleRuleAction);
    });
  }
}

// --- Event Handlers ---

// Login
loginUserBtn.addEventListener('click', async () => {
  state.role = 'User';
  loginScreen.classList.add('hidden');
  document.getElementById('app-layout').classList.remove('hidden');
  roleBadge.textContent = 'Member';
  
  // Hide admin controls
  settingsLocked.classList.remove('hidden');
  passwordChangeForm.classList.add('hidden');
  openAddMemberBtn.classList.add('hidden');
  if (openAddAnnouncementBtn) openAddAnnouncementBtn.classList.add('hidden');
  if (openAddRuleBtn) openAddRuleBtn.classList.add('hidden');
  
  refreshMembers();
  refreshAnnouncements();
  refreshRules();
  
  showToast('success', 'Welcome back! Accessing member dashboard.');
});

adminLoginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const adminId = document.getElementById('admin-login-id').value.trim();
  const adminPassword = document.getElementById('admin-login-password').value.trim();
  const submitBtn = adminLoginForm.querySelector('button[type="submit"]');

  if (!adminId || !adminPassword) {
    showToast('error', 'Please enter both Admin ID and Password');
    return;
  }

  setButtonLoading(submitBtn, true, 'Verifying...');

  try {
    const response = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ admin_id: adminId, admin_password: adminPassword }),
    });
    const data = await response.json().catch(() => ({}));
    
    if (!response.ok || !data.authenticated) {
      throw new Error(data.detail || 'Invalid credentials');
    }

    state.role = 'Admin';
    state.adminId = adminId;
    state.adminPassword = adminPassword;
    
    loginScreen.classList.add('hidden');
    document.getElementById('app-layout').classList.remove('hidden');
    roleBadge.textContent = `Admin: ${adminId}`;
    
    // Show admin controls
    settingsLocked.classList.add('hidden');
    passwordChangeForm.classList.remove('hidden');
    openAddMemberBtn.classList.remove('hidden');
    if (openAddAnnouncementBtn) openAddAnnouncementBtn.classList.remove('hidden');
    if (openAddRuleBtn) openAddRuleBtn.classList.remove('hidden');
    
    showToast('success', 'Admin authentication successful.');
    refreshMembers();
    refreshAnnouncements();
    refreshRules();
  } catch (error) {
    showToast('error', error.message);
  } finally {
    setButtonLoading(submitBtn, false, 'Secure Login');
  }
});

logoutBtn.addEventListener('click', () => {
  state.role = null;
  state.adminId = null;
  state.adminPassword = null;
  document.getElementById('app-layout').classList.add('hidden');
  loginScreen.classList.remove('hidden');
  adminLoginForm.reset();
  showToast('info', 'Signed out successfully.');
});

// Navigation
document.querySelectorAll('.nav-item').forEach((button) => {
  button.addEventListener('click', () => {
    // Update active state
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active', 'text-white', 'bg-white/5'));
    button.classList.add('active', 'text-white', 'bg-white/5');
    
    // Show section
    const section = button.getAttribute('data-section');
    document.querySelectorAll('main section[id$="-section"]').forEach((sec) => {
      sec.classList.add('hidden');
    });
    document.getElementById(`${section}-section`).classList.remove('hidden');
    
    // Update title
    const titleMap = {
      'dashboard': 'Dashboard',
      'members': 'Members Directory',
      'announcements': 'Announcements',
      'rules': 'Rules & Regulations',
      'settings': 'Settings'
    };
    document.getElementById('page-title').textContent = titleMap[section];
  });
});

// Mobile Menu
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const sidebar = document.getElementById('sidebar');
if (mobileMenuBtn && sidebar) {
  mobileMenuBtn.addEventListener('click', () => {
    sidebar.classList.toggle('hidden');
    sidebar.classList.toggle('absolute');
    sidebar.classList.toggle('inset-0');
  });
}

// Member Actions
async function handleMemberCardAction(event) {
  const button = event.currentTarget;
  const action = button.getAttribute('data-action');
  const memberId = button.getAttribute('data-member');

  if (!memberId) return;

  try {
    if (action === 'delete') {
      if (!confirm('Are you sure you want to delete this member?')) return;
      const result = await adminPost('/api/admin/members/delete', { member_id: memberId });
      showToast('success', result.message || 'Member deleted.');
    } else if (action === 'mark') {
      const status = button.getAttribute('data-status');
      const result = await adminPost('/api/admin/members/mark', {
        member_id: memberId,
        payment_status: status,
      });
      showToast('success', `Member marked as ${status}.`);
    } else if (action === 'edit') {
      const member = state.members.find((m) => m.member_id === memberId);
      if (member) {
        openMemberEditModal(member);
      }
      return;
    }
    await refreshMembers();
  } catch (error) {
    showToast('error', error.message);
  }
}

// Member Modal
function openMemberEditModal(member) {
  editingMemberId = member.member_id;
  memberModalTitle.textContent = 'Edit Member';
  addMemberSubmitButton.textContent = 'Save Changes';
  
  addMemberIdInput.value = member.member_id;
  addMemberIdInput.setAttribute('readonly', 'readonly');
  addMemberIdInput.classList.add('opacity-50', 'cursor-not-allowed');
  
  addMemberNameInput.value = member.name;
  addMemberAmountInput.value = member.amount;
  addMemberRole.value = member.role;
  addMemberRole.disabled = true;
  addMemberRole.classList.add('opacity-50', 'cursor-not-allowed');
  
  addMemberPhone.value = member.phone || '';
  addMemberPasswordWrapper.classList.add('hidden');
  
  addMemberModal.classList.remove('hidden');
}

function resetMemberForm() {
  editingMemberId = null;
  addMemberForm.reset();
  memberModalTitle.textContent = 'Add Member';
  addMemberSubmitButton.textContent = 'Create Member';
  
  addMemberIdInput.removeAttribute('readonly');
  addMemberIdInput.classList.remove('opacity-50', 'cursor-not-allowed');
  
  addMemberRole.disabled = false;
  addMemberRole.classList.remove('opacity-50', 'cursor-not-allowed');
  addMemberRole.value = 'User';
  
  addMemberPasswordWrapper.classList.add('hidden');
}

openAddMemberBtn.addEventListener('click', () => {
  resetMemberForm();
  addMemberModal.classList.remove('hidden');
});

closeAddMemberBtn.addEventListener('click', () => {
  addMemberModal.classList.add('hidden');
  resetMemberForm();
});

addMemberRole.addEventListener('change', (e) => {
  if (e.target.value === 'Admin') {
    addMemberPasswordWrapper.classList.remove('hidden');
  } else {
    addMemberPasswordWrapper.classList.add('hidden');
  }
});

addMemberForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const memberId = addMemberIdInput.value.trim();
  const name = addMemberNameInput.value.trim();
  const amount = Number(addMemberAmountInput.value);
  const role = addMemberRole.value;
  const phone = addMemberPhone.value.trim();
  const adminPass = document.getElementById('add-member-admin-password').value.trim();

  if (!memberId || !name || isNaN(amount)) {
    showToast('error', 'Please fill in all required fields.');
    return;
  }
  
  if (phone && !isValidPakistaniPhone(phone)) {
    showToast('error', 'Invalid phone number format. Use +923... or 03...');
    return;
  }

  if (!editingMemberId && role === 'Admin' && !adminPass) {
    showToast('error', 'Admin password is required for new admins.');
    return;
  }

  setButtonLoading(addMemberSubmitButton, true, 'Saving...');

  try {
    if (editingMemberId) {
      await adminPost('/api/admin/members/update', {
        member_id: editingMemberId,
        name,
        amount,
        phone: phone || null
      });
      showToast('success', 'Member updated successfully.');
    } else {
      const payload = { member_id: memberId, name, amount, role, phone: phone || null };
      if (role === 'Admin') payload.password = adminPass;
      await adminPost('/api/admin/members', payload);
      showToast('success', 'Member created successfully.');
    }
    
    addMemberModal.classList.add('hidden');
    resetMemberForm();
    refreshMembers();
  } catch (error) {
    showToast('error', error.message);
  } finally {
    setButtonLoading(addMemberSubmitButton, false, editingMemberId ? 'Save Changes' : 'Create Member');
  }
});

// Announcement Actions
async function handleAnnouncementAction(event) {
  const button = event.currentTarget;
  const action = button.getAttribute('data-action');
  const id = parseInt(button.getAttribute('data-id'));

  try {
    if (action === 'delete') {
      if (!confirm('Delete this announcement?')) return;
      await adminPost('/api/admin/announcements/delete', { announcement_id: id });
      showToast('success', 'Announcement deleted.');
      refreshAnnouncements();
    } else if (action === 'edit') {
      const announcement = state.announcements.find(a => a.id === id);
      if (announcement) {
        announcementTitle.value = announcement.title;
        announcementText.value = announcement.text;
        announcementId.value = announcement.id;
        announcementModalTitle.textContent = 'Edit Announcement';
        
        if (announcement.image_path) {
          announcementImagePath.value = announcement.image_path;
          announcementPreviewImg.src = announcement.image_path;
          announcementImagePreview.classList.remove('hidden');
        } else {
          announcementImagePath.value = '';
          announcementImagePreview.classList.add('hidden');
        }
        
        addAnnouncementModal.classList.remove('hidden');
      }
    }
  } catch (error) {
    showToast('error', error.message);
  }
}

// Announcement Modal
if (openAddAnnouncementBtn) {
  openAddAnnouncementBtn.addEventListener('click', () => {
    addAnnouncementForm.reset();
    announcementId.value = '';
    announcementImagePath.value = '';
    announcementImagePreview.classList.add('hidden');
    announcementModalTitle.textContent = 'New Announcement';
    addAnnouncementModal.classList.remove('hidden');
  });
}

if (closeAddAnnouncementBtn) {
  closeAddAnnouncementBtn.addEventListener('click', () => {
    addAnnouncementModal.classList.add('hidden');
  });
}

if (announcementImageInput) {
  announcementImageInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      announcementPreviewImg.src = e.target.result;
      announcementImagePreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);

    announcementUploadStatus.classList.remove('hidden');
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      // We need a separate upload endpoint or handle it via adminPost if supported
      // Assuming existing endpoint structure
      if (state.role !== 'Admin') throw new Error('Admin required');
      
      const res = await fetch('/api/admin/announcements/upload', {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) throw new Error('Upload failed');
      const data = await res.json();
      
      announcementImagePath.value = data.image_path;
      announcementUploadStatus.textContent = 'Upload complete';
      setTimeout(() => announcementUploadStatus.classList.add('hidden'), 2000);
    } catch (error) {
      showToast('error', 'Image upload failed: ' + error.message);
      announcementUploadStatus.classList.add('hidden');
    }
  });
}

if (removeAnnouncementImage) {
  removeAnnouncementImage.addEventListener('click', () => {
    announcementImagePath.value = '';
    announcementImageInput.value = '';
    announcementImagePreview.classList.add('hidden');
  });
}

if (addAnnouncementForm) {
  addAnnouncementForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = announcementTitle.value.trim();
    const text = announcementText.value.trim();
    const id = announcementId.value;
    const imagePath = announcementImagePath.value;

    if (!title || !text) {
      showToast('error', 'Title and content are required.');
      return;
    }

    const submitBtn = addAnnouncementForm.querySelector('button[type="submit"]');
    setButtonLoading(submitBtn, true, 'Posting...');

    try {
      if (id) {
        await adminPost('/api/admin/announcements/update', {
          announcement_id: parseInt(id),
          title,
          text,
          image_path: imagePath || null
        });
        showToast('success', 'Announcement updated.');
      } else {
        await adminPost('/api/admin/announcements', {
          title,
          text,
          image_path: imagePath || null
        });
        showToast('success', 'Announcement posted.');
      }
      addAnnouncementModal.classList.add('hidden');
      refreshAnnouncements();
    } catch (error) {
      showToast('error', error.message);
    } finally {
      setButtonLoading(submitBtn, false, 'Post Announcement');
    }
  });
}

// Rules Actions
async function handleRuleAction(event) {
  const button = event.currentTarget;
  const action = button.getAttribute('data-action');
  const id = parseInt(button.getAttribute('data-id'));

  try {
    if (action === 'delete') {
      if (!confirm('Delete this rule?')) return;
      await adminPost('/api/admin/rules/delete', { rule_id: id });
      showToast('success', 'Rule deleted.');
      refreshRules();
    } else if (action === 'edit') {
      const rule = state.rules.find(r => r.id === id);
      if (rule) {
        ruleTitle.value = rule.title;
        ruleText.value = rule.text;
        ruleId.value = rule.id;
        ruleModalTitle.textContent = 'Edit Rule';
        addRuleModal.classList.remove('hidden');
      }
    }
  } catch (error) {
    showToast('error', error.message);
  }
}

if (openAddRuleBtn) {
  openAddRuleBtn.addEventListener('click', () => {
    addRuleForm.reset();
    ruleId.value = '';
    ruleModalTitle.textContent = 'New Rule';
    addRuleModal.classList.remove('hidden');
  });
}

if (closeAddRuleBtn) {
  closeAddRuleBtn.addEventListener('click', () => {
    addRuleModal.classList.add('hidden');
  });
}

if (addRuleForm) {
  addRuleForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = ruleTitle.value.trim();
    const text = ruleText.value.trim();
    const id = ruleId.value;

    if (!title || !text) {
      showToast('error', 'Title and description are required.');
      return;
    }

    const submitBtn = addRuleForm.querySelector('button[type="submit"]');
    setButtonLoading(submitBtn, true, 'Saving...');

    try {
      if (id) {
        await adminPost('/api/admin/rules/update', {
          rule_id: parseInt(id),
          title,
          text
        });
        showToast('success', 'Rule updated.');
      } else {
        await adminPost('/api/admin/rules', {
          title,
          text
        });
        showToast('success', 'Rule created.');
      }
      addRuleModal.classList.add('hidden');
      refreshRules();
    } catch (error) {
      showToast('error', error.message);
    } finally {
      setButtonLoading(submitBtn, false, 'Save Rule');
    }
  });
}

// Settings
if (passwordChangeForm) {
  passwordChangeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const adminId = document.getElementById('settings-admin-id').value.trim();
    const newPass = document.getElementById('settings-new-password').value.trim();
    
    if (!adminId || !newPass) {
      showToast('error', 'All fields are required.');
      return;
    }

    const submitBtn = passwordChangeForm.querySelector('button[type="submit"]');
    setButtonLoading(submitBtn, true, 'Updating...');

    try {
      await adminPost('/api/admin/password', {
        target_admin_id: adminId,
        new_password: newPass
      });
      showToast('success', 'Password updated successfully.');
      passwordChangeForm.reset();
    } catch (error) {
      showToast('error', error.message);
    } finally {
      setButtonLoading(submitBtn, false, 'Update Password');
    }
  });
}

// Chatbot
function appendChatMessage(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = `flex w-full ${role === 'user' ? 'chatbot-message-user' : 'chatbot-message-assistant'}`;
  
  const bubble = document.createElement('div');
  bubble.className = 'chatbot-message-bubble';
  bubble.textContent = text;
  
  wrapper.appendChild(bubble);
  chatbotMessages.appendChild(wrapper);
  chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
  
  return bubble;
}

function toggleChatbot() {
  chatbotOpen = !chatbotOpen;
  chatbotPanel.classList.toggle('open', chatbotOpen);
  chatbotLauncher.classList.toggle('active', chatbotOpen);
  
  if (chatbotOpen) {
    setTimeout(() => chatbotInput.focus(), 300);
    if (!chatbotMessages.hasChildNodes()) {
      appendChatMessage('assistant', "Hello! I'm your AI accountant. Ask me about member payments or financial summaries.");
    }
  }
}

if (chatbotLauncher) chatbotLauncher.addEventListener('click', toggleChatbot);
if (chatbotClose) chatbotClose.addEventListener('click', toggleChatbot);

if (chatbotForm) {
  chatbotForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = chatbotInput.value.trim();
    if (!message) return;

    appendChatMessage('user', message);
    chatbotInput.value = '';
    
    const loadingBubble = appendChatMessage('assistant', 'Thinking...');
    
    try {
      const result = await callAgent(message);
      const reply = result.message || 'I processed your request.';
      loadingBubble.textContent = reply;
    } catch (error) {
      loadingBubble.textContent = 'Sorry, I encountered an error. Please try again.';
    }
  });
}

// Filter Buttons
document.querySelectorAll('button[data-filter]').forEach(btn => {
  btn.addEventListener('click', () => {
    state.filter = btn.getAttribute('data-filter');
    // Update active styles for filter buttons
    document.querySelectorAll('button[data-filter]').forEach(b => {
      if (b.getAttribute('data-filter') === state.filter) {
        b.classList.add('bg-white/10');
      } else {
        b.classList.remove('bg-white/10');
      }
    });
    renderMembers();
  });
});
