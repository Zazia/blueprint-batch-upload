// Deterministic publication assets. Uses locally installed Playwright and Chrome.
// Set NODE_PATH to the existing package directory; no network calls are made.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const root = __dirname;
const charts = JSON.parse(fs.readFileSync(path.join(root,'diagrams.json'),'utf8'));
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const text = (x,y,size,value,weight=400,color='#263446',max=990) => `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${color}" data-max="${max}">${esc(value)}</text>`;
function svg(c) {
  const out = [`<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440"><title>${esc(c.title)}</title><desc>${esc(c.stages.map(s=>s.join('；')).join('。'))}</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#007AFF"/></marker></defs><rect width="1080" height="1440" fill="white"/><g font-family="Microsoft YaHei, PingFang SC, sans-serif">`,
    text(60,63,28,'BLUEPRINT BATCH UPLOAD  /  设计单位上传',600,'#526176'),
    text(60,139,54,c.title,700,'#16283D',1020),
    text(60,197,34,c.subtitle,400,'#526176',1020)];
  c.stages.forEach((s,i)=>{
    const y=235+i*280;
    out.push(`<rect x="56" y="${y}" width="968" height="244" rx="18" fill="#F5F8FC" stroke="#C9D9EB" stroke-width="2"/>`,
      `<path d="M 74 ${y} H 1006 Q 1024 ${y} 1024 ${y+18} V ${y+66} H 56 V ${y+18} Q 56 ${y} 74 ${y}" fill="#EAF3FF"/>`,
      text(85,y+47,42,String(i+1).padStart(2,'0'),700,'#007AFF'),
      text(168,y+47,42,s[0],700,'#16283D'));
    for(let j=1;j<=3;j++) {
      out.push(`<circle cx="82" cy="${y+97+(j-1)*53}" r="4" fill="#007AFF"/>`,text(101,y+111+(j-1)*53,40,s[j],400,'#263446',1000));
    }
    if(i<3) out.push(`<path d="M 540 ${y+247} V ${y+274}" stroke="#007AFF" stroke-width="3" fill="none" marker-end="url(#arrow)"/>`);
  });
  out.push(text(60,1384,32,c.footer,600,'#526176',1020),text(60,1420,24,'流程说明图 · 具体上传结果以当次系统回读为准',400,'#657184',1020),'</g></svg>');
  return out.join('\n');
}
function mermaid(c) {
  const lines=['flowchart TD'];
  c.stages.forEach((s,i)=>{
    lines.push(`  subgraph S${i}["${i+1}. ${s[0]}"]`,'    direction TB');
    s.slice(1).forEach((v,j)=>lines.push(`    N${i}${j}["${v.replaceAll('"','＂')}"]`));
    // Invisible edges preserve vertical layout without pretending alternative rules run sequentially.
    lines.push(`    N${i}0 ~~~ N${i}1 ~~~ N${i}2`,'  end');
    if(i) lines.push(`  S${i-1} --> S${i}`);
  });
  return lines.join('\n')+'\n';
}
const font = "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif";
const pstyle = `font-family:${font};font-size:16px;font-weight:400;line-height:1.8;color:#1D1D1F;margin:0 0 20px;text-align:left;`;
function inline(s) {
  return esc(s).replace(/\*\*(.*?)\*\*/g,'<strong style="color:#007AFF;font-weight:700;">$1</strong>')
    .replace(/`([^`]+)`/g,'<span style="font-family:monospace;font-size:16px;color:#263446;">$1</span>');
}
function body() {
  const md = fs.readFileSync(path.join(root,'../usage-walkthrough.md'),'utf8').split('\n---\n')[0];
  const parts = [];
  for(const block of md.split(/\n\s*\n/)) {
    const b=block.trim();
    if(!b || /^# /.test(b)) continue;
    const img=b.match(/^!\[([^\]]*)\]\(upload-guide\/([^)]*)\)$/);
    if(img) {parts.push(`<p style="margin:24px 0 8px;"><img src="${img[2]}" alt="${esc(img[1])}" style="width:100%;height:auto;display:block;" /></p><p style="font-family:${font};font-size:14px;line-height:1.6;color:#6E6E78;margin:0 0 28px;text-align:center;">${esc(img[1])} · 先看阶段，再看框内动作</p>`);continue;}
    if(b.startsWith('## ')) {
      const m=b.slice(3).match(/^(\d{2}) (.*)$/);
      if(m) parts.push(`<p style="font-family:${font};font-size:56px;font-weight:700;line-height:1.1;color:#1D1D1F;text-align:center;margin:48px 0 16px;">${m[1]}</p>`);
      parts.push(`<p style="font-family:${font};font-size:20px;font-weight:600;line-height:1.5;color:#1D1D1F;text-align:center;margin:${m?'0':'40px'} 0 28px;">${esc(m?m[2]:b.slice(3))}</p>`);continue;
    }
    if(b.startsWith('>')) {
      for(const q of b.split('\n').map(x=>x.replace(/^> ?/,''))) if(q) parts.push(`<p style="${pstyle}padding:12px 16px;border-left:3px solid #007AFF;background:#F5F5F7;">${inline(q)}</p>`);
      continue;
    }
    const emphasis=/^\*\*[^]*\*\*$/.test(b);
    parts.push(`<p style="${pstyle}${emphasis?'text-align:center;font-size:18px;font-weight:700;':''}">${inline(b.replaceAll('\n',''))}</p>`);
  }
  const content=parts.join('\n')+'\n';
  fs.writeFileSync(path.join(root,'body.html'),content);
  // Portable fallback after the skill's injection command failed on this host.
  const preview=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>图都画完了，怎么还在跟“上传”较劲？</title></head><body style="margin:0;background:#F5F5F7;font-family:${font};"><header style="max-width:640px;margin:24px auto;padding:20px;background:white;"><p style="font-size:14px;color:#526176;line-height:1.6;">公众号预览稿 · 正文图片请上传至公众号素材库后替换。本地预览不代表微信粘贴验证。</p><button id="copy" style="font-size:16px;padding:10px 20px;cursor:pointer;">复制正文</button><span id="status" style="font-size:14px;margin-left:12px;"></span></header><main style="max-width:640px;margin:auto;padding:24px;background:white;"><h1 style="font-size:28px;line-height:1.5;color:#16283D;">图都画完了，怎么还在跟“上传”较劲？</h1><article id="article">${content}</article></main><script>document.getElementById('copy').onclick=()=>{const r=document.createRange();r.selectNodeContents(document.getElementById('article'));const s=window.getSelection();s.removeAllRanges();s.addRange(r);let ok=false;try{ok=document.execCommand('copy');}catch(e){}document.getElementById('status').textContent=ok?'已复制，请替换上传正文图片':'正文已选中，请按 Ctrl+C';if(ok)s.removeAllRanges();};</script></body></html>`;
  fs.writeFileSync(path.join(root,'index.html'),preview);
}
(async()=>{
  fs.mkdirSync(path.join(root,'assets'),{recursive:true});
  fs.mkdirSync(path.join(root,'sources'),{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const results=[];
  try {
    const page=await browser.newPage({viewport:{width:1080,height:1440},deviceScaleFactor:1});
    for(const c of charts) {
      if(c.stages.length!==4 || c.stages.some(s=>s.length!==4)) throw Error(c.id+': expected four stages with three details');
      const source=svg(c);
      fs.writeFileSync(path.join(root,'sources',c.id+'.svg'),source);
      fs.writeFileSync(path.join(root,'sources',c.id+'.mmd'),mermaid(c));
      await page.setContent(`<html><head><meta charset="utf-8"></head><body style="margin:0">${source}</body></html>`);
      await page.evaluate(()=>document.fonts.ready);
      const overflow=await page.evaluate(()=>[...document.querySelectorAll('text')].filter(t=>{const b=t.getBBox();return b.x+b.width>Number(t.dataset.max)||b.y<0||b.y+b.height>1440;}).map(t=>({text:t.textContent,box:t.getBBox().width,max:t.dataset.max})));
      if(overflow.length) throw Error(c.id+': '+JSON.stringify(overflow));
      await page.screenshot({path:path.join(root,'assets',c.id+'.png')});
      results.push({id:c.id,width:1080,height:1440,stages:4,bodyFont:40,titleFont:54,stageFont:42,overflow:0});
    }
  } finally {await browser.close();}
  body();
  fs.writeFileSync(path.join(root,'validation.json'),JSON.stringify({checks:results,articleImages:9,notes:'PNG rendered locally; diagram text bounding boxes checked. No WeChat paste verification.'},null,2)+'\n');
  console.log(`Rendered ${results.length} diagrams; consistent dimensions/fonts; no text overflow. Body HTML generated.`);
})().catch(e=>{console.error(e);process.exit(1);});
