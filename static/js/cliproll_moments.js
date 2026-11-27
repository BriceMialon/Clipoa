/* ClipRoll — micro-interactions (« UI moments »).
 *
 * 1. Suivi de fabrication par étapes : ClipRollMoments.stepsHtml(job)
 *    rend une piste d'étapes (Script, Voix & son, Décor & montage, Contrôle)
 *    dont l'étape en cours se remplit selon la progression réelle.
 * 2. « Maintenir pour confirmer » :
 *    - ClipRollMoments.holdConfirm(message, opts) -> Promise<boolean>
 *      remplace window.confirm() pour les suppressions ;
 *    - ClipRollMoments.holdify(button, onConfirm, opts) transforme un bouton
 *      existant en bouton à maintenir (utilisé pour « Publier maintenant »).
 *
 * Inspiré des contrôles « Step Track » et « Hold to Confirm » de UI Moments
 * (https://github.com/guanmo-ai/ui-moments), MIT © 2026 guanmo-ai.
 * Voir THIRD_PARTY_NOTICES.md.
 */
(function () {
  'use strict';

  const HOLD_MS = 900;

  function reduceMotion() {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  /* ------------------------------------------------------------------ */
  /* 1. Suivi de fabrication par étapes                                  */
  /* ------------------------------------------------------------------ */

  // Bornes de progression envoyées par core/pipeline.py (messages « [n/4] »).
  const MAKE_STEPS = [
    { label: 'Script', from: 0, to: 41 },
    { label: 'Voix & son', from: 41, to: 55 },
    { label: 'Décor & montage', from: 55, to: 95 },
    { label: 'Contrôle', from: 95, to: 100 },
  ];
  // Copie d'un short concurrent (messages « [n/5] »).
  const CLONE_STEPS = [
    { label: 'Téléchargement', from: 0, to: 28 },
    { label: 'Transcription', from: 28, to: 45 },
    { label: 'Recette virale', from: 45, to: 60 },
    { label: 'Script', from: 60, to: 75 },
    { label: 'Voix & montage', from: 75, to: 100 },
  ];

  function clamp01(x) { return Math.max(0, Math.min(1, x)); }

  /** Calcule l'état de chaque étape. Exporté pour les tests. */
  function computeSteps(job) {
    const p = Math.max(0, Math.min(100, Number((job && job.progress) || 0)));
    const stepTxt = String((job && job.step) || '');
    const m = stepTxt.match(/\[(\d)\s*\/\s*(\d)\]/);
    const total = m ? Number(m[2]) : 0;
    const steps = (total === 5 || (job && job.kind === 'clone')) ? CLONE_STEPS : MAKE_STEPS;

    let idx;
    if (m && Number(m[1]) >= 1 && Number(m[1]) <= steps.length && total === steps.length) {
      idx = Number(m[1]) - 1;
    } else {
      idx = steps.findIndex(s => p < s.to);
      if (idx < 0) idx = steps.length - 1;
    }
    const done = p >= 100;
    return steps.map((s, i) => {
      let state, fill;
      if (done || i < idx) { state = 'done'; fill = 1; }
      else if (i === idx) { state = 'active'; fill = clamp01((p - s.from) / Math.max(1, s.to - s.from)); }
      else { state = 'todo'; fill = 0; }
      return { label: s.label, state, fill };
    });
  }

  const CHECK_SVG = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>';

  function stepsHtml(job) {
    const steps = computeSteps(job);
    const items = steps.map((s, i) => {
      const pct = Math.round(s.fill * 100);
      const stateTxt = s.state === 'done' ? 'terminée' : (s.state === 'active' ? `en cours, ${pct} %` : 'à venir');
      return `<li class="cr-step is-${s.state}"${s.state === 'active' ? ' aria-current="step"' : ''}>
          <span class="cr-step-bar"><span class="cr-step-fill" style="width:${pct}%"></span></span>
          <span class="cr-step-label">${s.state === 'done' ? CHECK_SVG : `<span class="cr-step-num">${i + 1}</span>`}${esc(s.label)}<span class="sr-only"> : ${stateTxt}</span></span>
        </li>`;
    }).join('');
    return `<ol class="cr-steps" aria-label="Étapes de fabrication">${items}</ol>`;
  }

  /* ------------------------------------------------------------------ */
  /* 2. Maintenir pour confirmer                                         */
  /* ------------------------------------------------------------------ */

  /**
   * Branche le geste « maintenir » sur un bouton qui contient un .cr-hold-fill.
   * opts : { duration, onDone, onShort }
   * Retourne une fonction qui débranche le geste.
   */
  function attachHold(btn, opts) {
    const fill = btn.querySelector('.cr-hold-fill');
    const duration = opts.duration || HOLD_MS;
    let anim = null, started = 0, finished = false;

    function start() {
      if (btn.disabled || finished) return;
      if (anim && anim.playbackRate > 0) return;
      started = performance.now();
      btn.setAttribute('data-holding', '');
      if (anim) {
        anim.updatePlaybackRate(1);
        anim.play();
        return;
      }
      if (fill && fill.animate) {
        anim = fill.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }],
          { duration, easing: 'cubic-bezier(.45,0,.6,1)', fill: 'forwards' });
        anim.onfinish = done;
      } else {
        // Navigateur sans Web Animations : simple minuterie.
        anim = { playbackRate: 1, _t: setTimeout(done, duration), cancel() { clearTimeout(this._t); }, updatePlaybackRate() {}, play() {} };
      }
    }

    function release() {
      if (!anim || finished) return;
      btn.removeAttribute('data-holding');
      if (performance.now() - started < 250 && opts.onShort) opts.onShort();
      if (anim.updatePlaybackRate && anim.effect) {
        anim.updatePlaybackRate(reduceMotion() ? -100 : -3.2);
      } else {
        anim.cancel();
        anim = null;
      }
    }

    function done() {
      if (anim && anim.playbackRate < 0) { anim.cancel(); anim = null; return; }
      finished = true;
      btn.removeAttribute('data-holding');
      btn.setAttribute('data-done', '');
      setTimeout(() => {
        btn.removeAttribute('data-done');
        if (anim) anim.cancel();
        anim = null;
        finished = false;
      }, 700);
      if (opts.onDone) opts.onDone();
    }

    function onDown(e) {
      if (e.button !== 0) return;
      try { btn.setPointerCapture(e.pointerId); } catch (_) { /* rien */ }
      start();
    }
    function onKeyDown(e) {
      if (e.key !== ' ' && e.key !== 'Enter') return;
      e.preventDefault();
      if (!e.repeat) start();
    }
    function onKeyUp(e) {
      if (e.key === ' ' || e.key === 'Enter') release();
    }
    function onClick(e) { e.preventDefault(); e.stopImmediatePropagation(); }
    function onCtx(e) { e.preventDefault(); }

    btn.addEventListener('pointerdown', onDown);
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(t => btn.addEventListener(t, release));
    btn.addEventListener('keydown', onKeyDown);
    btn.addEventListener('keyup', onKeyUp);
    btn.addEventListener('blur', release);
    btn.addEventListener('click', onClick, true);
    btn.addEventListener('contextmenu', onCtx);
    return function detach() {
      btn.removeEventListener('pointerdown', onDown);
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(t => btn.removeEventListener(t, release));
      btn.removeEventListener('keydown', onKeyDown);
      btn.removeEventListener('keyup', onKeyUp);
      btn.removeEventListener('blur', release);
      btn.removeEventListener('click', onClick, true);
      btn.removeEventListener('contextmenu', onCtx);
    };
  }

  /**
   * Fenêtre de confirmation à maintenir. Remplace window.confirm().
   * opts : { action: 'supprimer' (verbe affiché), danger: true }
   */
  function holdConfirm(message, opts) {
    opts = opts || {};
    const action = opts.action || 'supprimer';
    const danger = opts.danger !== false;
    return new Promise(resolve => {
      const prevFocus = document.activeElement;
      const overlay = document.createElement('div');
      overlay.className = 'cr-hold-overlay';
      overlay.innerHTML = `
        <div class="cr-hold-dialog" role="alertdialog" aria-modal="true" aria-labelledby="cr-hold-msg" aria-describedby="cr-hold-hint">
          <p class="cr-hold-msg" id="cr-hold-msg">${esc(message)}</p>
          <div class="cr-hold-actions">
            <button type="button" class="btn btn-ghost btn-sm cr-hold-cancel">Annuler</button>
            <button type="button" class="btn btn-sm cr-hold ${danger ? 'is-danger' : ''}">
              <span class="cr-hold-fill" aria-hidden="true"></span>
              <span class="cr-hold-label">Maintenir pour ${esc(action)}</span>
              <svg class="cr-hold-check" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
            </button>
          </div>
          <p class="cr-hold-hint" id="cr-hold-hint" aria-live="polite">Garde le bouton enfoncé (ou la touche Espace) pour ${esc(action)}.</p>
        </div>`;
      document.body.appendChild(overlay);
      const holdBtn = overlay.querySelector('.cr-hold');
      const cancelBtn = overlay.querySelector('.cr-hold-cancel');
      const hint = overlay.querySelector('.cr-hold-hint');
      let closed = false;

      function close(result) {
        if (closed) return;
        closed = true;
        detach();
        document.removeEventListener('keydown', onEsc, true);
        overlay.classList.add('is-leaving');
        setTimeout(() => overlay.remove(), reduceMotion() ? 0 : 160);
        try { if (prevFocus && prevFocus.focus) prevFocus.focus(); } catch (_) { /* rien */ }
        resolve(result);
      }
      function onEsc(e) {
        if (e.key === 'Escape') { e.preventDefault(); close(false); }
        else if (e.key === 'Tab') {
          // Garde le focus dans la fenêtre.
          const f = [cancelBtn, holdBtn];
          const i = f.indexOf(document.activeElement);
          e.preventDefault();
          f[(i + (e.shiftKey ? f.length - 1 : 1)) % f.length].focus();
        }
      }
      const detach = attachHold(holdBtn, {
        onDone: () => setTimeout(() => close(true), reduceMotion() ? 0 : 260),
        onShort: () => { hint.classList.remove('is-nudge'); void hint.offsetWidth; hint.classList.add('is-nudge'); },
      });
      cancelBtn.addEventListener('click', () => close(false));
      overlay.addEventListener('pointerdown', e => { if (e.target === overlay) close(false); });
      document.addEventListener('keydown', onEsc, true);
      holdBtn.focus();
    });
  }

  /**
   * Transforme un bouton existant en bouton à maintenir.
   * opts : { label: texte affiché, hint: message si simple clic }
   */
  function holdify(btn, onConfirm, opts) {
    if (!btn || btn.dataset.crHold) return;
    opts = opts || {};
    btn.dataset.crHold = '1';
    btn.removeAttribute('onclick');
    btn.classList.add('cr-hold', 'cr-hold-inline');
    const label = opts.label || btn.textContent.trim();
    btn.innerHTML = `<span class="cr-hold-fill" aria-hidden="true"></span>
      <span class="cr-hold-label">${esc(label)}</span>
      <svg class="cr-hold-check" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>`;
    btn.setAttribute('aria-description', opts.hint || 'Maintenir enfoncé pour confirmer');
    attachHold(btn, {
      onDone: onConfirm,
      onShort: () => { if (typeof window.toast === 'function') window.toast(opts.hint || 'Maintiens le bouton enfoncé pour confirmer.'); },
    });
  }

  window.ClipRollMoments = { computeSteps, stepsHtml, holdConfirm, holdify, HOLD_MS };
})();
