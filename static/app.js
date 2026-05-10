/**
 * Adaalat AI - Frontend Logic
 * Handles case management, chat, document uploads, and drafting.
 */

// API Base URL - empty string assumes relative to same host
const API_BASE = '/api/v1';

// State Management
let currentCaseId = null;
let isProcessing = false;

// DOM Elements
const elements = {
    casesList: document.getElementById('cases-list'),
    newCaseBtn: document.getElementById('new-case-btn'),
    activeCaseTitle: document.getElementById('active-case-title'),
    activeCaseId: document.getElementById('active-case-id'),
    chatMessages: document.getElementById('chat-messages'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    sendBtn: document.getElementById('send-btn'),
    dropZone: document.getElementById('drop-zone'),
    fileInput: document.getElementById('file-input'),
    uploadStatus: document.getElementById('upload-status'),
    documentsList: document.getElementById('documents-list'),
    caseSearch: document.getElementById('case-search'),
    newCaseModal: document.getElementById('new-case-modal'),
    closeCaseModal: document.getElementById('close-case-modal'),
    confirmNewCaseBtn: document.getElementById('confirm-new-case-btn'),
    caseTitleInput: document.getElementById('case-title-input'),
    draftType: document.getElementById('draft-type'),
    draftInstructions: document.getElementById('draft-instructions'),
    draftBtn: document.getElementById('draft-btn'),
    draftsList: document.getElementById('drafts-list'),
    draftModal: document.getElementById('draft-modal'),
    modalTitle: document.getElementById('modal-title'),
    modalText: document.getElementById('modal-text'),
    closeModal: document.getElementById('close-modal'),
    copyDraftBtn: document.getElementById('copy-draft-btn')
};

/**
 * Initialization
 */
document.addEventListener('DOMContentLoaded', () => {
    loadCases();
    setupEventListeners();
    
    // Auto-resize textarea
    elements.chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
});

function setupEventListeners() {
    // New Case
    elements.newCaseBtn.addEventListener('click', () => {
        elements.newCaseModal.classList.remove('hidden');
        elements.caseTitleInput.focus();
    });
    
    elements.closeCaseModal.addEventListener('click', () => elements.newCaseModal.classList.add('hidden'));
    
    elements.confirmNewCaseBtn.addEventListener('click', handleCreateCase);
    elements.caseTitleInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleCreateCase();
    });

    // Case Search
    elements.caseSearch.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        document.querySelectorAll('.case-item').forEach(item => {
            const title = item.querySelector('.case-item-title').innerText.toLowerCase();
            item.style.display = title.includes(term) ? 'flex' : 'none';
        });
    });

    // Quick Actions
    document.body.addEventListener('click', (e) => {
        const card = e.target.closest('.action-card');
        if (!card) return;
        
        if (card.id === 'qa-new-case') {
            elements.newCaseBtn.click();
        } else if (card.id === 'qa-upload') {
            if (currentCaseId) elements.fileInput.click();
            else alert('Please select or create a case first.');
        } else if (card.id === 'qa-draft') {
            if (currentCaseId) elements.draftType.focus();
            else alert('Please select or create a case first.');
        }
    });

    // Chat
    elements.chatForm.addEventListener('submit', handleChatSubmit);
    elements.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            elements.chatForm.requestSubmit();
        }
    });

    // File Upload
    elements.dropZone.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
    });
    
    // Drag & Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        elements.dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    elements.dropZone.addEventListener('dragover', () => elements.dropZone.classList.add('active'));
    elements.dropZone.addEventListener('dragleave', () => elements.dropZone.classList.remove('active'));
    elements.dropZone.addEventListener('drop', (e) => {
        elements.dropZone.classList.remove('active');
        const dt = e.dataTransfer;
        const file = dt.files[0];
        if (file && file.type === 'application/pdf') {
            handleFileUpload(file);
        } else {
            alert('Please upload a PDF file.');
        }
    });

    // Drafting
    elements.draftBtn.addEventListener('click', handleGenerateDraft);

    // Modal
    elements.closeModal.addEventListener('click', () => elements.draftModal.classList.add('hidden'));
    elements.copyDraftBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(elements.modalText.innerText);
        elements.copyDraftBtn.innerText = 'Copied!';
        setTimeout(() => elements.copyDraftBtn.innerText = 'Copy to Clipboard', 2000);
    });
    
    window.addEventListener('click', (e) => {
        if (e.target === elements.draftModal) elements.draftModal.classList.add('hidden');
    });
}

/**
 * Case Management
 */
async function loadCases() {
    try {
        const response = await fetch(`${API_BASE}/cases`);
        const cases = await response.json();
        
        elements.casesList.innerHTML = '';
        cases.forEach(c => {
            const li = document.createElement('li');
            li.className = `case-item ${c.id === currentCaseId ? 'active' : ''}`;
            li.innerHTML = `
                <div class="case-item-title">${c.title}</div>
                <div class="case-item-date">${new Date(c.created_at).toLocaleDateString()}</div>
            `;
            li.onclick = () => selectCase(c.id);
            elements.casesList.appendChild(li);
        });
    } catch (err) {
        console.error('Failed to load cases:', err);
    }
}

async function handleCreateCase() {
    const title = elements.caseTitleInput.value.trim();
    if (!title) return;

    try {
        const response = await fetch(`${API_BASE}/cases`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description: 'Created via web UI' })
        });
        const newCase = await response.json();
        
        elements.newCaseModal.classList.add('hidden');
        elements.caseTitleInput.value = '';
        
        currentCaseId = newCase.id;
        await loadCases();
        selectCase(newCase.id);
    } catch (err) {
        alert('Failed to create case');
    }
}

async function selectCase(caseId) {
    currentCaseId = caseId;
    
    // UI Updates
    document.querySelectorAll('.case-item').forEach(el => el.classList.remove('active'));
    const activeEl = Array.from(document.querySelectorAll('.case-item')).find(el => el.innerText.includes(caseId));
    // (Actually title match is better but IDs are unique. We'll refresh list anyway)
    
    // Enable inputs
    elements.chatInput.disabled = false;
    elements.sendBtn.disabled = false;
    elements.dropZone.classList.remove('disabled');
    elements.draftType.disabled = false;
    elements.draftInstructions.disabled = false;
    elements.draftBtn.disabled = false;
    
    // Update Header
    try {
        const response = await fetch(`${API_BASE}/cases/${caseId}`);
        const caseData = await response.json();
        elements.activeCaseTitle.innerText = caseData.title;
        elements.activeCaseId.innerText = caseId;
        elements.activeCaseId.classList.remove('hidden');
        
        // Clear chat and show history?
        // For now, let's just clear or show a transition
        elements.chatMessages.innerHTML = `
            <div class="welcome-screen">
                <i class="fa-solid fa-gavel welcome-icon"></i>
                <h2>Case: ${caseData.title}</h2>
                <p>Upload documents for this case or start asking legal questions.</p>
            </div>
        `;
        
        loadCaseHistory(caseId);
    } catch (err) {
        console.error('Failed to select case:', err);
    }
    
    loadCases(); // Refresh list to update active class
}

async function loadCaseHistory(caseId) {
    try {
        const response = await fetch(`${API_BASE}/cases/${caseId}/history`);
        const data = await response.json();
        
        // Populate docs
        elements.documentsList.innerHTML = '';
        data.documents.forEach(doc => appendDocItem(doc));
        
        // Populate drafts
        elements.draftsList.innerHTML = '';
        data.drafts.forEach(draft => appendDraftItem(draft));
        
        // Note: The /history endpoint in routes.py doesn't return chat history.
        // We might need to call /cases/{case_id}/messages if we want persistent chat history.
        // Let's assume for now we don't have it or we'll add it if needed.
    } catch (err) {
        console.error('Failed to load history:', err);
    }
}

/**
 * Chat Logic
 */
async function handleChatSubmit(e) {
    e.preventDefault();
    const message = elements.chatInput.value.trim();
    if (!message || isProcessing || !currentCaseId) return;

    appendMessage('user', message);
    elements.chatInput.value = '';
    elements.chatInput.style.height = 'auto';
    
    isProcessing = true;
    const indicator = showTypingIndicator();

    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_id: currentCaseId, message })
        });
        const data = await response.json();
        indicator.remove();
        appendMessage('assistant', data.response);
    } catch (err) {
        indicator.remove();
        appendMessage('assistant', 'Sorry, I encountered an error processing your request.');
    } finally {
        isProcessing = false;
    }
}

function appendMessage(role, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    
    const icon = role === 'user' ? 'fa-user' : 'fa-robot';
    const avatar = `<div class="avatar"><i class="fa-solid ${icon}"></i></div>`;
    
    // Render markdown using marked.js
    const bubbleContent = role === 'assistant' ? marked.parse(text) : `<p>${text}</p>`;
    
    const copyBtn = role === 'assistant' ? `
        <button class="copy-msg-btn" onclick="copyText(this, \`${text.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
            <i class="fa-solid fa-copy"></i>
        </button>
    ` : '';

    msgDiv.innerHTML = `
        ${avatar}
        <div class="bubble">${bubbleContent}${copyBtn}</div>
    `;
    
    elements.chatMessages.appendChild(msgDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    
    // Remove welcome screen if it exists
    const welcome = elements.chatMessages.querySelector('.welcome-screen');
    if (welcome) welcome.remove();
}

window.copyText = (btn, text) => {
    navigator.clipboard.writeText(text);
    const icon = btn.querySelector('i');
    icon.className = 'fa-solid fa-check';
    setTimeout(() => icon.className = 'fa-solid fa-copy', 2000);
};

function showTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="bubble typing-indicator">
            <span></span><span></span><span></span>
        </div>
    `;
    elements.chatMessages.appendChild(div);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    return div;
}

/**
 * File Upload Logic
 */
async function handleFileUpload(file) {
    if (!currentCaseId) return;
    
    elements.uploadStatus.classList.remove('hidden');
    elements.dropZone.classList.add('disabled');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        // Upload
        const response = await fetch(`${API_BASE}/upload?case_id=${currentCaseId}`, {
            method: 'POST',
            body: formData
        });
        const docData = await response.json();
        appendDocItem({ id: docData.doc_id, filename: docData.filename });
        
        // Automatically start analysis
        appendMessage('assistant', `I've received **${docData.filename}**. Let me analyze it for you...`);
        
        const analyzeRes = await fetch(`${API_BASE}/analyze?case_id=${currentCaseId}&doc_id=${docData.doc_id}`, {
            method: 'POST'
        });
        const analysisData = await analyzeRes.json();
        appendMessage('assistant', analysisData.analysis);
        
    } catch (err) {
        alert('Failed to upload/analyze document.');
    } finally {
        elements.uploadStatus.classList.add('hidden');
        elements.dropZone.classList.remove('disabled');
    }
}

function appendDocItem(doc) {
    const li = document.createElement('li');
    li.className = 'doc-item';
    li.innerHTML = `
        <div class="doc-info">
            <i class="fa-solid fa-file-pdf"></i>
            <span class="doc-name" title="${doc.filename}">${doc.filename}</span>
        </div>
        <div class="doc-actions">
            <button onclick="analyzeDocument('${doc.id}')"><i class="fa-solid fa-magnifying-glass"></i></button>
        </div>
    `;
    elements.documentsList.appendChild(li);
}

window.analyzeDocument = async (docId) => {
    if (isProcessing) return;
    isProcessing = true;
    const indicator = showTypingIndicator();
    try {
        const response = await fetch(`${API_BASE}/analyze?case_id=${currentCaseId}&doc_id=${docId}`, {
            method: 'POST'
        });
        const data = await response.json();
        indicator.remove();
        appendMessage('assistant', data.analysis);
    } catch (err) {
        indicator.remove();
        appendMessage('assistant', 'Analysis failed.');
    } finally {
        isProcessing = false;
    }
};

/**
 * Drafting Logic
 */
async function handleGenerateDraft() {
    if (!currentCaseId || isProcessing) return;
    
    const docType = elements.draftType.value;
    const instructions = elements.draftInstructions.value;
    
    isProcessing = true;
    elements.draftBtn.disabled = true;
    elements.draftBtn.innerHTML = '<div class="spinner"></div> Generating...';

    try {
        const response = await fetch(`${API_BASE}/draft`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                case_id: currentCaseId,
                document_type: docType,
                additional_instructions: instructions
            })
        });
        const data = await response.json();
        appendDraftItem({ id: data.draft_id, document_type: docType, content: data.content });
        showDraftModal(docType, data.content);
        
        // Also add to chat
        appendMessage('assistant', `I've generated a draft for **${docType.replace('_', ' ')}**. You can view it in the side panel.`);
    } catch (err) {
        alert('Failed to generate draft.');
    } finally {
        isProcessing = false;
        elements.draftBtn.disabled = false;
        elements.draftBtn.innerText = 'Generate Draft';
    }
}

function appendDraftItem(draft) {
    const li = document.createElement('li');
    li.className = 'draft-item';
    const typeLabel = draft.document_type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    li.innerHTML = `
        <i class="fa-solid fa-file-signature"></i>
        <span>${typeLabel}</span>
    `;
    li.onclick = () => showDraftModal(typeLabel, draft.content);
    elements.draftsList.appendChild(li);
}

function showDraftModal(title, content) {
    elements.modalTitle.innerText = title;
    elements.modalText.innerText = content;
    elements.draftModal.classList.remove('hidden');
}
