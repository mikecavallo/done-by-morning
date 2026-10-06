// Intake form: posts to the endpoint in config.js, or falls back to a pre-filled email.
(function () {
  const form = document.getElementById('intake-form');
  if (!form) return;
  const cfg = Object.assign(
    { FORM_ENDPOINT: '', FORM_FORMAT: 'formdata', INTAKE_URL: '', CONTACT_EMAIL: 'hello@businessrunsbetter.com' },
    window.DBM_CONFIG || {}
  );
  const status = document.getElementById('intake-status');
  const startedAt = Date.now();

  function setStatus(text, kind, html) {
    status.className = 'full intake-status' + (kind ? ' ' + kind : '');
    if (html) status.innerHTML = html; else status.textContent = text;
  }

  function values() {
    const get = (name) => (form.elements[name] ? form.elements[name].value.trim() : '');
    return {
      name: get('name'), email: get('email'), company: get('company'), plan: get('plan'),
      question: get('question'), context: get('context'), website: get('website'),
    };
  }

  function briefText(v) {
    return [
      'Research question:', v.question, '',
      'Context:', v.context || '(none)', '',
      'Report type: ' + v.plan,
      'Name: ' + v.name,
      'Email: ' + v.email,
      'Company: ' + (v.company || '-'),
    ].join('\n');
  }

  function mailtoHref(v) {
    const subject = 'Done By Morning brief: ' + v.question.slice(0, 60);
    return 'mailto:' + cfg.CONTACT_EMAIL + '?subject=' + encodeURIComponent(subject) +
      '&body=' + encodeURIComponent(briefText(v));
  }

  function fallbackToEmail(v, reason) {
    const href = mailtoHref(v);
    setStatus('', 'err',
      (reason ? reason + ' ' : '') + 'Your email app should open with the brief filled in. ' +
      'If it does not, <a href="' + href.replace(/"/g, '&quot;') + '" style="color: inherit;">click here</a> ' +
      'or write to ' + cfg.CONTACT_EMAIL + '.');
    window.location.href = href;
  }

  function buildRequest(v) {
    const fmt = cfg.FORM_FORMAT;
    if (fmt === 'json') {
      return { headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(v) };
    }
    if (fmt === 'netlify') {
      const p = new URLSearchParams(Object.assign({ 'form-name': 'intake' }, v));
      return { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: p.toString() };
    }
    const fd = new FormData();
    if (fmt === 'brb-contact') {
      fd.append('name', v.name);
      fd.append('email', v.email);
      fd.append('company', v.company);
      fd.append('interest', 'Done By Morning research report');
      fd.append('budget', v.plan);
      fd.append('message', briefText(v));
      fd.append('website', v.website);
      fd.append('started', String(startedAt));
    } else {
      Object.entries(v).forEach(([k, val]) => fd.append(k, val));
      fd.append('_subject', 'Done By Morning brief from ' + v.name);
    }
    return { headers: { Accept: 'application/json' }, body: fd };
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const v = values();
    if (v.website) { setStatus('Thanks! Your brief was sent.', 'ok'); return; } // honeypot
    if (!v.name || !v.question) { setStatus('Please add your name and research question.', 'err'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.email)) { setStatus('Please enter a valid email address.', 'err'); return; }

    if (cfg.INTAKE_URL) {
      const url = new URL(cfg.INTAKE_URL);
      ['name', 'email', 'plan', 'question'].forEach((k) => url.searchParams.set(k, v[k]));
      window.location.href = url.toString();
      return;
    }
    if (!cfg.FORM_ENDPOINT) { fallbackToEmail(v, ''); return; }

    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    setStatus('Sending…', '');
    try {
      const req = buildRequest(v);
      const res = await fetch(cfg.FORM_ENDPOINT, { method: 'POST', headers: req.headers, body: req.body });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      form.reset();
      setStatus('Thanks! Your brief was sent. We will reply by email to confirm scope and price.', 'ok');
    } catch (err) {
      fallbackToEmail(v, 'The form could not be sent.');
    } finally {
      button.disabled = false;
    }
  });
})();
