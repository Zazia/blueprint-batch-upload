/* PACK-only precise-target adapter, preserving the original JGTGL COS/version/unpack chain.
 * PDF/cancellation materials use native page validation. No completion/DELETE/BGID writes.
 */
(function (root) {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const same = (a, b) => ['site','WID','OrgId','unit','profession','workstatus'].every(k => String(a[k]) === String(b[k]));
  const failure = (message, state = 'failed') => Object.assign(new Error(message), {state});

  function createRunner(adapter) {
    let active = false, stopRequested = false;
    let status = {running: false, results: []};
    const run = async (tasks, options) => {
      if (active) throw new Error('A batch is already running');
      if (!Array.isArray(tasks) || new Set(tasks.map(t => t.itemId)).size !== tasks.length) throw new Error('Invalid/duplicate items');
      if (!options?.runId || !['site','WID','OrgId','unit','profession','workstatus'].every(k =>
        options.context?.[k] != null && String(options.context[k]).trim())) throw new Error('Complete context and runId required');
      active = true; stopRequested = false;
      status = {running: true, total: tasks.length, current: 0, results: []};
      try {
        for (const task of tasks) {
          if (stopRequested) break;
          if (!same(await adapter.context(), options.context)) {
            status.results.push({itemId: task.itemId, state: 'blocked', reason: 'Page context changed'});
            break;
          }
          let began = false, timer;
          const controller = new AbortController();
          const emit = async event => adapter.persist({runId: options.runId, itemId: task.itemId,
            at: new Date().toISOString(), ...event});
          status.current++;
          try {
            await emit({state: 'starting', BPID: task.BPID, fileSha256: task.sha256});
            began = true;
            const result = await Promise.race([
              adapter.upload(task, emit, controller.signal, options.context),
              new Promise((_, reject) => { timer = setTimeout(() => {
                controller.abort(); reject(failure('Timeout: reconcile server state before retry', 'unknown'));
              }, options.timeoutMs || 180000); })
            ]);
            const record = {itemId: task.itemId, ...result};
            const saved = await emit(record);
            if (saved?.file) record.evidenceRef = saved.file;
            status.results.push(record);
          } catch (e) {
            const record = {itemId: task.itemId, state: e.state || (began ? 'unknown' : 'blocked'), reason: e.message};
            status.results.push(record);
            try { await emit(record); } catch (_persistError) { record.persistenceFailed = true; }
            if (record.state !== 'failed' || record.persistenceFailed) break;
          } finally { clearTimeout(timer); }
        }
      } finally {
        for (const t of tasks) if (!status.results.some(r => r.itemId === t.itemId)) {
          status.results.push({itemId: t.itemId, state: 'planned', reason: 'Not dispatched'});
        }
        status.running = false; active = false;
      }
      return copy(status);
    };
    return {run, stop: () => {stopRequested = true;}, status: () => copy(status)};
  }

  function jgtglAdapter({getContext, persist, readBack}) {
    if (![getContext, persist, readBack].every(f => typeof f === 'function')) throw new Error('context/persist/readBack functions required');
    return {
      context: getContext, persist,
      async upload(task, emit, signal, expected) {
        const guard = async () => {
          if (signal.aborted) throw failure('Aborted after timeout; reconcile', 'unknown');
          if (!same(await getContext(), expected)) throw failure('Context changed; reconcile', 'unknown');
        };
        const $ = root.jQuery, uploader = root.uploadPDF, cos = root.cos;
        if (!$ || !uploader || !cos || !root.Config || typeof root.taskReady === 'undefined') throw failure('Page upload dependencies unavailable');
        if (!task.BPID || !/\.pack$/i.test(task.uploadName) || task.action === 'add' || task.action === 'cancel') {
          throw failure('Only existing-record PACK updates supported here; use native add/PDF/cancellation input');
        }
        await guard();
        const matches = [...root.document.querySelectorAll('tr.editTR')].filter(tr => String($(tr).data('data')?.BPID) === String(task.BPID));
        if (matches.length !== 1) throw failure('BPID missing or ambiguous');
        const tr = $(matches[0]), data = tr.data('data');
        if (String(data.WID) !== String(expected.WID) || String(data.code).trim() !== String(task.uploadCode).trim()) throw failure('Target code/project mismatch');
        if (String(root.wstatus) !== String(expected.workstatus)) throw failure('Stage mismatch');
        const response = await root.fetch(task.url, {signal});
        if (!response.ok) throw failure('Local file unavailable');
        const blob = await response.blob();
        if (blob.size !== task.size) throw failure('Local file size changed');
        // Hash the whole opaque file; never inspect its members.
        // JGTGL deployments can use HTTP, where WebCrypto is unavailable.
        let hash = response.headers.get('X-Content-SHA256');
        if (root.crypto?.subtle) {
          hash = [...new Uint8Array(await root.crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(b => b.toString(16).padStart(2, '0')).join('');
        }
        if (hash !== task.sha256) throw failure('Local file hash changed');
        const file = new root.File([blob], task.uploadName, {type:'application/octet-stream'});
        const td = tr.find('td.versions:first'), old = td.find('a[vsid]:last')[0];
        const link = $('<a status="待上传"><i>待上传</i></a>'); td.append(link);
        const post = (url, params) => new Promise((resolve, reject) => {
          $.post(url, params, resolve).fail(() => reject(failure('Network response lost: '+url, 'unknown')));
        });
        try {
          await guard();
          await emit({state:'uploading'});
          await guard();
          const stored = await new Promise((resolve, reject) => {
            cos.uploadFile(result => {
              try {
                const obj = JSON.parse(result.target.response);
                const url = obj.url || obj.data;
                if ((obj.errcode != null && Number(obj.errcode) !== 0) || obj.success === false || typeof url !== 'string') throw failure('File storage rejected');
                resolve(url);
              } catch (e) { reject(e); }
            }, () => reject(failure('Storage callback failed; reconcile', 'unknown')), () => {},
            cos.bucket, cos.region, file, 0, root.taskReady, {convert2svg:'1'});
          });
          await guard();
          await emit({state:'stored', url:stored});
          await guard();
          const res = await post('/api/procHandler?procname=blueprintVersion_add_jgt', {
            BPID:data.BPID, url:stored, fileSize:file.size, workstatus:root.wstatus});
          if (res.errcode !== 0 || !res.data?.[0]?.VSID) throw failure(res.errmsg || 'Version save rejected');
          const v = res.data[0];
          // Preserve the original DOM/jQuery fix. Never call .find on a native link.
          $(old).closest('td').find('a[version="'+v.version+'"]').not(link).remove();
          link.attr({vsid:v.VSID, version:v.version, status:'处理中'}).find('i').text('处理中');
          await emit({state:'version_saved', BPID:String(data.BPID), VSID:String(v.VSID), url:stored});
          await guard();
          const unpackPath = stored.substring(1, stored.lastIndexOf('/')+1) + data.WID + stored.substring(stored.lastIndexOf('/'), stored.length-5);
          const unpack = await post(root.Config.GetValue('中望解压程序地址'), {packPath:stored.substring(1), unpackPath});
          if (unpack.success !== true) throw failure(unpack.message || 'PACK unpack failed');
          await guard();
          const snapshot = await readBack();
          await guard();
          if (!['site','WID','OrgId','unit','profession'].every(k => String(snapshot.context?.[k]) === String(expected[k]))) throw failure('Readback context mismatch', 'unknown');
          const row = snapshot.rows.find(r => String(r.BPID) === String(data.BPID));
          const actual = row?.versions?.find(x => String(x.VSID) === String(v.VSID));
          if (!actual || actual.status !== task.expectedStatus) throw failure('Version/stage readback not confirmed', 'unknown');
          link.attr('status','已上传').find('i').text('已上传');
          return {state:'verified', executionSource:'uploaded', BPID:String(data.BPID), VSID:String(v.VSID), processing:'success',
            fileSha256:hash, evidenceRef:task.itemId, snapshot};
        } catch (e) {
          link.attr({status:e.state === 'failed' ? '上传失败' : '待核查', title:e.message}).find('i').text(e.state === 'failed' ? '上传失败' : '待核查');
          throw e;
        }
      }
    };
  }
  const api = {createRunner, jgtglAdapter};
  root.BlueprintUpload = api;
  if (typeof module !== 'undefined') module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
