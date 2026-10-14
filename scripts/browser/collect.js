/* Read-only helpers; use only with a browser tool that permits page JavaScript. */
(function (root) {
  'use strict';
  function normalize(context, payload, complete = false) {
    if (typeof payload === 'string') payload = JSON.parse(payload);
    if (!payload || !Array.isArray(payload.data) || !Array.isArray(payload.data[0]) || !Array.isArray(payload.data[1])) {
      throw new Error('Expected observed read_blueprint_and_version data[0]/data[1] arrays');
    }
    const grouped = new Map();
    for (const v of payload.data[1]) {
      const key = String(v.BPID);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(v);
    }
    return {context: {...context}, capturedAt: new Date().toISOString(), complete,
      rows: payload.data[0].map(r => ({...r, BPID: String(r.BPID), versions: grouped.get(String(r.BPID)) || []}))};
  }
  function visible(context) {
    if (!root.jQuery) throw new Error('jQuery unavailable');
    const rows = [...root.document.querySelectorAll('tr.editTR')].map(tr => {
      const r = root.jQuery(tr).data('data');
      if (!r || r.BPID == null) throw new Error('Row missing BPID');
      return {...r, BPID: String(r.BPID), ...(Array.isArray(r.xml) ? {versions:r.xml} : {})};
    });
    // Visible rows cannot prove pagination completeness or presence of hidden fields.
    return {context: {...context}, rows, complete: false, capturedAt: new Date().toISOString()};
  }
  function captureOnce(context, requestMatches) {
    if (!root.jQuery || typeof requestMatches !== 'function') throw new Error('Provide a matcher for observed request parameters');
    const $ = root.jQuery;
    const fixed = {...context};
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { $(root.document).off('ajaxComplete', handler); reject(new Error('Capture timeout')); }, 30000);
      function handler(_e, response, settings) {
        if (!/read_blueprint_and_version/.test(settings.url) || !requestMatches(settings)) return;
        clearTimeout(timer);
        $(root.document).off('ajaxComplete', handler);
        try { resolve(normalize(fixed, response.responseText)); } catch (e) { reject(e); }
      }
      $(root.document).on('ajaxComplete', handler);
    });
  }
  const api = {normalize, visible, captureOnce};
  root.BlueprintCollect = api;
  if (typeof module !== 'undefined') module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
