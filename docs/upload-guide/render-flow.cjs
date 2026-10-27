// Explicit row layout keeps real flowchart branches narrow and font sizes stable.
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const layouts={
 '00-overview':[[['a'],['b','x']],[['c'],['d']],[['e'],['f']],[['g'],['h'],['i','j']]],
 '01-initial':[[['a'],['b']],[['c','d'],['u']],[['e'],['f']],[['g'],['h']]],
 '02-change':[[['a'],['b']],[['c','d']],[['e'],['f']],[['g'],['h']]],
 '03-handover':[[['a'],['b','c']],[['d']],[['e'],['f']],[['g'],['h']]],
 '04-add-cancel':[[['a']],[['b','c','d']],[['e','f','g']],[['h'],['i'],['j','k']]],
 '05-completion':[[['a'],['b']],[['c'],['d']],[['e'],['f']],[['g','h']]],
 '06-resume':[[['a'],['b']],[['c','d','e']],[['f']],[['g'],['h']]],
 '07-limited':[[['a'],['b']],[['c','d']],[['e']],[['f'],['g']]],
 '08-report-submit':[[['a']],[['b','c']],[['d'],['e']],[['f'],['g']]],
 '09-interfaces':[[['a','b']],[['c'],['d']],[['e']],[['f']]]
};
const W=420,FONT=14;
function wrap(s,width){
 const lines=[];
 for(const line of s.split('\n')){
  let row='',count=0;
  for(const ch of line){const u=/[^\x00-\x7F]/.test(ch)?FONT:FONT*.57;if(count+u>width&&row){lines.push(row);row='';count=0;}row+=ch;count+=u;}
  lines.push(row);
 }return lines;
}
function mermaid(c){
 const lines=['flowchart TD'];
 c.stages.forEach((s,i)=>{lines.push(`  subgraph S${i}["${s.title}"]`,'    direction TB');s.nodes.forEach(n=>{const v=n.label.replaceAll('\n','<br/>');lines.push(`    ${n.id}${n.shape==='diamond'?`{"${v}"}`:n.shape==='end'?`(["${v}"])`:`["${v}"]`}`);});lines.push('  end');});
 c.edges.forEach(e=>lines.push(`  ${e.from} ${c.id==='09-interfaces'&&e.from==='d'?'-.->':'-->'}${e.label?'|'+e.label+'|':''} ${e.to}`));return lines.join('\n')+'\n';
}
function dot(c){return 'digraph G {\nrankdir=TB;\n'+c.stages.map((s,i)=>`subgraph cluster_${i} { label=${JSON.stringify(s.title)};\n${s.nodes.map(n=>`${n.id} [label=${JSON.stringify(n.label)},shape=${n.shape==='diamond'?'diamond':n.shape==='end'?'oval':'box'}];`).join('\n')}\n}`).join('\n')+'\n'+c.edges.map(e=>`${e.from} -> ${e.to} [label=${JSON.stringify(e.label)}];`).join('\n')+'\n}\n';}
function draw(c){
 const nodes={},groups=[];let y=48,order=0;
 c.stages.forEach((s,i)=>{
  const top=y;y+=43;
  const def=Object.fromEntries(s.nodes.map(n=>[n.id,n]));
  layouts[c.id][i].forEach(row=>{
   let rh=0;
   row.forEach((id,j)=>{
    const n=def[id];if(!n)throw Error(c.id+': missing node '+id);
    const w=row.length===3?112:row.length===2?166:232;
    const x=row.length===3?78+j*132:row.length===2?112+j*196:210;
    const lines=wrap(n.label,w-(n.shape==='diamond'?54:20));
    const h=n.shape==='diamond'?Math.max(66,lines.length*20+34):Math.max(42,lines.length*20+18);
    nodes[id]={...n,x,y:y+h/2,w,h,lines,stage:i,order:order++};rh=Math.max(rh,h);
   });
   y+=rh+36;
  });
  y-=18;groups.push({top,h:y-top,title:s.title});y+=30;
 });
 const H=y+2;
 const out=[`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><title>${esc(c.title)}</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#647C8F"/></marker></defs><rect width="100%" height="100%" fill="white"/><g font-family="Microsoft YaHei, sans-serif"><text x="210" y="26" text-anchor="middle" font-size="16" font-weight="600" fill="#263D50">${esc(c.title)}</text>`];
 groups.forEach(g=>out.push(`<rect x="10" y="${g.top}" width="400" height="${g.h}" rx="8" fill="#F8FAFC" stroke="#C6D3DD"/><text x="24" y="${g.top+25}" font-size="14" font-weight="600" fill="#23577D">${esc(g.title)}</text>`));
 const labels=[];
 c.edges.forEach((e,index)=>{
  const a=nodes[e.from],b=nodes[e.to];let d,lx,ly;
  const sameRow=Math.abs((a.y-a.h/2)-(b.y-b.h/2))<2;
  if(sameRow){
   const dir=b.x>a.x?1:-1,sx=a.x+dir*a.w/2,tx=b.x-dir*b.w/2;
   d=`M${sx} ${a.y} L${(sx+tx)/2} ${a.y} L${(sx+tx)/2} ${b.y} L${tx} ${b.y}`;lx=(sx+tx)/2;ly=Math.min(a.y,b.y)-7;
  }else if(b.y<a.y){
   const lane=404,sx=a.x+a.w/2,tx=b.x+b.w/2;
   d=`M${sx} ${a.y} H${lane} V${b.y} H${tx}`;lx=lane-9;ly=(a.y+b.y)/2;
  }else{
   const sy=a.y+a.h/2,ty=b.y-b.h/2;
   const obstruct=b.stage>a.stage+1||Object.values(nodes).some(n=>n!==a&&n!==b&&n.y>sy&&n.y<ty&&Math.abs(n.x-a.x)<n.w/2+8);
   if(obstruct){const lane=a.x<210?4:416;d=`M${a.x} ${sy} V${sy+13} H${lane} V${ty-12} H${b.x} V${ty}`;lx=a.x+(lane-a.x)/2;ly=sy+9;}
   else{const mid=sy+(ty-sy)*.48;d=`M${a.x} ${sy} V${mid} H${b.x} V${ty}`;lx=a.x===b.x?a.x+15:(a.x+b.x)/2;ly=mid-5;}
   // Enter left-hand nodes below the group heading instead of crossing its text.
   const targetGroup=groups[b.stage],labelEnd=24+targetGroup.title.length*14;
   if(b.stage>a.stage&&b.x<labelEnd&&b.x>24){
    const lane=16;d=`M${a.x} ${sy} V${sy+12} H${lane} V${targetGroup.top+35} H${b.x} V${ty}`;
    lx=(a.x+lane)/2;ly=sy+8;
   }
  }
  out.push(`<path data-edge="${e.from}-${e.to}" d="${d}" fill="none" stroke="#647C8F" stroke-width="1.1" marker-end="url(#arrow)"${c.id==='09-interfaces'&&e.from==='d'?' stroke-dasharray="4 3"':''}/>`);
  if(e.label){const half=e.label.length*6;lx=Math.max(half+8,Math.min(W-half-8,lx));labels.push(`<text x="${lx}" y="${ly}" text-anchor="middle" font-size="12" fill="#465D72" stroke="white" stroke-width="3" paint-order="stroke">${esc(e.label)}</text>`);}
 });
 Object.values(nodes).forEach(n=>{
  const x=n.x-n.w/2,y=n.y-n.h/2;
  out.push(`<g class="node" data-id="${n.id}">`);
  if(n.shape==='diamond')out.push(`<polygon points="${n.x},${y} ${x+n.w},${n.y} ${n.x},${y+n.h} ${x},${n.y}" fill="#EEF5FC" stroke="#96A9BB"/>`);
  else out.push(`<rect x="${x}" y="${y}" width="${n.w}" height="${n.h}" rx="${n.shape==='end'?n.h/2:6}" fill="white" stroke="#96A9BB"/>`);
  n.lines.forEach((line,j)=>out.push(`<text x="${n.x}" y="${n.y-(n.lines.length-1)*10+j*20+5}" text-anchor="middle" font-size="${FONT}" fill="#263446">${esc(line)}</text>`));out.push('</g>');
 });
 out.push(...labels,'</g></svg>');
 return {id:c.id,title:c.title,svg:out.join('\n'),dot:dot(c),mmd:mermaid(c),displayWidth:W,displayHeight:H,font:FONT,stages:c.stages.length};
}
async function render(charts){return charts.map(draw);}
module.exports={render};
