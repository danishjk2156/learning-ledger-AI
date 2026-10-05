// Learning Ledger — Frontend Client Logic (Scholar & Researcher Edition)

let currentFilter = '';
let currentViewMode = 'grid'; // 'grid' or 'flashcards'
let allClaims = [];

const TAB_META = {
  claims: {
    title: 'Research Ledger',
    subtitle: 'Scientific beliefs grounded in verbatim quotes & validated by Jev 1.13 decision gates.'
  },
  learn: {
    title: 'Record Finding',
    subtitle: 'Verify findings against original paper text using Jev 1.13 typed probability decision gates.'
  },
  ask: {
    title: 'Ask Literature (RAG)',
    subtitle: 'Synthesize research answers with verbatim citations and exact page numbers.'
  },
  drop: {
    title: 'Ingest PDF Papers',
    subtitle: 'Extract text, remove academic watermarks & license banners, and compute Gemini embeddings.'
  },
  audit: {
    title: 'Integrity Audit',
    subtitle: 'Continuous monitoring against Retraction Watch, Crossref errata, and semantic decay.'
  },
  inspector: {
    title: 'DOI & Retraction Tool',
    subtitle: 'Live lookup across Retraction Watch SQLite, Crossref update-to notices, and OpenAlex.'
  }
};

/**
 * Universal safe JSON fetch wrapper.
 * Prevents "Unexpected token 'I'" crashes by inspecting status & text before JSON parsing.
 */
async function safeFetchJson(url, options = {}) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (netErr) {
    throw new Error(`Network error connecting to backend: ${netErr.message}`);
  }

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (jsonErr) {
    if (!res.ok) {
      throw new Error(`Server Error (${res.status}): ${text.slice(0, 200) || res.statusText}`);
    }
    throw new Error(`Invalid JSON response: ${text.slice(0, 100)}`);
  }

  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed with status ${res.status}`);
  }

  return data;
}

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initDragAndDrop();
  initFormHandlers();
  refreshAll();
});

// ── Tab Navigation ──

function switchTab(tabId) {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });

  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === `pane-${tabId}`);
  });

  const meta = TAB_META[tabId] || { title: 'Learning Ledger', subtitle: '' };
  document.getElementById('view-title').textContent = meta.title;
  document.getElementById('view-subtitle').textContent = meta.subtitle;

  if (tabId === 'claims') loadClaims();
}

function initNavigation() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Claims Filter Buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      filterAndRenderClaims();
    });
  });

  // Search Box
  const searchInput = document.getElementById('claims-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', () => filterAndRenderClaims());
  }
}

// ── View Mode Toggle (Journal Grid vs Student Study Cards) ──

function setClaimsViewMode(mode) {
  currentViewMode = mode;
  document.getElementById('btn-view-grid')?.classList.toggle('active', mode === 'grid');
  document.getElementById('btn-view-flashcards')?.classList.toggle('active', mode === 'flashcards');
  filterAndRenderClaims();
}

// ── API Operations & Refresh ──

async function refreshAll() {
  await Promise.all([
    checkSystemStatus(),
    loadStats(),
    loadClaims()
  ]);
}

async function checkSystemStatus() {
  try {
    const data = await safeFetchJson('/api/status');
    const dot = document.querySelector('.status-dot');
    const text = document.getElementById('status-desc-text');
    const banner = document.getElementById('api-warning-banner');
    const bannerText = document.getElementById('api-warning-text');

    if (data.ok) {
      if (dot) dot.className = 'status-dot';
      if (text) text.textContent = 'Gemini & Jev Online';
      if (banner) banner.style.display = 'none';
    } else {
      if (dot) dot.className = 'status-dot warning';
      if (text) text.textContent = 'API Keys Missing in .env';

      const missing = [];
      if (!data.keys.GOOGLE_API_KEY) missing.push('GOOGLE_API_KEY');
      if (!data.keys.OPENROUTER_API_KEY) missing.push('OPENROUTER_API_KEY');

      if (banner && missing.length > 0) {
        banner.style.display = 'flex';
        bannerText.textContent = `Missing keys in .env: ${missing.join(', ')}. Ingestion & claim verification require these.`;
      }
    }
  } catch (err) {
    console.error('Failed to check status:', err);
  }
}

async function loadStats() {
  try {
    const data = await safeFetchJson('/api/stats');

    document.getElementById('stat-total-claims').textContent = data.total_claims;
    document.getElementById('stat-active-claims').textContent = data.active_claims;
    document.getElementById('stat-suspect-claims').textContent = data.suspect_claims;
    document.getElementById('stat-retracted-claims').textContent = data.retracted_claims;
    document.getElementById('stat-chunks-indexed').textContent = data.chunks_indexed;
    document.getElementById('badge-active-claims').textContent = data.active_claims;

    // Sidebar summary badge
    const sidebarSummary = document.getElementById('sidebar-indexed-summary');
    if (sidebarSummary) {
      sidebarSummary.textContent = `${data.papers_count} Papers • ${data.active_claims} Active Claims`;
    }

    const flaggedBadge = document.getElementById('badge-flagged-claims');
    const flaggedCount = data.suspect_claims + data.retracted_claims;
    if (flaggedCount > 0) {
      flaggedBadge.textContent = flaggedCount;
      flaggedBadge.style.display = 'inline-block';
    } else {
      flaggedBadge.style.display = 'none';
    }

    updateIndexedSourcesBadge(data);
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

async function loadClaims() {
  const container = document.getElementById('claims-container');
  try {
    allClaims = await safeFetchJson('/api/claims');
    filterAndRenderClaims();
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h4>Error loading research ledger</h4><p>${escapeHtml(err.message)}</p></div>`;
  }
}

function filterAndRenderClaims() {
  const container = document.getElementById('claims-container');
  const query = (document.getElementById('claims-search-input')?.value || '').toLowerCase().trim();

  let filtered = allClaims;
  if (currentFilter) {
    filtered = filtered.filter(c => c.status === currentFilter);
  }
  if (query) {
    filtered = filtered.filter(c => 
      (c.claim || '').toLowerCase().includes(query) ||
      (c.doi || '').toLowerCase().includes(query) ||
      (c.source_title || '').toLowerCase().includes(query) ||
      (c.quote || '').toLowerCase().includes(query)
    );
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="8" y1="12" x2="16" y2="12"></line></svg>
        <h4>No claims found</h4>
        <p>${query || currentFilter ? 'Try clearing your search query or filter.' : 'Click "+ Record Finding" above to record what you learned.'}</p>
      </div>`;
    return;
  }

  container.innerHTML = filtered.map(claim => {
    const conf = Math.round((claim.confidence || 0) * 100);
    const confClass = conf >= 80 ? 'conf-high' : conf >= 50 ? 'conf-med' : 'conf-low';
    const statusClass = `status-${claim.status || 'active'}`;

    if (currentViewMode === 'flashcards') {
      // 🎓 Student Study Card Mode
      return `
        <div class="claim-card ${statusClass} flashcard-mode" id="card-${claim.claim_id}">
          <div class="claim-card-header">
            <span class="claim-id">#${claim.claim_id}</span>
            <span class="status-badge ${claim.status}">${claim.status}</span>
          </div>

          <div style="font-size: 0.72rem; font-family: var(--font-mono); color: var(--accent-gold); text-transform: uppercase;">
            🎓 STUDY PROMPT: CAN YOU CITE THE PROOF?
          </div>

          <div class="claim-text">${escapeHtml(claim.claim)}</div>

          <button class="flashcard-prompt-btn" onclick="toggleFlashcardReveal('${claim.claim_id}')">
            🔍 Reveal Supporting Quote & Verification
          </button>

          ${claim.quote ? `
            <div class="claim-quote-box ${claim.status === 'retracted' ? 'retracted' : ''}">
              ${escapeHtml(claim.quote)}
            </div>
          ` : ''}

          <div class="claim-meta">
            <div class="confidence-meter ${confClass}">
              <span class="conf-dot"></span>
              <span>${conf}% Jev support</span>
            </div>
            <div>
              ${claim.doi ? `<a href="https://doi.org/${encodeURIComponent(claim.doi)}" target="_blank" class="claim-doi-tag">DOI: ${escapeHtml(claim.doi)}</a>` : ''}
              ${claim.page ? ` <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-dim);">• p.${claim.page}</span>` : ''}
            </div>
          </div>

          <div class="claim-actions">
            <button class="btn-xs btn-cite-xs" onclick="citeClaim('${claim.claim_id}')">Cite (APA)</button>
            ${claim.status !== 'active' ? `<button class="btn-xs" onclick="updateClaimStatusAction('${claim.claim_id}', 'active')">Mark Active</button>` : ''}
            ${claim.status !== 'suspect' ? `<button class="btn-xs" onclick="updateClaimStatusAction('${claim.claim_id}', 'suspect')">Mark Suspect</button>` : ''}
            ${claim.status !== 'retracted' ? `<button class="btn-xs btn-danger-xs" onclick="updateClaimStatusAction('${claim.claim_id}', 'retracted')">Mark Retracted</button>` : ''}
          </div>
        </div>
      `;
    }

    // 📜 Traditional Academic Journal Card View
    return `
      <div class="claim-card ${statusClass}">
        <div class="claim-card-header">
          <span class="claim-id">#${claim.claim_id}</span>
          <span class="status-badge ${claim.status}">${claim.status}</span>
        </div>

        <div class="claim-text">${escapeHtml(claim.claim)}</div>

        ${claim.quote ? `
          <div class="claim-quote-box ${claim.status === 'retracted' ? 'retracted' : ''}">
            ${escapeHtml(claim.quote)}
          </div>
        ` : ''}

        ${claim.note ? `
          <div style="font-size: 0.8rem; color: var(--text-muted); background: rgba(0,0,0,0.3); padding: 0.5rem 0.75rem; border-radius: 4px; border-left: 2px solid var(--accent-amber);">
            💬 ${escapeHtml(claim.note)}
          </div>
        ` : ''}

        <div class="claim-meta">
          <div class="confidence-meter ${confClass}">
            <span class="conf-dot"></span>
            <span>${conf}% Jev support</span>
          </div>

          <div>
            ${claim.doi ? `<a href="https://doi.org/${encodeURIComponent(claim.doi)}" target="_blank" class="claim-doi-tag" title="Open paper DOI in browser">DOI: ${escapeHtml(claim.doi)}</a>` : ''}
            ${claim.page ? ` <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-dim);">• p.${claim.page}</span>` : ''}
          </div>
        </div>

        <div class="claim-actions">
          <button class="btn-xs btn-cite-xs" onclick="citeClaim('${claim.claim_id}')" title="Copy formatted citation to clipboard">Cite (APA)</button>
          ${claim.status !== 'active' ? `<button class="btn-xs" onclick="updateClaimStatusAction('${claim.claim_id}', 'active')">Mark Active</button>` : ''}
          ${claim.status !== 'suspect' ? `<button class="btn-xs" onclick="updateClaimStatusAction('${claim.claim_id}', 'suspect')">Mark Suspect</button>` : ''}
          ${claim.status !== 'retracted' ? `<button class="btn-xs btn-danger-xs" onclick="updateClaimStatusAction('${claim.claim_id}', 'retracted')">Mark Retracted</button>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function toggleFlashcardReveal(claimId) {
  const card = document.getElementById(`card-${claimId}`);
  if (card) {
    card.classList.toggle('revealed');
  }
}

function citeClaim(claimId) {
  const claim = allClaims.find(c => c.claim_id === claimId);
  if (!claim) return;

  const conf = Math.round((claim.confidence || 0) * 100);
  const citationText = `"${claim.claim}" — Supported by: ${claim.source_title || 'Research Paper'}${claim.doi ? ` (DOI: ${claim.doi})` : ''}${claim.page ? `, p. ${claim.page}` : ''}. [Verified with ${conf}% confidence via Jev 1.13 Decision Gate in Learning Ledger]`;

  navigator.clipboard.writeText(citationText).then(() => {
    showToast('Citation copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy citation', 'error');
  });
}

async function updateClaimStatusAction(claimId, status) {
  try {
    await safeFetchJson(`/api/claims/${claimId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    showToast(`Claim marked as ${status}`, 'info');
    await refreshAll();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Student Sample Fillers ──

function fillSampleClaim(sampleKey) {
  const samples = {
    lora: {
      claim: "LoRA achieves comparable performance to full fine-tuning on large language models while reducing trainable parameters by up to 10,000x and GPU memory overhead by 3x.",
      quote: "When compared to GPT-3 175B fine-tuned with Adam, LoRA can reduce the number of trainable parameters by 10,000 times and the GPU memory requirement by 3 times.",
      doi: "10.48550/arXiv.2106.09685",
      title: "LoRA: Low-Rank Adaptation of Large Language Models",
      page: 1
    },
    transformer: {
      claim: "The Transformer architecture relies entirely on self-attention mechanisms to compute input and output representations without sequence-aligned RNNs or convolution.",
      quote: "The Transformer is the first transduction model relying entirely on self-attention to compute representations of its input and output without using sequencealigned RNNs or convolution.",
      doi: "10.48550/arXiv.1706.03762",
      title: "Attention Is All You Need",
      page: 2
    }
  };

  const sample = samples[sampleKey];
  if (!sample) return;

  document.getElementById('learn-claim-input').value = sample.claim;
  document.getElementById('learn-quote-input').value = sample.quote;
  document.getElementById('learn-doi-input').value = sample.doi;
  document.getElementById('learn-title-input').value = sample.title;
  document.getElementById('learn-page-input').value = sample.page;

  showToast(`Sample '${sample.title}' loaded into form`, 'info');
}

// ── Form Handlers ──

function initFormHandlers() {
  const learnForm = document.getElementById('record-claim-form') || document.getElementById('form-learn-claim');
  if (learnForm) {
    learnForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const claim = document.getElementById('learn-claim-input').value.trim();
      const quote = document.getElementById('learn-quote-input').value.trim();
      const doi = document.getElementById('learn-doi-input').value.trim();
      const title = document.getElementById('learn-title-input').value.trim();
      const page = parseInt(document.getElementById('learn-page-input').value, 10) || 0;

      const previewBox = document.getElementById('learn-result-box') || document.getElementById('learn-eval-preview');
      const btn = document.getElementById('btn-submit-claim');
      const spinner = btn?.querySelector('.btn-spinner');
      const textSpan = btn?.querySelector('span');

      if (spinner) spinner.style.display = 'inline-block';
      if (textSpan) textSpan.textContent = 'Evaluating with Jev 1.13...';
      if (btn) btn.disabled = true;

      try {
        const data = await safeFetchJson('/api/learn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ claim, quote, doi, title, page })
        });

        showToast('Claim verified & saved to ledger!', 'success');
        if (previewBox) {
          previewBox.style.display = 'block';
          previewBox.innerHTML = `
            <h4 style="color: var(--accent-emerald); margin-bottom: 0.5rem; font-family: var(--font-serif); font-size: 1.1rem;">✅ Jev Verified & Recorded</h4>
            <pre style="font-family: var(--font-mono); font-size: 0.85rem; color: #d1d5db; white-space: pre-wrap; background: rgba(0,0,0,0.3); padding: 0.85rem; border-radius: 6px;">${escapeHtml(data.message)}</pre>
          `;
        }

        learnForm.reset();
        await refreshAll();
      } catch (err) {
        showToast(err.message, 'error');
        if (previewBox) {
          previewBox.style.display = 'block';
          previewBox.innerHTML = `
            <h4 style="color: var(--accent-rose); margin-bottom: 0.5rem;">❌ Verification Error</h4>
            <p style="font-size: 0.88rem; color: #d1d5db;">${escapeHtml(err.message)}</p>
          `;
        }
      } finally {
        if (spinner) spinner.style.display = 'none';
        if (textSpan) textSpan.textContent = 'Verify with Jev & Save to Ledger';
        if (btn) btn.disabled = false;
      }
    });
  }
}

// ── Research Chat (RAG) ──

function formatResearchAnswer(text) {
  if (!text) return '';

  let html = escapeHtml(text);

  // Convert headers ### Title -> <h4 class="chat-heading">Title</h4>
  html = html.replace(/^###\s+(.+)$/gm, '<h4 class="chat-heading">$1</h4>');
  html = html.replace(/^##\s+(.+)$/gm, '<h3 class="chat-heading-lg">$1</h3>');

  // Convert bold **text** -> <strong>text</strong>
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Convert italics *text* -> <em>text</em>
  html = html.replace(/(^|[^\*])\*([^\*]+?)\*([^\*]|$)/g, '$1<em>$2</em>$3');

  // Convert inline citations [Paper.pdf, p.X] into sleek interactive badges
  html = html.replace(/\[([^[\]]+?,\s*p\.?\s*\d+)\]/g, '<span class="citation-pill"><span class="pill-dot"></span>$1</span>');
  html = html.replace(/\[Page\s*(\d+)\]/gi, '<span class="citation-pill"><span class="pill-dot"></span>Page $1</span>');

  // Convert lists
  const lines = html.split('\n');
  let inList = false;
  let formatted = [];

  for (let line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
      if (!inList) {
        formatted.push('<ul class="chat-list">');
        inList = true;
      }
      const itemText = trimmed.replace(/^[\*\-•]\s+/, '');
      formatted.push(`<li>${itemText}</li>`);
    } else {
      if (inList) {
        formatted.push('</ul>');
        inList = false;
      }
      if (trimmed.length > 0) {
        if (trimmed.startsWith('<h3') || trimmed.startsWith('<h4')) {
          formatted.push(trimmed);
        } else {
          formatted.push(`<p>${trimmed}</p>`);
        }
      }
    }
  }
  if (inList) formatted.push('</ul>');

  return formatted.join('\n');
}

function applyPromptQuery(promptText) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = promptText;
    input.focus();
  }
}

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;

  const chatContainer = document.getElementById('chat-messages');

  // Add User Message
  const userMsg = document.createElement('div');
  userMsg.className = 'message user';
  userMsg.innerHTML = `<div class="msg-bubble"><p>${escapeHtml(query)}</p></div>`;
  chatContainer.appendChild(userMsg);
  input.value = '';
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // Add Assistant Thinking Message
  const thinkingMsg = document.createElement('div');
  thinkingMsg.className = 'message assistant';
  thinkingMsg.innerHTML = `
    <div class="msg-avatar">📚</div>
    <div class="msg-bubble">
      <div class="spinner" style="width: 18px; height: 18px; margin: 0; display: inline-block;"></div>
      <span style="margin-left: 0.5rem; font-size: 0.85rem; color: var(--text-muted);">Searching indexed literature & synthesizing with Gemini...</span>
    </div>
  `;
  chatContainer.appendChild(thinkingMsg);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const data = await safeFetchJson('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: query, n_results: 6 })
    });

    thinkingMsg.querySelector('.msg-bubble').innerHTML = `
      <div class="chat-formatted-body">${formatResearchAnswer(data.answer)}</div>
      ${data.sources && data.sources.length > 0 ? `
        <details style="margin-top: 1rem; font-size: 0.8rem; color: var(--text-dim); border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.65rem;">
          <summary style="cursor: pointer; color: var(--accent-cambridge); font-weight: 600; display: flex; align-items: center; gap: 0.4rem;">
            <span>🔍 View ${data.sources.length} Retrieved Literature Excerpts</span>
          </summary>
          <div style="margin-top: 0.65rem; display: flex; flex-direction: column; gap: 0.5rem;">
            ${data.sources.map((s, idx) => `
              <div style="background: rgba(0,0,0,0.35); padding: 0.6rem 0.8rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.04);">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                  <strong style="color: var(--accent-cambridge); font-size: 0.78rem;">#${idx+1} ${escapeHtml(s.meta?.source || 'Paper')}</strong>
                  <span class="citation-pill" style="margin: 0; padding: 0.1rem 0.4rem; font-size: 0.7rem;">p.${s.meta?.page || '?'}</span>
                </div>
                <div style="font-size: 0.8rem; color: #cbd5e1; line-height: 1.45; font-family: var(--font-serif); font-style: italic;">“${escapeHtml(s.text.substring(0, 220))}...”</div>
              </div>
            `).join('')}
          </div>
        </details>
      ` : ''}
    `;
  } catch (err) {
    thinkingMsg.querySelector('.msg-bubble').innerHTML = `
      <p style="color: #f87171; font-weight: 500;">❌ ${escapeHtml(err.message)}</p>
    `;
  }
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function updateIndexedSourcesBadge(stats) {
  const badge = document.getElementById('indexed-sources-badge');
  if (badge && stats) {
    badge.textContent = `${stats.papers_count} Papers (${stats.chunks_indexed} Chunks)`;
  }
}

// ── Drop PDF Zone & Ingestion ──

let selectedPdfFile = null;

function initDragAndDrop() {
  const dropZone = document.getElementById('pdf-drop-zone');
  const fileInput = document.getElementById('pdf-file-input');
  const pill = document.getElementById('selected-file-pill');

  if (!dropZone || !fileInput) return;

  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileSelected(fileInput.files[0]);
    }
  });

  function handleFileSelected(file) {
    if (!file.name.endsWith('.pdf')) {
      showToast('Please select an academic PDF manuscript', 'error');
      return;
    }
    selectedPdfFile = file;
    pill.style.display = 'inline-block';
    pill.textContent = `Selected: ${file.name} (${(file.size / (1024*1024)).toFixed(2)} MB)`;
  }
}

async function handlePaperIngest() {
  const pathInput = document.getElementById('drop-path-input');
  const doiInput = document.getElementById('drop-doi-input');
  const titleInput = document.getElementById('drop-title-input');
  const statusBox = document.getElementById('ingest-status-box');
  const btn = document.getElementById('btn-ingest-paper');

  const path = pathInput.value.trim();
  const doi = doiInput.value.trim();
  const title = titleInput.value.trim();

  if (!selectedPdfFile && !path) {
    showToast('Please select a PDF file or enter a local path', 'error');
    return;
  }

  btn.disabled = true;
  btn.querySelector('.btn-spinner').style.display = 'inline-block';
  btn.querySelector('span').textContent = 'Ingesting & Embedding...';
  statusBox.style.display = 'block';
  statusBox.innerHTML = '<span style="color: var(--accent-cambridge);">Chunking manuscript by academic headings & computing Gemini embeddings...</span>';

  const formData = new FormData();
  if (selectedPdfFile) {
    formData.append('file', selectedPdfFile);
  } else if (path) {
    formData.append('path', path);
  }
  if (doi) formData.append('doi', doi);
  if (title) formData.append('title', title);

  try {
    const data = await safeFetchJson('/api/drop', {
      method: 'POST',
      body: formData
    });

    showToast('Paper ingested successfully into research collection!', 'success');
    statusBox.innerHTML = `<pre style="font-family: var(--font-mono); font-size: 0.85rem; color: #34d399; white-space: pre-wrap;">${escapeHtml(data.message)}</pre>`;
    await refreshAll();
  } catch (err) {
    showToast(err.message, 'error');
    statusBox.innerHTML = `<p style="color: #f87171;">❌ ${escapeHtml(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    btn.querySelector('.btn-spinner').style.display = 'none';
    btn.querySelector('span').textContent = 'Ingest & Embed Paper';
  }
}

async function handleReindexLibrary() {
  const btn = document.getElementById('btn-reindex-paper');
  const statusBox = document.getElementById('ingest-status-box');

  if (!confirm('This will wipe the vector collection and re-index all papers in library/ with clean semantic header chunking and publisher watermark filtering. Proceed?')) {
    return;
  }

  btn.disabled = true;
  btn.querySelector('.btn-spinner').style.display = 'inline-block';
  btn.querySelector('span').textContent = 'Purging & Re-indexing...';
  statusBox.style.display = 'block';
  statusBox.innerHTML = '<span style="color: var(--accent-cambridge);">Purging contaminated chunks and re-embedding clean academic sections...</span>';

  try {
    const data = await safeFetchJson('/api/reindex', { method: 'POST' });
    showToast('Library successfully re-indexed!', 'success');
    statusBox.innerHTML = `<pre style="font-family: var(--font-mono); font-size: 0.85rem; color: #34d399; white-space: pre-wrap;">${escapeHtml(data.message)}\nTotal clean chunks indexed: ${data.total_chunks}</pre>`;
    await refreshAll();
  } catch (err) {
    showToast(err.message, 'error');
    statusBox.innerHTML = `<p style="color: #f87171;">❌ ${escapeHtml(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    btn.querySelector('.btn-spinner').style.display = 'none';
    btn.querySelector('span').textContent = '🧹 Purge & Clean Re-index';
  }
}

// ── Revalidation Audit ──

async function runFullAudit() {
  const btn = document.getElementById('btn-run-audit');
  const area = document.getElementById('audit-results-area');

  btn.disabled = true;
  btn.querySelector('.btn-spinner').style.display = 'inline-block';
  btn.querySelector('span').textContent = 'Auditing Claims...';

  area.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <span>Auditing claims against Retraction Watch, Crossref & Jev semantic decay...</span>
    </div>
  `;

  try {
    const data = await safeFetchJson('/api/revalidate', { method: 'POST' });

    const flagged = data.flagged || [];
    if (flagged.length === 0) {
      area.innerHTML = `
        <div class="glass-card scholar-card" style="border-color: rgba(16, 185, 129, 0.4); text-align: center; padding: 3rem;">
          <h3 style="color: #34d399; margin-bottom: 0.5rem; font-family: var(--font-serif);">🎉 All Research Claims Verified</h3>
          <p style="color: var(--text-muted);">No retractions, errata, or quote support decay detected across your active knowledge base.</p>
        </div>
      `;
    } else {
      area.innerHTML = `
        <div style="margin-bottom: 1rem; color: #fbbf24; font-weight: 700; font-family: var(--font-serif); font-size: 1.15rem;">
          ⚠️ ${flagged.length} claim(s) require your immediate attention:
        </div>
        ${flagged.map(f => `
          <div class="audit-item action-${f.action.toLowerCase()}">
            <span class="audit-action-pill ${f.action.toLowerCase()}">${f.action}</span>
            <div class="audit-details">
              <h4>"${escapeHtml(f.claim)}"</h4>
              <p><strong>Reason:</strong> ${escapeHtml(f.reason)}</p>
              <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-dim);">Claim ID: #${f.claim_id}</span>
            </div>
          </div>
        `).join('')}
      `;
    }

    await refreshAll();
  } catch (err) {
    showToast(err.message, 'error');
    area.innerHTML = `<p style="color: #f87171;">❌ ${escapeHtml(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    btn.querySelector('.btn-spinner').style.display = 'none';
    btn.querySelector('span').textContent = 'Run Integrity Audit Now';
  }
}

// ── DOI Inspector ──

function inspectQuickDoi(doi) {
  const input = document.getElementById('inspect-doi-input');
  if (input) {
    input.value = doi;
    runInspector();
  }
}

async function runInspector() {
  const input = document.getElementById('inspect-doi-input');
  const output = document.getElementById('inspector-output');
  const doi = input.value.trim();

  if (!doi) {
    showToast('Enter a DOI first', 'error');
    return;
  }

  output.style.display = 'block';
  output.innerHTML = '<div class="spinner"></div>';

  try {
    const data = await safeFetchJson(`/api/check-doi?doi=${encodeURIComponent(doi)}`);

    output.innerHTML = `
      <pre style="font-family: var(--font-mono); font-size: 0.88rem; background: rgba(0,0,0,0.45); padding: 1.25rem; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); color: #e5e7eb; white-space: pre-wrap; line-height: 1.6;">${escapeHtml(data.formatted)}</pre>
    `;
  } catch (err) {
    output.innerHTML = `<p style="color: #f87171;">❌ ${escapeHtml(err.message)}</p>`;
  }
}

// ── Helper Utilities ──

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
