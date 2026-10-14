const test = require('node:test');
const assert = require('node:assert/strict');
const {createRunner, jgtglAdapter} = require('../scripts/browser/upload.js');
const {normalize} = require('../scripts/browser/collect.js');
const context = {site:'http://example.test', WID:'w1', OrgId:'o1', unit:'1号楼', profession:'建筑', workstatus:'竣工'};
const options = {context, runId:'synthetic', timeoutMs:40};
const tasks = [{itemId:'one'}, {itemId:'two'}];
const adapter = overrides => ({context:async()=>context, persist:async()=>{}, upload:async()=>({state:'verified'}), ...overrides});

test('readback groups versions by BPID, never assumes complete coverage', () => {
  const snapshot = normalize(context, {data:[[{BPID:1, BGID:'selected'}, {BPID:2}], [{BPID:1, VSID:'v1', status:'竣工'}]]});
  assert.equal(snapshot.complete, false);
  assert.equal(snapshot.rows[0].versions[0].VSID, 'v1');
  assert.equal(snapshot.rows[1].versions.length, 0);
  assert.throws(()=>normalize(context, {data:[[]]}));
});
test('runner persists before starting and after success', async () => {
  const events = [];
  const runner = createRunner(adapter({persist:async e=>events.push(e.state), upload:async()=>{
    assert.equal(events.at(-1), 'starting'); return {state:'verified'};
  }}));
  const result = await runner.run(tasks, options);
  assert.deepEqual(events, ['starting','verified','starting','verified']);
  assert.equal(result.results.length, 2);
  assert.equal(result.running, false);
});
test('context drift blocks remaining queue', async () => {
  let count = 0;
  const runner = createRunner(adapter({context:async()=>++count===1 ? context : {...context, unit:'2号楼'}}));
  const result = await runner.run(tasks, options);
  assert.deepEqual(result.results.map(r=>r.state), ['verified','blocked']);
});
test('timeout is unknown and no next dispatch', async () => {
  let count = 0;
  const runner = createRunner(adapter({upload:()=>{count++; return new Promise(()=>{});}}));
  const result = await runner.run(tasks, {...options, timeoutMs:5});
  assert.equal(count, 1);
  assert.deepEqual(result.results.map(r=>r.state), ['unknown','planned']);
});
test('explicit failure may continue; unknown stops', async () => {
  for (const state of ['failed','unknown']) {
    let count = 0;
    const runner = createRunner(adapter({upload:async()=>{count++; throw Object.assign(new Error('test'), {state});}}));
    const result = await runner.run(tasks, options);
    assert.equal(count, state === 'failed' ? 2 : 1);
    assert.equal(result.results.length, 2);
  }
});
test('failed evidence persistence prevents uploads', async () => {
  let count = 0;
  const runner = createRunner(adapter({persist:async()=>{throw new Error('disk full');}, upload:async()=>{count++;}}));
  const result = await runner.run(tasks, options);
  assert.equal(count, 0);
  assert.equal(result.results[0].persistenceFailed, true);
});
test('batch lock, stop and missing context', async () => {
  let release;
  const runner = createRunner(adapter({upload:()=>new Promise(resolve=>{release=resolve;})}));
  await assert.rejects(runner.run(tasks, {...options, context:{}}));
  const running = runner.run(tasks, {...options, timeoutMs:1000});
  await new Promise(resolve=>setImmediate(resolve));
  await assert.rejects(runner.run(tasks, options), /already running/);
  runner.stop();
  release({state:'verified'});
  const result = await running;
  assert.deepEqual(result.results.map(r=>r.state), ['verified','planned']);
});

// A small DOM/transport substitute exercises the real PACK adapter chain, not a copy of it.
async function packCase({unpack=true, status='竣工', hash='hash', name='A.1_平面图.pack'}={}) {
  const originals = {};
  const calls = [], attrs = {}, events = [];
  const row = {BPID:'b1', WID:'w1', code:'A.1'};
  const element = {};
  const wrapper = {
    data:()=>row, find:()=>wrapper, closest:()=>wrapper, not:()=>wrapper, remove:()=>wrapper,
    append:()=>wrapper, text:()=>wrapper,
    attr:(value,second)=>{if (typeof value === 'string') attrs[value]=second; else Object.assign(attrs,value); return wrapper;}, 0:element
  };
  const $ = ()=>wrapper;
  $.post = (url, params, callback) => {
    calls.push({url,params});
    queueMicrotask(()=>callback(url.includes('blueprintVersion_add_jgt') ? {errcode:0,data:[{VSID:'v2',version:2}]} : {success:unpack}));
    return {fail:()=>{}};
  };
  const globals = {
    jQuery:$, uploadPDF:()=>{}, document:{querySelectorAll:()=>[element]}, wstatus:'竣工', taskReady:1,
    Config:{GetValue:()=>'/unpack'}, crypto:undefined,
    fetch:async()=>({ok:true, headers:{get:()=>hash}, blob:async()=>new Blob(['abc'])}),
    cos:{bucket:'b', region:'r', uploadFile:(success,_fail,_progress,_bucket,_region,file)=>{
      calls.push({url:'storage',name:file.name}); success({target:{response:JSON.stringify({url:'/folder/a.pack'})}});
    }}
  };
  for (const [key,value] of Object.entries(globals)) {
    originals[key] = Object.getOwnPropertyDescriptor(globalThis,key);
    Object.defineProperty(globalThis,key,{value,configurable:true,writable:true});
  }
  try {
    const a = jgtglAdapter({getContext:async()=>context,persist:async()=>{},readBack:async()=>({context, rows:[{...row, versions:[{VSID:'v2',status}]}]})});
    const task = {itemId:'one',BPID:'b1',action:'update',uploadCode:'A.1', uploadName:name,size:3,sha256:'hash',url:'http://127.0.0.1/file',expectedStatus:'竣工'};
    try {
      const result = await a.upload(task,async e=>events.push(e),new AbortController().signal,context);
      return {result,calls,attrs,events};
    } catch(error) { return {error,calls,attrs,events}; }
  } finally {
    for (const [key,descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis,key,descriptor); else delete globalThis[key];
    }
  }
}
test('PACK adapter awaits save, unpack and actual version readback', async () => {
  const {result,error,calls,attrs} = await packCase();
  assert.ifError(error);
  assert.equal(result.state,'verified');
  assert.equal(attrs.status,'已上传');
  assert.equal(calls[0].name,'A.1_平面图.pack');
  assert.equal(calls[1].params.BPID,'b1');
  assert.equal(calls[2].params.packPath,'folder/a.pack');
});
test('unpack failure never appears as uploaded', async () => {
  const {error,attrs} = await packCase({unpack:false});
  assert.equal(error.state,'failed');
  assert.equal(attrs.status,'上传失败');
});
test('wrong readback stage is unknown', async () => {
  const {error,attrs} = await packCase({status:'变更'});
  assert.equal(error.state,'unknown');
  assert.equal(attrs.status,'待核查');
});
test('changed file and PDF refused before storage', async () => {
  for (const settings of [{hash:'different'}, {name:'取消单.pdf'}]) {
    const {error,calls} = await packCase(settings);
    assert.ok(error);
    assert.equal(calls.length,0);
  }
});
