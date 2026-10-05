const $ = id => document.getElementById(id);
let refreshTimer;
let savedConfigs = {};
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

function formPayload() {
  const selectors = $('selectors').value.trim() ? JSON.parse($('selectors').value) : {};
  return {url:$('url').value, name:$('name').value, max_pages:Number($('max-pages').value), selectors};
}
async function api(url, options={}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(body.error || `Request failed (${response.status})`);
  return body;
}
async function loadJobs() {
  try {
    const jobs = await api('/api/jobs');
    $('total-jobs').textContent = jobs.length;
    $('total-records').textContent = jobs.reduce((total, job) => total + job.records_found, 0);
    $('active-jobs').textContent = jobs.filter(job => ['Pending','Running'].includes(job.status)).length;
    $('jobs').innerHTML = jobs.length ? jobs.map(job => `
      <article class="job"><div class="job-line"><div><div class="job-name">${escapeHtml(job.name)}</div>
      <div class="job-sub">${escapeHtml(job.start_url)} · ${job.pages_processed}/${job.pages_requested} pages · ${job.records_found} records</div></div>
      <span class="pill ${['Running','Pending'].includes(job.status)?'running':job.status==='Failed'?'failed':''}">${escapeHtml(job.status)}</span></div>
      ${['Running','Pending'].includes(job.status)?`<div class="progress"><i style="width:${Math.min(100,Math.round(job.pages_processed*100/job.pages_requested))}%"></i></div>`:''}
      <div class="job-actions">${job.records_found?`<button class="small" data-action="results" data-id="${job.id}">View results</button><a class="small" href="/api/jobs/${job.id}/export?format=csv">CSV</a><a class="small" href="/api/jobs/${job.id}/export?format=json">JSON</a>`:''}
      ${['Running','Pending'].includes(job.status)?`<button class="small" data-action="cancel" data-id="${job.id}">Cancel</button>`:''}
      ${['Failed','Partially Completed','Cancelled','Completed'].includes(job.status)?`<button class="small" data-action="retry" data-id="${job.id}">Run again</button>`:''}</div></article>`).join('') : '<div class="empty">No jobs yet. Start with a public page URL.</div>';
    if (jobs.some(job => ['Running','Pending'].includes(job.status))) refreshTimer = setTimeout(loadJobs, 1800);
  } catch (error) { $('jobs').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`; }
}
async function showResults(id, page=1, query='') {
  try {
    const data = await api(`/api/jobs/${id}/results?page=${page}&per_page=25&q=${encodeURIComponent(query)}`);
    let section = document.querySelector('.results');
    if (!section) { section=document.createElement('section'); section.className='results'; document.querySelector('.layout > section:nth-child(2)').append(section); }
    const columns = [...new Set(data.results.flatMap(row => Object.keys(row)))];
    section.innerHTML = `<div class="results-head"><strong>Results · ${data.total}</strong><div><input id="search-results" placeholder="Search records" value="${escapeHtml(query)}"><button class="small" data-action="search" data-id="${id}">Search</button></div></div>
      ${data.results.length?`<table><tbody>${data.results.map(row=>`<tr>${columns.slice(0,6).map(key=>`<td><b>${escapeHtml(key)}</b><br>${escapeHtml(typeof row[key]==='object'?JSON.stringify(row[key]):row[key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'<div class="empty">No matching records.</div>'}
      <div class="job-actions"><button class="small" data-action="page" data-id="${id}" data-page="${page-1}" data-query="${escapeHtml(query)}" ${page<=1?'disabled':''}>Previous</button><span class="job-sub">Page ${page} · ${data.total} records</span><button class="small" data-action="page" data-id="${id}" data-page="${page+1}" data-query="${escapeHtml(query)}" ${page*data.per_page>=data.total?'disabled':''}>Next</button></div>`;
  } catch (error) { alert(error.message); }
}
async function loadConfigs() {
  try {
    const configs = await api('/api/configurations');
    savedConfigs = Object.fromEntries(configs.map(config => [config.id, config]));
    $('configs').innerHTML = configs.length ? configs.map(config => `<div class="saved-row"><span><b>${escapeHtml(config.name)}</b><br><span class="job-sub">${escapeHtml(config.start_url)} · ${config.max_pages} pages</span></span><span><button class="small" data-action="use-config" data-id="${config.id}">Use</button> <button class="small" data-action="delete-config" data-id="${config.id}">Delete</button></span></div>`).join('') : '<div class="empty">Save a URL and its selectors to reuse them later.</div>';
  } catch {}
}
function useConfig(config) { $('url').value=config.start_url; $('name').value=config.name; $('max-pages').value=config.max_pages; $('selectors').value=JSON.stringify(config.selectors,null,2); window.scrollTo({top:0,behavior:'smooth'}); }
$('job-form').addEventListener('submit', async event => {
  event.preventDefault(); $('form-status').textContent='';
  try { const job=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(formPayload())}); $('form-status').style.color='#345a48'; $('form-status').textContent=`Job #${job.id} queued.`; loadJobs(); }
  catch (error) { $('form-status').style.color='#a33'; $('form-status').textContent=error.message; }
});
$('save-config').addEventListener('click', async () => {
  try { await api('/api/configurations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(formPayload())}); $('form-status').style.color='#345a48'; $('form-status').textContent='Configuration saved.'; loadConfigs(); }
  catch (error) { $('form-status').style.color='#a33'; $('form-status').textContent=error.message; }
});
$('jobs').addEventListener('click', async event => {
  const button=event.target.closest('[data-action]'); if(!button)return; const id=Number(button.dataset.id);
  if(button.dataset.action==='results') showResults(id);
  if(button.dataset.action==='cancel') { try { await api(`/api/jobs/${id}/cancel`,{method:'POST'}); loadJobs(); } catch(error) { alert(error.message); } }
  if(button.dataset.action==='retry') { try { await api(`/api/jobs/${id}/retry`,{method:'POST'}); loadJobs(); } catch(error) { alert(error.message); } }
});
$('configs').addEventListener('click', async event => {
  const button=event.target.closest('[data-action]'); if(!button)return; const id=Number(button.dataset.id);
  if(button.dataset.action==='use-config') useConfig(savedConfigs[id]);
  if(button.dataset.action==='delete-config') { try { await api(`/api/configurations/${id}`,{method:'DELETE'}); loadConfigs(); } catch(error) { alert(error.message); } }
});
document.addEventListener('click', event => {
  const button=event.target.closest('[data-action="page"],[data-action="search"]'); if(!button)return;
  showResults(Number(button.dataset.id),button.dataset.action==='search'?1:Number(button.dataset.page),button.dataset.action==='search'?$('search-results').value:button.dataset.query);
});
$('refresh').addEventListener('click',()=>{clearTimeout(refreshTimer);loadJobs();});
loadJobs(); loadConfigs();
