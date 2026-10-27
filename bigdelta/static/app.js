'use strict';
let state = {projects: [], checks: {}, token: ''};
let currentId = localStorage.getItem('bigdelta-project');
let tab = 'Package builder';
let dialogAction = null;
let comparison = null;
let reviewSession = null;
let reviewTimer = null;
let reviewPage = 0;
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const project = () => state.projects.find(p => p.id === currentId);
const latest = d => d.revisions[d.revisions.length - 1];
const date = s => new Date(s).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});
const pill = (text, style='') => `<span class="pill ${style}">${esc(text)}</span>`;
const button = (action, title, id='', extra='') => `<button type="button" class="tiny" data-action="${action}" data-id="${esc(id)}" ${extra}>${title}</button>`;
const link = (id, title) => `<a href="/download/${esc(id)}" target="_blank" rel="noopener">${esc(title)}</a>`;
const options = (items, selected='') => items.map(([v,t]) => `<option value="${esc(v)}" ${v === selected ? 'selected' : ''}>${esc(t)}</option>`).join('');
function field(label, name, value='', type='text', more='') {
  return `<label for="f-${name}">${esc(label)}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${more}>`;
}
function textarea(label, name, value='', more='') {
  return `<label for="f-${name}">${esc(label)}</label><textarea id="f-${name}" name="${name}" ${more}>${esc(value)}</textarea>`;
}
function select(label, name, items, selected='', more='') {
  return `<label for="f-${name}">${esc(label)}</label><select id="f-${name}" name="${name}" ${more}>${options(items, selected)}</select>`;
}
function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  setTimeout(() => $('toast').hidden = true, 6000);
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json', 'X-BigDelta-Token':state.token}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed.');
  return data;
}
async function refresh() {
  state = await api('/api/state');
  if (!project()) currentId = state.projects[0]?.id;
  if (currentId) localStorage.setItem('bigdelta-project', currentId);
  render();
}
async function mutate(action, data, message='Saved.') {
  const result = await api(`/api/projects/${currentId}/${action}`, data);
  await refresh(); toast(message); return result;
}
function modal(title, fields, action, submit='Save') {
  $('dialog-title').textContent = title; $('dialog-fields').innerHTML = fields;
  $('dialog-error').textContent = ''; $('dialog-submit').textContent = submit;
  dialogAction = action; $('dialog').showModal();
}
function render() {
  $('projects').innerHTML = state.projects.map(p => `<button class="project-button ${p.id===currentId?'active':''}" data-action="project" data-id="${p.id}">${esc(p.name)}<small>${esc(p.number || 'NO PROJECT NUMBER')} · ${esc(p.phase)}</small></button>`).join('');
  const p = project();
  $('tabs').hidden = !p; $('compile-top').hidden = !p;
  if (!p) return;
  $('project-name').textContent = p.name;
  $('project-meta').textContent = `${p.number || 'Unnumbered project'} / ${p.client || 'Client not specified'} / ${p.phase}`;
  const docs = Object.values(p.documents), revisions = docs.reduce((n,d)=> n+d.revisions.length, 0);
  const checks = state.checks[p.id] || [];
  $('stats').innerHTML = [
    ['Project progress', `${p.progress}%`, p.phase], ['Documents', docs.length, `${revisions} revisions preserved`],
    ['Coordination', checks.length, checks.length ? 'Items need review' : 'No tracked conflicts'],
    ['Report packages', p.packages.length, `${p.packages.filter(x=>x.issue).length} issued packages`]
  ].map(([title,value,caption])=>`<div class="stat"><div class="stat-title">${title}</div><b>${value}</b><small>${esc(caption)}</small>${title==='Project progress'?`<div class="progress"><div style="width:${p.progress}%"></div></div>`:''}</div>`).join('');
  $('tabs').innerHTML = ['Package builder','Design changes','Drawing compare','Calculation review','Project journal','Overview'].map(t=>`<button data-action="tab" data-id="${t}" class="${tab===t?'active':''}">${t}</button>`).join('');
  ({'Package builder':renderPackage,'Design changes':renderChanges,'Drawing compare':renderCompare,'Calculation review':renderReview,'Project journal':renderJournal,'Overview':renderOverview}[tab])();
}
function renderPackage() {
  const p = project();
  $('content').innerHTML = `<div class="toolbar"><div><h2>Report package</h2><p>Your template. Your order. Always the latest uploaded revision.</p></div><div class="actions">${button('template','Edit template')}${button('upload','＋ Add documents')}</div></div>
  ${(state.checks[p.id]||[]).length ? `<div class="notice"><b>Review required before issue.</b> ${(state.checks[p.id]||[]).length} coordination items are open. Draft compilation remains available.</div>` : ''}
  ${p.sections.map((s,i)=>`<div class="card"><div class="card-head"><h3><span class="section-num">${String(i+1).padStart(2,'0')}</span>${esc(s.name)}</h3><small>${s.document_ids.length} documents</small></div>
  ${s.document_ids.length ? s.document_ids.map((did,j)=>{
    const d=p.documents[did], r=latest(d);
    return `<div class="document"><div class="file-icon">${r.is_pdf?'PDF':'FILE'}</div><div class="document-title"><strong>${esc(d.title)}</strong><small>${esc(r.filename)} · ${r.is_pdf?`${r.pages} pages`:'Attachment only'} · ${esc(r.author)}</small></div>${pill(r.label)}<div class="actions">${button('up','↑',did,`aria-label="Move ${esc(d.title)} up"`)}${button('down','↓',did,`aria-label="Move ${esc(d.title)} down"`)}${button('move','Move',did)}${button('revision','＋ Revision',did)}${button('history','History',did)}</div></div>`;
  }).join('') : '<div class="empty">No documents yet. Empty sections are omitted from the compiled package.</div>'}</div>`).join('')}
  <div class="toolbar"><div><h2>Compiled packages</h2><p>Each compilation preserves its revision manifest and original output.</p></div>${button('compile','Compile package ↗')}</div>
  <div class="card">${p.packages.length ? `<div class="table-wrap"><table><thead><tr><th>Compiled</th><th>Status</th><th>Pages</th><th>Package</th><th>Traceability</th></tr></thead><tbody>${[...p.packages].reverse().map(x=>`<tr><td>${date(x.at)}</td><td>${pill(x.issue?'Issued':'Draft',x.issue?'':'warn')}</td><td>${x.page_count}</td><td>${link(x.id,'Download PDF ↗')}</td><td><a href="/manifest/${x.id}" target="_blank" rel="noopener">Revision manifest ↗</a></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Compile your first report to create a permanent package snapshot.</div>'}</div>`;
}
function newProject() {
  modal('Create a project',field('Project name','name','','text','required maxlength="160"')+field('Project number','number')+field('Client','client'), async data=> {
    const p = await api('/api/projects',data); currentId=p.id; tab='Package builder'; comparison=null;
    await refresh(); toast('Project created. Add your first documents.');
  },'Create project');
}
function uploadDialog(did) {
  const p=project(), d=p.documents[did], prev=d?latest(d):null;
  const references = Object.values(p.documents).filter(x=>x.id!==did);
  const selected = new Set((prev?.references || []).map(r=>`${r.document_id}:${r.revision_id}`));
  modal(d?'Upload a new revision':'Add project documents',
    `<div class="notice">${d?`Adding a revision to <b>${esc(d.title)}</b>. Previous files remain available.`:'Select multiple files to add them in filename order. PDFs are compiled; other files are retained as attachments.'}</div>`+
    (d?'':field('Document title (optional for multiple files)','title')+select('Report section','section_id',p.sections.map(s=>[s.id,s.name])))+
    field(d?'Replacement file':'Files','files','','file',`required ${d?'':'multiple'}`)+
    field('Revision label','label','','text','required maxlength="50" placeholder="e.g. P01, V3, IFC"')+
    field('Uploaded by','author',localStorage.getItem('bigdelta-author')||'','text','required maxlength="120"')+
    textarea('Revision note / reason for change','note','','required maxlength="4000"')+
    (references.length ? `<label>References used by this revision</label><p class="help">Select the revision of each document this work relies on. A newer target revision will flag this document for coordination.</p><div class="check-list">${references.map(x=>`<label for="ref-${x.id}">${esc(x.title)}</label><select id="ref-${x.id}" name="reference"><option value="">Not referenced</option>${x.revisions.slice().reverse().map(r=>`<option value="${x.id}:${r.id}" ${selected.has(`${x.id}:${r.id}`)?'selected':''}>${esc(r.label)}${r.id===latest(x).id?' (latest)':''}</option>`).join('')}</select>`).join('')}</div>` : ''),
    async (data, form)=>{
      const files = [...form.elements.files.files].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));
      if (files.some(f=>f.size>120*1024*1024)) throw new Error('Each file must be smaller than 120 MB.');
      const refs=[...form.querySelectorAll('[name=reference]')].filter(x=>x.value).map(x=>{const [document_id,revision_id]=x.value.split(':');return {document_id,revision_id};});
      localStorage.setItem('bigdelta-author',data.author);
      let done=0;
      for (const file of files) {
        const content = await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
        try {
          await api(`/api/projects/${currentId}/upload`,{...data, document_id:did, filename:file.name, content, references:refs,title:files.length===1&&data.title?data.title:file.name.replace(/\.[^.]+$/,'')});
          done++;
        } catch (e) {
          await refresh(); throw new Error(`${done} file(s) saved. ${file.name}: ${e.message} Remove saved files from your selection before retrying.`);
        }
      }
      await refresh(); toast(`${done} file(s) added. Revision history preserved.`);
    },d?'Add revision':'Upload documents');
}
function templateDialog() {
  const p=project();
  modal('Customize report template',`<p>One section per line. Reorder lines to reorder the report. Move documents before removing their section.</p>`+
    textarea('Section names','names',p.sections.map(s=>s.name).join('\n'),'required')+
    `<div class="actions">${button('export-template','Export template JSON')}<label>Import template JSON<input id="import-template" type="file" accept=".json,application/json"></label></div>`,
    data=>mutate('template',{names:data.names.split('\n').map(s=>s.trim()).filter(Boolean)},'Template updated.'));
  $('import-template').addEventListener('change',async e=> {
    try { const data=JSON.parse(await e.target.files[0].text()); if(!Array.isArray(data.sections)||data.sections.some(x=>typeof x!=='string')) throw new Error('Expected a sections array of names.');$('f-names').value=data.sections.join('\n'); }
    catch(e){$('dialog-error').textContent=e.message;}
  });
}
function compileDialog() {
  const checks=state.checks[currentId]||[];
  modal('Compile report package',`<div class="notice ${checks.length?'':'good'}">${checks.length?`<b>${checks.length} coordination items remain.</b><br>${checks.map(esc).join('<br>')}`:'No tracked coordination conflicts. Confirm the engineering review before issuing.'}</div><p class="help">Includes cover, linked contents, section dividers, bookmarks, continuous package page numbers, and the assumptions / code register. Documents whose current revision is a PDF are included.</p>`+
    field('Generated by','generated_by',localStorage.getItem('bigdelta-author')||'','text','maxlength="160"')+
    field('Checked by','checked_by','','text','maxlength="160"')+field('Approved by','approved_by','','text','maxlength="160"')+
    `<label><input type="checkbox" name="issue" ${checks.length?'disabled':''}> Issue this package (otherwise create a draft)</label><p class="help">Names are workflow records. This does not apply a digital signature or professional seal.</p>`,
    async data=>{const result=await mutate('compile',{...data,issue:data.issue==='on'},'Package compiled. Download it from Compiled packages.');tab='Package builder';render();},'Compile PDF');
}
function renderChanges() {
  const p=project(),checks=state.checks[p.id]||[];
  $('content').innerHTML=`<div class="toolbar"><div><h2>Design intent & coordination</h2><p>Record why the design changed, then close the loop on every affected document.</p></div>${button('new-change','＋ Log design change')}</div>
  <div class="notice ${checks.length?'':'good'}"><b>${checks.length?`${checks.length} items require review`:'No tracked conflicts'}</b>${checks.length?'<br>'+checks.map(esc).join('<br>'):'. References are checked against the latest uploaded revisions.'}</div>
  ${p.changes.length?p.changes.slice().reverse().map(c=>`<div class="card pad"><div class="toolbar"><h3>${esc(c.title)}</h3>${pill(Object.values(c.impacts).every(Boolean)?'Reviewed':'Action required',Object.values(c.impacts).every(Boolean)?'':'warn')}</div><div class="note">${esc(c.intent)}</div><p class="help">Logged ${date(c.at)}</p>${Object.entries(c.impacts).map(([did,res])=>`<div class="impact"><div><b>${esc(p.documents[did].title)}</b>${res?`<p class="help">Reviewed at ${esc(p.documents[did].revisions.find(r=>r.id===res.revision_id)?.label)} · ${esc(res.note)}</p>`:'<p class="help">Review or update the underlying document.</p>'}</div>${res?pill('Resolved'):button('resolve','Record resolution',c.id,`data-document="${did}"`)}</div>`).join('')}</div>`).join(''):'<div class="card empty">No changes logged yet. Track criteria updates, openings, load paths, and plan-checker comments here.</div>'}`;
}
function changeDialog() {
  const docs=Object.values(project().documents);
  if(!docs.length) return toast('Add project documents before logging a design change.');
  modal('Log a design change',field('Change / issue title','title','','text','required maxlength="200"')+
    textarea('Design intent / reason / learning','intent','','required maxlength="4000"')+
    `<label>Affected documents</label><div class="check-list">${docs.map(d=>`<label><input name="impact" type="checkbox" value="${d.id}">${esc(d.title)}</label>`).join('')}</div>`,
    (data,form)=>mutate('change',{...data,document_ids:[...form.querySelectorAll('[name=impact]:checked')].map(x=>x.value)},'Design change logged.'));
}
function renderJournal() {
  const p=project();
  $('content').innerHTML=`<div class="toolbar"><div><h2>Project journal</h2><p>Keep the assumptions visible, the code references explicit, and the lessons useful.</p></div>${button('record','＋ Add entry')}</div>
  <div class="notice"><b>Engineering basis is recorded by your team.</b> Cite the code title, adopted edition, section, and source URL. Assumptions and code citations are included in compiled reports.</div>
  ${[['assumption','Assumptions','warn'],['code','Code citations',''],['comment','Comments & lessons','neutral']].map(([kind,title,style])=>`<div class="card"><div class="card-head"><h3>${title}</h3>${pill(p.records.filter(r=>r.kind===kind).length+' entries',style)}</div>${p.records.filter(r=>r.kind===kind).reverse().map(r=>`<div class="record"><div class="note">${esc(r.text)}</div><small>${esc(r.author)} · ${date(r.at)}</small></div>`).join('')||`<div class="empty">No ${title.toLowerCase()} recorded.</div>`}</div>`).join('')}`;
}
function recordDialog() {
  modal('Add journal entry',select('Entry type','kind',[['comment','Comment / lesson learned'],['assumption','Assumption'],['code','Code citation']])+
    textarea('Details (include edition, section and URL for code citations)','text','','required maxlength="6000"')+
    field('Recorded by','author',localStorage.getItem('bigdelta-author')||'','text','required maxlength="120"'),
    data=>mutate('record',data,'Journal entry added.'));
}
function renderOverview() {
  const p=project();
  $('content').innerHTML=`<div class="toolbar"><div><h2>Project overview</h2><p>Follow the project through planning, design, construction, and closeout.</p></div>${button('progress','Update progress')}</div>
  <div class="grid"><div class="card pad"><div class="eyebrow">CURRENT PHASE</div><h2>${p.phase}</h2><p>${p.progress}% complete · manually assessed by your team</p><div class="progress"><div style="width:${p.progress}%"></div></div></div><div class="card pad"><div class="eyebrow">PROJECT BASIS</div><p>${p.records.filter(x=>x.kind==='assumption').length} assumptions recorded</p><p>${p.records.filter(x=>x.kind==='code').length} code citations recorded</p><p>${p.changes.length} design changes tracked</p></div></div>
  <div class="toolbar"><h2>Activity history</h2>${button('export-project','Export project register')}</div><div class="card">${p.events.slice().reverse().map(e=>`<div class="record"><div>${esc(e.action)}</div><small>${date(e.at)}</small></div>`).join('')}</div>`;
}
function renderCompare() {
  const revisions=Object.values(project().documents).flatMap(d=>d.revisions.filter(r=>r.is_pdf).map(r=>[r.id,`${d.title} / ${r.label} (${r.pages} pages)`]));
  $('content').innerHTML=`<div class="toolbar"><div><h2>Drawing comparison</h2><p>Inspect revisions side by side, as an overlay, or with changed pixels highlighted.</p></div></div><div class="notice">Compare matching sheet sizes and aligned drawing exports. Raster differences are a visual review aid; document meaning and design congruency require engineering review.</div>
  <div class="card pad"><form id="compare-form"><div class="compare-controls"><div>${select('Earlier revision','left',revisions)}${field('Page','left_page',1,'number','min="1" required')}</div><div>${select('Later revision','right',revisions,revisions[revisions.length-1]?.[0])}${field('Page','right_page',1,'number','min="1" required')}</div></div><button class="primary" style="margin-top:20px" ${revisions.length?'':'disabled'}>Compare pages</button></form></div><div id="compare-result"></div>`;
  $('compare-form').addEventListener('submit',async e=>{
    e.preventDefault();const form=e.target,btn=form.querySelector('button');btn.disabled=true;btn.textContent='Rendering pages…';
    try{comparison=await api(`/api/projects/${currentId}/compare`,Object.fromEntries(new FormData(form)));renderComparison();}
    catch(e){toast(e.message);}finally{btn.disabled=false;btn.textContent='Compare pages';}
  });
  if(comparison)renderComparison();
}
function renderComparison(mode='overlay') {
  if(!comparison)return;
  $('compare-result').innerHTML=`<div class="toolbar"><div><h3>${comparison.changed_percent}% of rendered pixels changed</h3><p>Overlay: old ink is magenta, new ink is cyan; coincident ink is dark.</p></div><div class="actions">${button('compare-mode','Overlay','overlay')}${button('compare-mode','Highlight','difference')}${button('compare-mode','Side by side','side')}</div></div><div class="compare-canvas">${mode==='side'?`<div class="split-images"><img alt="Earlier drawing" src="${comparison.left}"><img alt="Later drawing" src="${comparison.right}"></div>`:`<img class="comparison" alt="Drawing ${esc(mode)}" src="${comparison[mode]}">`}</div>`;
}
function exportJSON(name,data) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
}
async function action(name,id,element) {
  const p=project();
  switch(name) {
    case 'project':currentId=id;comparison=null;reviewSession=null;clearTimeout(reviewTimer);localStorage.setItem('bigdelta-project',id);render();break;
    case 'tab':clearTimeout(reviewTimer);tab=id;render();break;
    case 'upload':uploadDialog();break;
    case 'revision':uploadDialog(id);break;
    case 'template':templateDialog();break;
    case 'compile':compileDialog();break;
    case 'new-change':changeDialog();break;
    case 'record':recordDialog();break;
    case 'resolve':modal('Record impact resolution',`<p>Confirm the affected document has been updated or reviewed. This records the resolution against its latest uploaded revision.</p>`+textarea('Resolution / review note','note','','required maxlength="4000"'),data=>mutate('resolve',{...data,change_id:id,document_id:element.dataset.document},'Impact resolution recorded.'));break;
    case 'progress':modal('Update project progress',select('Phase','phase',['Planning','Design','Construction','Closeout'].map(x=>[x,x]),p.phase)+field('Overall progress (%)','progress',p.progress,'number','min="0" max="100" required'),data=>mutate('update',data,'Progress updated.'));break;
    case 'up':case 'down': {
      const s=p.sections.find(s=>s.document_ids.includes(id)),pos=s.document_ids.indexOf(id);
      await mutate('arrange',{document_id:id,section_id:s.id,position:pos+(name==='up'?-1:1)},'Document order updated.');break;
    }
    case 'move': {
      const s=p.sections.find(s=>s.document_ids.includes(id));
      modal('Move document',select('Destination section','section_id',p.sections.map(s=>[s.id,s.name]),s.id)+field('Position (1 = first)','position',1,'number','min="1" required'),data=>mutate('arrange',{...data,document_id:id,position:Number(data.position)-1},'Document moved.'));break;
    }
    case 'history': {
      const d=p.documents[id];
      modal(`${d.title} / revisions`,d.revisions.slice().reverse().map(r=>`<div class="record"><div class="toolbar">${pill(r.label)}${link(r.id,'Download original ↗')}</div><div class="note">${esc(r.note)}</div><small>${esc(r.author)} · ${date(r.at)} · ${r.pages||'Attachment'} ${r.pages?'pages':''}</small><p class="help">${r.references.map(ref=>`Uses ${esc(p.documents[ref.document_id].title)} / ${esc(p.documents[ref.document_id].revisions.find(x=>x.id===ref.revision_id)?.label)}`).join('<br>')||'No document dependencies recorded.'}</p><p class="help">SHA-256: ${esc(r.sha256)}</p></div>`).join(''),async()=>{},'Close');break;
    }
    case 'export-template':exportJSON('bigdelta-template.json',{name:p.name,sections:$('f-names').value.split('\n').map(s=>s.trim()).filter(Boolean)});break;
    case 'export-project':exportJSON('bigdelta-project-register.json',p);toast('Register exported. Copy the full data folder to back up files too.');break;
    case 'compare-mode':renderComparison(id);break;
    case 'review-save':await saveReview();renderReviewResults();toast('Review decisions saved.');break;
    case 'review-export':await exportReview(element);break;
    case 'review-json':exportJSON('bigdelta-calculation-review.json',reviewSession.job);break;
    case 'review-open':await openReview(id);break;
    case 'review-manual':manualFinding();break;
    case 'review-prev':reviewPage=Math.max(0,reviewPage-1);renderReviewResults();break;
    case 'review-next':reviewPage++;renderReviewResults();break;
  }
}
document.addEventListener('click',e=>{const el=e.target.closest('[data-action]');if(el)action(el.dataset.action,el.dataset.id,el).catch(e=>toast(e.message));});
$('new-project').addEventListener('click',newProject);$('start-project').addEventListener('click',newProject);
$('compile-top').addEventListener('click',compileDialog);$('close-dialog').addEventListener('click',()=>$('dialog').close());
$('dialog').addEventListener('cancel',e=>{if($('dialog-submit').disabled)e.preventDefault();});
$('dialog-form').addEventListener('submit',async e=>{
  e.preventDefault(); const btn=$('dialog-submit');btn.disabled=true;$('close-dialog').disabled=true;$('dialog-error').textContent='';const label=btn.textContent;btn.textContent='Working…';
  try{await dialogAction(Object.fromEntries(new FormData(e.target)),e.target);$('dialog').close();}
  catch(e){$('dialog-error').textContent=e.message;}
  finally{btn.disabled=false;$('close-dialog').disabled=false;btn.textContent=label;}
});
refresh().catch(e=>toast(`Cannot load workspace: ${e.message}`));

const reviewCategories = [
  ['acceptance','1 · Acceptance changed'], ['assumption','2 · Fundamental assumption'],
  ['loading','3 · Loading condition'], ['removed_check','4 · Check disappeared'],
  ['propagation','5 · Input without downstream update'], ['geometry_material','6 · Geometry / material'],
  ['conclusion','7 · Conflicting conclusion'], ['result','8 · Calculated result'], ['other','9 · Other change']
];
function renderReview() {
  clearTimeout(reviewTimer);
  const p=project(),pid=p.id;
  const revisions=Object.values(p.documents).flatMap(d=>d.revisions.filter(r=>r.is_pdf).map(r=>[r.id,`${d.title} / ${r.label} (${r.pages} pages)`]));
  $('content').innerHTML=`<div class="toolbar"><div><h2>Calculation revision review</h2><p>Find changes across a complete package, review the findings, then export individual callouts.</p></div>${button('upload','＋ Add PDFs')}</div>
  <div class="notice"><b>Your review rules:</b> node loads are excluded. Acceptance transitions always remain visible. Numerical results are grouped only when corresponding applied loads change in the same calculation section. Each included finding becomes one editable PDF callout.</div>
  <div class="card pad"><form id="review-form"><div class="compare-controls"><div>${select('Earlier PDF','left',revisions)}</div><div>${select('Newer PDF','right',revisions,revisions.at(-1)?.[0])}</div></div><p class="help">Choose the revision direction explicitly. Uploads may use separate document titles or unique revision labels. Processing stays on this computer.</p><button class="primary" ${revisions.length<2?'disabled':''}>Analyze calculation packages</button></form></div>
  <div id="review-results"></div>
  <div class="toolbar"><h3>Saved comparisons</h3></div><div id="review-jobs" class="card pad">Loading…</div>
  <div class="toolbar"><h3>Exported callout copies</h3></div><div class="card pad">${(p.reviews||[]).length?p.reviews.slice().reverse().map(r=>`<p>${link(r.id,'Download reviewed PDF ↗')} · ${r.callout_count} callouts · ${date(r.at)}</p>`).join(''):'No review exports yet.'}</div>`;
  $('review-form').addEventListener('submit',async e=>{
    e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;
    try {
      const job=await api(`/api/projects/${pid}/review_start`,Object.fromEntries(new FormData(e.target)));
      if(currentId===pid&&tab==='Calculation review'){reviewSession={pid,job};reviewPage=0;renderReviewResults();pollReview(pid,job.id);}
    } catch(err){toast(err.message);}finally{b.disabled=false;}
  });
  api(`/api/projects/${pid}/reviews`).then(jobs=>{
    if(currentId!==pid||tab!=='Calculation review')return;
    $('review-jobs').innerHTML=jobs.length?jobs.map(j=>`<div class="toolbar"><span>${esc(j.earlier_name)} → ${esc(j.newer_name)} · ${esc(j.status)} · ${date(j.at)}</span>${button('review-open','Open',j.id)}</div>`).join(''):'No comparisons yet.';
  }).catch(e=>toast(e.message));
  if(reviewSession?.pid===pid){renderReviewResults();if(['queued','running'].includes(reviewSession.job.status))pollReview(pid,reviewSession.job.id);}
}
async function openReview(id) {
  const pid=currentId;
  const job=await api(`/api/projects/${pid}/reviews/${id}`);
  if(currentId!==pid||tab!=='Calculation review')return;
  reviewSession={pid,job};reviewPage=0;renderReviewResults();
  if(['queued','running'].includes(job.status))pollReview(pid,id);
}
function pollReview(pid,id) {
  clearTimeout(reviewTimer);
  reviewTimer=setTimeout(async()=>{
    if(currentId!==pid||tab!=='Calculation review'||reviewSession?.job.id!==id)return;
    try {
      const job=await api(`/api/projects/${pid}/reviews/${id}`);
      if(currentId!==pid||reviewSession?.job.id!==id)return;
      reviewSession.job=job;renderReviewResults();
      if(['queued','running'].includes(job.status))pollReview(pid,id);
    }catch(e){toast(e.message);}
  },1000);
}
function renderReviewResults() {
  const root=$('review-results');if(!root||!reviewSession)return;
  const j=reviewSession.job;
  if(j.status==='failed'){root.innerHTML=`<div class="notice"><b>Review stopped.</b> ${esc(j.error||j.message)}</div>`;return;}
  if(j.status!=='complete'){
    root.innerHTML=`<div class="card pad" role="status"><h3>${esc(j.message)}</h3><p>${j.progress||0}%</p><progress max="100" value="${Number(j.progress)||0}"></progress><p class="help">You can switch tabs while comparison runs. Reopen it from Saved comparisons.</p></div>`;return;
  }
  const r=j.result,findings=r.findings, included=findings.filter(f=>f.disposition==='include').length;
  const pageSize=30;reviewPage=Math.min(reviewPage,Math.max(0,Math.ceil(findings.length/pageSize)-1));
  const shown=findings.slice(reviewPage*pageSize,(reviewPage+1)*pageSize);
  root.innerHTML=`<div class="toolbar"><div><h3>${findings.length} candidates · ${included} included</h3><p>${r.unchanged_pages} pages matched unchanged; ${r.grouped_results.length} result changes grouped under revised loads.</p></div><div class="actions">${button('review-manual','＋ Add finding')}${button('review-save','Save decisions')}${button('review-json','Export review JSON')}${button('review-export','Export callout PDF')}</div></div>
  <div class="notice"><b>Review each candidate.</b> Rule-based text matching does not verify engineering adequacy. Edit descriptions and categories, then choose Include or Exclude. Pending items are not exported. Unlabeled equations, numeric tables and graphics may need manual findings.</div>
  <details class="card pad"><summary>Coverage and exclusions (${r.coverage_gaps.length} items)</summary><p>Node-load rows excluded: ${r.excluded_node_load_rows}. No node-load verification was performed.</p>${r.limitations.map(x=>`<p class="help">${esc(x)}</p>`).join('')}${r.coverage_gaps.slice(0,50).map(g=>`<p class="help">${esc(JSON.stringify(g))}</p>`).join('')}${r.coverage_gaps.length>50?'<p>Export review JSON for the full coverage list.</p>':''}</details>
  <details class="card pad"><summary>Unclassified text / formula fragments (${(r.unclassified_changes||[]).length})</summary><p class="help">These fragments were not classified as engineering findings. Inspect the source and add manual findings when needed. Full details are in Export review JSON.</p>${(r.unclassified_changes||[]).slice(0,30).map(f=>`<div class="record"><b>Newer p${f.newer_page}</b><pre>${esc(f.summary)}</pre></div>`).join('')}</details>
  <details class="card pad"><summary>Grouped numerical results (${r.grouped_results.length})</summary>${r.grouped_results.slice(0,50).map(f=>`<div class="record"><b>Newer p${f.newer_page}</b><pre>${esc(f.summary)}</pre></div>`).join('')}${r.grouped_results.length>50?'<p>Export review JSON for the full grouped list.</p>':''}</details>
  <div class="toolbar"><span>Findings ${findings.length?reviewPage*pageSize+1:0}–${Math.min((reviewPage+1)*pageSize,findings.length)} of ${findings.length}</span><div class="actions">${button('review-prev','Previous','',''+(reviewPage===0?'disabled':''))}${button('review-next','Next','',''+((reviewPage+1)*pageSize>=findings.length?'disabled':''))}</div></div>
  ${shown.map(f=>`<article class="card pad review-finding" data-finding="${esc(f.id)}"><div class="toolbar"><b>${esc(f.id)} · newer p${f.newer_page} · earlier p${f.earlier_page||'unmatched'}</b>${pill(f.confidence)}</div><p class="help">${esc(f.section||'')}</p><label>Title<input data-review-field="title" value="${esc(f.title)}" maxlength="240"></label><div class="compare-controls"><div><label>Priority / category<select data-review-field="category">${options(reviewCategories,f.category)}</select></label></div><div><label>Disposition<select data-review-field="disposition">${options([['pending','Pending review'],['include','Include in callout export'],['exclude','Exclude']],f.disposition)}</select></label></div></div><label>Change summary / description<textarea data-review-field="summary" maxlength="6000">${esc(f.summary)}</textarea></label></article>`).join('')||'<div class="card empty">No labeled-text candidates found. Inspect coverage gaps and add manual findings for engineering changes the rules could not interpret.</div>'}`;
  root.addEventListener('input',updateReviewField);
  root.addEventListener('change',updateReviewField);
}
function updateReviewField(e) {
  const el=e.target.closest('[data-review-field]'),card=el?.closest('[data-finding]');
  if(!card||!reviewSession)return;
  const f=reviewSession.job.result.findings.find(x=>x.id===card.dataset.finding);
  f[el.dataset.reviewField]=el.value;
}
async function saveReview() {
  if(reviewSession?.job.status!=='complete')throw new Error('Open a completed comparison first.');
  const pid=reviewSession.pid, id=reviewSession.job.id;
  const job=await api(`/api/projects/${pid}/review_update`,{job_id:id,findings:reviewSession.job.result.findings});
  if(reviewSession?.job.id===id)reviewSession.job=job;
}
async function exportReview(el) {
  el.disabled=true;el.textContent='Writing callouts…';
  try {
    await saveReview();
    await api(`/api/projects/${reviewSession.pid}/review_export`,{job_id:reviewSession.job.id});
    await refresh();toast('Callout copy saved. Download it under Exported callout copies.');
  }finally{el.disabled=false;el.textContent='Export callout PDF';}
}
function manualFinding() {
  if(reviewSession?.job.status!=='complete')return toast('Open a completed comparison first.');
  modal('Add an individual discrepancy',field('Newer PDF page','newer_page',1,'number',`min="1" max="${reviewSession.job.result.newer_pages}" required`)+
    field('Text to point to (optional; exact source text)','target_text')+
    select('Priority / category','category',reviewCategories)+field('Title','title','','text','required maxlength="240"')+
    textarea('Change summary / description','summary','','required maxlength="6000"'),async data=>{
      reviewSession.job.result.findings.push({...data,id:'M'+Date.now(),newer_page:Number(data.newer_page),earlier_page:null,disposition:'include',confidence:'manual',section:'Manual finding'});
      try{await saveReview();renderReviewResults();}catch(e){reviewSession.job.result.findings.pop();throw e;}
    },'Add callout finding');
}
