/**
 * Hephaestus Web UI — Client JavaScript
 * Handles SSE streaming, progress UI, and result rendering.
 */

(function () {
  'use strict';

  // ── DOM refs ──────────────────────────────────────────────────────────────

  const problemInput     = document.getElementById('problem');
  const depthSlider      = document.getElementById('depth');
  const depthValue       = document.getElementById('depth-value');
  const candidatesSlider = document.getElementById('candidates');
  const candidatesValue  = document.getElementById('candidates-value');
  const modelSelect      = document.getElementById('model');
  const forgeBtn         = document.getElementById('forge-btn');
  const btnText          = document.getElementById('btn-text');

  const progressSection  = document.getElementById('progress-section');
  const stageList        = document.getElementById('stage-list');

  const resultSection    = document.getElementById('result-section');
  const errorBox         = document.getElementById('error-box');
  const errorMsg         = document.getElementById('error-message');

  // Result fields
  const resName          = document.getElementById('res-invention-name');
  const resSource        = document.getElementById('res-source-domain');
  const resNativeStr     = document.getElementById('res-native-structure');
  const resNoveltyScore  = document.getElementById('res-novelty-score');
  const resValidity      = document.getElementById('res-validity');
  const resFeasibility   = document.getElementById('res-feasibility');
  const resVerdict       = document.getElementById('res-verdict');
  const resKeyInsight    = document.getElementById('res-key-insight');
  const resArchitecture  = document.getElementById('res-architecture');
  const resMapping       = document.getElementById('res-mapping');
  const resLimitations   = document.getElementById('res-limitations');
  const resAlternatives  = document.getElementById('res-alternatives');
  const resCost          = document.getElementById('res-cost');
  const resDuration      = document.getElementById('res-duration');
  const resModels        = document.getElementById('res-models');

  // ── Slider live-update ────────────────────────────────────────────────────

  if (depthSlider && depthValue) {
    depthSlider.addEventListener('input', () => {
      depthValue.textContent = depthSlider.value;
    });
  }

  if (candidatesSlider && candidatesValue) {
    candidatesSlider.addEventListener('input', () => {
      candidatesValue.textContent = candidatesSlider.value;
    });
  }

  // ── Active SSE connection (stored so we can abort) ────────────────────────

  let activeController = null;

  // ── Forge submission ──────────────────────────────────────────────────────

  const forgeForm = document.getElementById('forge-form');
  if (forgeForm) {
    forgeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await startForge();
    });
  }

  async function startForge() {
    const problem = problemInput?.value?.trim();
    if (!problem || problem.length < 5) {
      showError('Please enter a problem description (at least 5 characters).');
      return;
    }

    // Abort any in-flight request
    if (activeController) {
      activeController.abort();
      activeController = null;
    }

    const payload = {
      problem,
      depth:      parseInt(depthSlider?.value || '3', 10),
      model:      modelSelect?.value || 'both',
      candidates: parseInt(candidatesSlider?.value || '8', 10),
    };

    // Reset UI
    resetUI();
    progressSection.classList.add('visible');
    forgeBtn.disabled = true;
    forgeBtn.classList.add('loading');
    btnText.textContent = '⚒  Forging...';

    activeController = new AbortController();

    try {
      const response = await fetch('/api/invent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(payload),
        signal: activeController.signal,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }

      await consumeSSE(response);
    } catch (err) {
      if (err.name === 'AbortError') return;
      showError(err.message || 'Connection failed');
      resetForgeBtn();
    }
  }

  // ── SSE stream consumer ───────────────────────────────────────────────────

  async function consumeSSE(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = parseSSEBuffer(buffer);
        buffer = events.remainder;

        for (const ev of events.events) {
          handleSSEEvent(ev.type, ev.data);
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        showError(err.message || 'Stream error');
      }
    } finally {
      resetForgeBtn();
    }
  }

  function parseSSEBuffer(text) {
    const events = [];
    const lines = text.split('\n');
    let remainder = '';
    let currentEvent = { type: 'message', data: '' };
    let inEvent = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith('event: ')) {
        currentEvent.type = line.slice(7).trim();
        inEvent = true;
      } else if (line.startsWith('data: ')) {
        currentEvent.data = line.slice(6).trim();
        inEvent = true;
      } else if (line === '' && inEvent) {
        // End of event block
        if (currentEvent.data) {
          events.push({ ...currentEvent });
        }
        currentEvent = { type: 'message', data: '' };
        inEvent = false;
      } else if (i === lines.length - 1 && line !== '') {
        // Incomplete last line — save for next chunk
        remainder = line;
      }
    }

    return { events, remainder };
  }

  function handleSSEEvent(type, rawData) {
    let data;
    try {
      data = JSON.parse(rawData);
    } catch {
      return;
    }

    switch (type) {
      case 'stage':
        addStageUpdate(data);
        break;
      case 'result':
        renderResult(data);
        break;
      case 'error':
        showError(data.message || 'Unknown error');
        addStageUpdate({
          stage: 'FAILED',
          icon: '✗',
          label: 'Pipeline failed',
          message: data.message,
          elapsed_seconds: data.elapsed_seconds || 0,
        });
        break;
    }
  }

  // ── Stage progress ────────────────────────────────────────────────────────

  let lastStageEl = null;

  function addStageUpdate(data) {
    // Remove spinner from last stage
    if (lastStageEl) {
      const spinner = lastStageEl.querySelector('.spinner');
      if (spinner) spinner.remove();
    }

    const el = document.createElement('div');
    el.className = 'pipeline-stage';

    const isTerminal = data.stage === 'COMPLETE' || data.stage === 'FAILED';
    const isActive = !isTerminal;

    el.innerHTML = `
      <div class="stage-icon">${isActive ? '<span class="spinner"></span>' : (data.icon || '◦')}</div>
      <div class="stage-body">
        <div class="stage-label">${escHtml(data.label || data.stage)}</div>
        <div class="stage-message">${escHtml(data.message || '')}</div>
      </div>
      <div class="stage-elapsed">${data.elapsed_seconds != null ? data.elapsed_seconds + 's' : ''}</div>
    `;

    if (data.stage === 'FAILED') {
      el.style.opacity = '0.7';
      const iconEl = el.querySelector('.stage-icon');
      if (iconEl) iconEl.style.color = 'var(--red)';
    }
    if (data.stage === 'COMPLETE') {
      const iconEl = el.querySelector('.stage-icon');
      if (iconEl) iconEl.style.color = 'var(--green)';
    }

    stageList.appendChild(el);
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    lastStageEl = isActive ? el : null;
  }

  // ── Result rendering ──────────────────────────────────────────────────────

  function renderResult(data) {
    if (!data || data.error) {
      showError(data?.error || 'No result data received.');
      return;
    }

    // Hero
    if (resName)     resName.textContent = data.invention_name || 'Unknown';
    if (resSource)   resSource.innerHTML = `From <span class="domain">${escHtml(data.source_domain || '')}</span>`;

    if (resNativeStr && data.native_domain) {
      resNativeStr.textContent = `${data.native_domain} → ${data.mathematical_shape || ''}`;
    }

    // Scores
    if (resNoveltyScore) {
      const val = typeof data.novelty_score === 'number' ? data.novelty_score : 0;
      resNoveltyScore.textContent = val.toFixed(2);
      resNoveltyScore.className = 'badge-value ' + scoreClass(val);
    }
    if (resValidity) {
      const val = typeof data.structural_validity === 'number' ? data.structural_validity : 0;
      resValidity.textContent = val.toFixed(2);
      resValidity.className = 'badge-value ' + scoreClass(val);
    }
    if (resFeasibility) {
      resFeasibility.textContent = data.feasibility_rating || '—';
      resFeasibility.className = 'badge-value ' + feasibilityClass(data.feasibility_rating);
    }

    // Verdict
    if (resVerdict) {
      const verdict = (data.verdict || 'UNKNOWN').toLowerCase();
      resVerdict.textContent = data.verdict || '—';
      resVerdict.className = 'verdict-badge ' + verdict;
    }

    // Key insight
    if (resKeyInsight) resKeyInsight.textContent = data.key_insight || '';

    // Architecture
    if (resArchitecture) resArchitecture.textContent = data.architecture || '';

    // Mapping table
    if (resMapping && Array.isArray(data.mapping) && data.mapping.length > 0) {
      resMapping.innerHTML = buildMappingTable(data.mapping);
    } else if (resMapping) {
      resMapping.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">No mapping data available.</p>';
    }

    // Limitations
    if (resLimitations) {
      if (Array.isArray(data.limitations) && data.limitations.length > 0) {
        resLimitations.innerHTML = '<ul class="limitations-list">' +
          data.limitations.map(l => `<li>${escHtml(l)}</li>`).join('') +
          '</ul>';
      } else {
        resLimitations.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">None reported.</p>';
      }
    }

    // Alternatives
    if (resAlternatives) {
      if (Array.isArray(data.alternatives) && data.alternatives.length > 0) {
        resAlternatives.innerHTML = '<div class="alt-grid">' +
          data.alternatives.map(alt => `
            <div class="alt-card">
              <div class="alt-name">${escHtml(alt.name)}</div>
              <div class="alt-meta">
                <span class="alt-domain">${escHtml(alt.source_domain)}</span>
                · novelty ${(alt.novelty_score || 0).toFixed(2)}
              </div>
            </div>
          `).join('') +
          '</div>';
      } else {
        resAlternatives.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">No alternatives.</p>';
      }
    }

    // Cost / meta
    if (resCost)     resCost.textContent = `$${(data.cost_usd || 0).toFixed(4)}`;
    if (resDuration) resDuration.textContent = `${data.duration_seconds || 0}s`;
    if (resModels && data.models) {
      resModels.textContent = Object.values(data.models).filter(Boolean).join(', ');
    }

    // Show result, scroll to it
    resultSection.classList.add('visible');
    setTimeout(() => {
      resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 150);
  }

  function buildMappingTable(mapping) {
    return `
      <table class="mapping-table">
        <thead>
          <tr>
            <th>Foreign Element</th>
            <th>Target Element</th>
            <th>Mechanism</th>
          </tr>
        </thead>
        <tbody>
          ${mapping.map(row => `
            <tr>
              <td>${escHtml(row.source || '')}</td>
              <td>${escHtml(row.target || '')}</td>
              <td>${escHtml(row.mechanism || '')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  // ── Error display ─────────────────────────────────────────────────────────

  function showError(message) {
    if (!errorBox || !errorMsg) return;
    errorMsg.textContent = message;
    errorBox.classList.add('visible');
    errorBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function hideError() {
    if (errorBox) errorBox.classList.remove('visible');
  }

  // ── UI helpers ────────────────────────────────────────────────────────────

  function resetUI() {
    if (stageList)      stageList.innerHTML = '';
    if (progressSection) progressSection.classList.remove('visible');
    if (resultSection)  resultSection.classList.remove('visible');
    hideError();
    lastStageEl = null;
  }

  function resetForgeBtn() {
    if (!forgeBtn) return;
    forgeBtn.disabled = false;
    forgeBtn.classList.remove('loading');
    if (btnText) btnText.textContent = '⚒  Forge Invention';
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function scoreClass(val) {
    if (val >= 0.7) return 'high';
    if (val >= 0.4) return 'medium';
    return 'low';
  }

  function feasibilityClass(rating) {
    if (!rating) return 'medium';
    const r = rating.toUpperCase();
    if (r === 'HIGH') return 'high';
    if (r === 'MEDIUM') return 'medium';
    return 'low';
  }

  // ── Health check banner ───────────────────────────────────────────────────

  async function checkHealth() {
    try {
      const res = await fetch('/api/health');
      if (!res.ok) return;
      const data = await res.json();
      const warningEl = document.getElementById('config-warning');
      if (!warningEl) return;

      const warnings = [];
      if (!data.anthropic_configured) warnings.push('ANTHROPIC_API_KEY not set');
      if (!data.openai_configured)    warnings.push('OPENAI_API_KEY not set');

      if (warnings.length > 0) {
        warningEl.textContent = '⚠ ' + warnings.join(', ') + ' — some models unavailable';
        warningEl.style.display = 'block';
      }
    } catch {
      // Server might not be ready
    }
  }

  checkHealth();

})();
