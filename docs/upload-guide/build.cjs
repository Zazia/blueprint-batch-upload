// Rebuild publication diagrams and article from local sources; no network calls.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const {render} = require('./render-flow.cjs');
const root = __dirname;
const charts = require('./diagrams.cjs');
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function save(file,data){
  const bytes=Buffer.isBuffer(data)?data:Buffer.from(data);
  if(fs.existsSync(file)&&fs.readFileSync(file).equals(bytes))return;
  fs.writeFileSync(file,bytes);
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
    if(img) {parts.push(`<p style="margin:24px 0 8px;"><img src="${img[2]}" alt="${esc(img[1])}" style="width:100%;max-width:420px;height:auto;display:block;margin:0 auto;" /></p><p style="font-family:${font};font-size:14px;line-height:1.6;color:#6E6E78;margin:0 0 28px;text-align:center;">${esc(img[1])}</p>`);continue;}
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
  const preview=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>广州审图系统太难用了，我给上传图纸写了个技能</title></head><body style="margin:0;background:#F5F5F7;font-family:${font};"><header style="max-width:640px;margin:24px auto;padding:20px;background:white;"><p style="font-size:14px;color:#526176;line-height:1.6;">公众号预览稿 · 正文图片请上传至公众号素材库后替换。本地预览不代表微信粘贴验证。</p><button id="copy" style="font-size:16px;padding:10px 20px;cursor:pointer;">复制正文</button><span id="status" style="font-size:14px;margin-left:12px;"></span></header><main style="max-width:640px;margin:auto;padding:24px;background:white;"><h1 style="font-size:28px;line-height:1.5;color:#16283D;">广州审图系统太难用了，我给上传图纸写了个技能</h1><article id="article">${content}</article></main><script>document.getElementById('copy').onclick=()=>{const r=document.createRange();r.selectNodeContents(document.getElementById('article'));const s=window.getSelection();s.removeAllRanges();s.addRange(r);let ok=false;try{ok=document.execCommand('copy');}catch(e){}document.getElementById('status').textContent=ok?'已复制，请替换上传正文图片':'正文已选中，请按 Ctrl+C';if(ok)s.removeAllRanges();};</script></body></html>`;
  fs.writeFileSync(path.join(root,'index.html'),preview);
}
(async()=>{
  fs.mkdirSync(path.join(root,'assets'),{recursive:true});
  fs.mkdirSync(path.join(root,'sources'),{recursive:true});
  const rendered=await render(charts);
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const results=[];
  try {
    const page=await browser.newPage({deviceScaleFactor:2});
    for(const c of rendered) {
      save(path.join(root,'sources',c.id+'.svg'),c.svg);
      save(path.join(root,'sources',c.id+'.mmd'),c.mmd);
      save(path.join(root,'sources',c.id+'.dot'),c.dot);
      await page.setViewportSize({width:c.displayWidth,height:c.displayHeight});
      await page.setContent(`<html><head><meta charset="utf-8"></head><body style="margin:0">${c.svg}</body></html>`);
      await page.evaluate(()=>document.fonts.ready);
      const issues=await page.evaluate(()=>{
        const nodes=[...document.querySelectorAll('g.node')];
        const issues=nodes.flatMap(g=>{
          const shape=g.querySelector('polygon,path,ellipse,rect'); if(!shape)return[];
          const r=shape.getBoundingClientRect();
          return [...g.querySelectorAll('text')].filter(t=>{const b=t.getBoundingClientRect();return b.left<r.left-1||b.right>r.right+1||b.top<r.top-1||b.bottom>r.bottom+1;}).map(t=>t.textContent);
        });
        for(const t of document.querySelectorAll('text')){const b=t.getBoundingClientRect();if(b.left<0||b.right>innerWidth||b.top<0||b.bottom>innerHeight)issues.push('canvas: '+t.textContent);}
        return issues;
      });
      if(issues.length) throw Error(c.id+': node text overflow: '+JSON.stringify(issues));
      save(path.join(root,'assets',c.id+'.png'),await page.screenshot());
      results.push({id:c.id,width:c.displayWidth*2,height:c.displayHeight*2,stages:c.stages,displayWidth:c.displayWidth,bodyFont:Number(c.font.toFixed(2)),overflow:0});
    }
  } finally {await browser.close();}
  body();
  fs.writeFileSync(path.join(root,'validation.json'),JSON.stringify({checks:results,articleImages:9,notes:'Actual graph nodes, decisions, labeled edges and stage clusters. Shared font scale; article font 16px. No WeChat paste verification.'},null,2)+'\n');
  console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exit(1);});
