import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, Boxes, Check, CheckCircle2, CircleAlert, Cpu, Download,
  KeyRound, LayoutDashboard, Play, Plus, RefreshCw, Server,
  ShieldCheck, SquareStack, Trash2, Upload, Wifi, X,
} from 'lucide-react';
import './styles.css';

const API_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' && window.location.hostname ? `http://${window.location.hostname}:8000` : 'http://127.0.0.1:8000');
const HOST_TOKEN = import.meta.env.VITE_HOST_TOKEN || '';

async function api(path, options = {}) {
  const r = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${HOST_TOKEN}`, 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.status === 204 ? null : r.json();
}

async function downloadBlob(path, filename) {
  const r = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${HOST_TOKEN}` } });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Error ${r.status}`);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(await r.blob());
  a.download = filename;
  a.click();
}

const navItems = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'clients', label: 'Clients', icon: Boxes },
  { id: 'jobs', label: 'Jobs', icon: SquareStack },
];

function App() {
  const [view, setView] = useState('overview');
  const [clients, setClients] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  async function refreshClients() {
    setLoading(true);
    try { setClients(await api('/clients')); setError(''); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  async function refreshJobs() {
    try { setJobs(await api('/jobs')); } catch (_) {}
  }

  useEffect(() => { refreshClients(); refreshJobs(); }, []);

  // poll jobs every 10s while jobs tab is active
  useEffect(() => {
    if (view !== 'jobs') return;
    const t = setInterval(refreshJobs, 10000);
    return () => clearInterval(t);
  }, [view]);

  async function changeClient(clientId, action) {
    try {
      if (action === 'kit') { await downloadBlob(`/clients/${clientId}/kit`, `${clientId}-kit.zip`); return; }
      await api(action === 'remove' ? `/clients/${clientId}` : `/clients/${clientId}/${action}`,
        { method: action === 'remove' ? 'DELETE' : 'POST' });
      await refreshClients();
    } catch (e) { setError(e.message); }
  }

  async function createClient(form) {
    try { await api('/clients', { method: 'POST', body: JSON.stringify(form) }); setShowCreate(false); await refreshClients(); }
    catch (e) { setError(e.message); }
  }

  async function submitJob(form) {
    try {
      await api('/jobs/nvflare', {
        method: 'POST',
        body: JSON.stringify({
          participants: form.participants,
          num_rounds: form.rounds,
          local_epochs: form.epochs,
          batch_size: form.batchSize,
          data_paths: form.dataPaths,
          min_clients: form.minClients || form.participants.length,
        }),
      });
      await refreshJobs();
      setView('jobs');
      setError('');
    } catch (e) { setError(e.message); }
  }

  const onlineCount = clients.filter(c => c.status === 'ONLINE').length;
  const pendingCount = clients.filter(c => c.status === 'PENDING').length;
  const approvedCount = clients.filter(c => ['APPROVED', 'ONLINE', 'OFFLINE'].includes(c.status)).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark"><span>NX</span></div>
        <div className="brand-copy"><strong>NexMesh</strong><span>Coordinator</span></div>
        <nav className="primary-nav">
          {navItems.map(({ id, label, icon: Icon }) => (
            <button className={view === id ? 'nav-item active' : 'nav-item'} key={id} onClick={() => setView(id)}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
              {id === 'clients' && pendingCount > 0 && <em>{pendingCount} pending</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="secure-note"><ShieldCheck size={15} /><span>Private federation</span></div>
          <span className="version">Coordinator v0.1</span>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Federated operations</p>
            <h1>{view === 'overview' ? 'Dashboard' : navItems.find(i => i.id === view)?.label}</h1>
          </div>
          <div className="topbar-actions">
            <span className="connection-pill"><span className="status-dot online" /> Coordinator online</span>
            <button className="icon-button" onClick={() => { refreshClients(); refreshJobs(); }}><RefreshCw size={17} /></button>
            <div className="avatar">H</div>
          </div>
        </header>

        {error && <div className="alert error"><CircleAlert size={17} /><span>{error}</span><button onClick={() => setError('')}><X size={15} /></button></div>}

        {view === 'overview' && <Overview clients={clients} onlineCount={onlineCount} approvedCount={approvedCount} pendingCount={pendingCount} onNavigate={setView} />}
        {view === 'clients' && <Clients clients={clients} loading={loading} onCreate={() => setShowCreate(true)} onChange={changeClient} onRefresh={refreshClients} />}
        {view === 'jobs' && <Jobs jobs={jobs} clients={clients} onSubmit={submitJob} onRefresh={refreshJobs} />}
      </main>

      {showCreate && <CreateClientModal onClose={() => setShowCreate(false)} onCreate={createClient} />}
    </div>
  );
}

function Jobs({ jobs, clients, onSubmit, onRefresh }) {
  const [form, setForm] = useState({ rounds: 5, epochs: 1, batchSize: 64, minClients: '', participants: [], dataPaths: {} });
  const [submitting, setSubmitting] = useState(false);
  const approvedClients = clients.filter(c => ['APPROVED', 'ONLINE', 'OFFLINE'].includes(c.status));

  const toggle = (id) => setForm(f => ({
    ...f,
    participants: f.participants.includes(id) ? f.participants.filter(p => p !== id) : [...f.participants, id],
  }));
  const setPath = (id, v) => setForm(f => ({ ...f, dataPaths: { ...f.dataPaths, [id]: v } }));

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    await onSubmit(form);
    setForm({ rounds: 5, epochs: 1, batchSize: 64, minClients: '', participants: [], dataPaths: {} });
    setSubmitting(false);
  }

  return (
    <section>
      <div className="section-toolbar">
        <div><p className="eyebrow">Federated jobs</p><p className="section-copy">Select approved participants and submit an NVFlare federated run.</p></div>
        <button className="icon-button" onClick={onRefresh}><RefreshCw size={17} /></button>
      </div>
      <div className="job-layout">
        <form className="panel job-form" onSubmit={submit}>
          <div className="panel-heading"><div><p className="eyebrow">New job</p><h3>Submit a federated run</h3></div><Upload size={18} /></div>
          <div className="field-grid">
            <label>Rounds<input type="number" min="1" value={form.rounds} onChange={e => setForm({ ...form, rounds: +e.target.value })} /></label>
            <label>Local epochs<input type="number" min="1" value={form.epochs} onChange={e => setForm({ ...form, epochs: +e.target.value })} /></label>
            <label>Batch size<input type="number" min="1" value={form.batchSize} onChange={e => setForm({ ...form, batchSize: +e.target.value })} /></label>
          </div>
          <label>Min clients <span className="field-hint">optional — defaults to all selected</span>
            <input type="number" min="1" placeholder={form.participants.length || 1} value={form.minClients} onChange={e => setForm({ ...form, minClients: +e.target.value || '' })} />
          </label>
          <div className="form-note"><ShieldCheck size={15} /> Raw data never leaves participant machines. Only model updates are exchanged.</div>
          <button className="primary-button" type="submit" disabled={submitting || !form.participants.length}>
            <Play size={16} /> {submitting ? 'Submitting…' : 'Submit NVFlare job'}
          </button>
        </form>

        <div className="panel participant-panel">
          <div className="panel-heading"><div><p className="eyebrow">Participants</p><h3>Select approved clients</h3></div><span className="selection-count">{form.participants.length} selected</span></div>
          {approvedClients.length === 0
            ? <EmptyState icon={Boxes} title="No approved clients" copy="Approve a client before assigning it to a job." />
            : <div className="participant-list">
                {approvedClients.map(c => (
                  <div key={c.id} className="participant-entry">
                    <label className="participant-option">
                      <input type="checkbox" checked={form.participants.includes(c.id)} onChange={() => toggle(c.id)} />
                      <span className="client-avatar">{c.id.slice(0, 2).toUpperCase()}</span>
                      <span><strong>{c.display_name}</strong><small>{c.id} · {c.status.toLowerCase()}</small></span>
                      <Check size={15} />
                    </label>
                    {form.participants.includes(c.id) && (
                      <input className="data-path-input" placeholder={`/data/${c.id}/mnist.pt`}
                        value={form.dataPaths[c.id] || ''} onChange={e => setPath(c.id, e.target.value)} />
                    )}
                  </div>
                ))}
              </div>}
        </div>
      </div>

      <div className="panel table-panel jobs-list">
        <div className="panel-heading"><div><p className="eyebrow">Job queue</p><h3>Submitted jobs</h3></div></div>
        {jobs.length === 0
          ? <EmptyState icon={SquareStack} title="No jobs yet" copy="Submit a job to assign work to participants." />
          : jobs.map(job => (
              <div className="job-row" key={job.id}>
                <div><strong>{job.id}</strong><span>{job.participants?.length ?? 0} participants · {job.status?.toLowerCase()}</span></div>
                <StatusBadge status={job.status} />
                {job.result && <pre className="job-result">{JSON.stringify(job.result, null, 2)}</pre>}
              </div>
            ))}
      </div>
    </section>
  );
}

function Overview({ clients, onlineCount, approvedCount, pendingCount, onNavigate }) {
  return (
    <>
      <section className="hero-band">
        <div>
          <div className="tag"><Wifi size={14} /> Remote-first federation</div>
          <h2>Keep data where it belongs.<br /><span>Move the model, not the records.</span></h2>
          <p>NexMesh coordinates trusted clients across independent machines. Raw datasets stay local while model updates flow through NVFlare.</p>
        </div>
        <div className="hero-orbit"><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="orbit-core"><Server size={25} /></div><span className="orbit-node node-a" /><span className="orbit-node node-b" /><span className="orbit-node node-c" /></div>
      </section>
      <div className="stat-grid">
        <StatCard label="Registered clients" value={clients.length} detail="Across all modes" icon={Boxes} accent="teal" />
        <StatCard label="Online now" value={onlineCount} detail={onlineCount ? 'Ready for selection' : 'Awaiting heartbeats'} icon={Activity} accent="green" />
        <StatCard label="Eligible clients" value={approvedCount} detail="Approved for jobs" icon={ShieldCheck} accent="amber" />
        <StatCard label="Pending approval" value={pendingCount} detail={pendingCount ? 'Action required' : 'None waiting'} icon={Cpu} accent="blue" />
      </div>
      <section className="content-grid">
        <div className="panel panel-wide">
          <div className="panel-heading"><div><p className="eyebrow">Federation map</p><h3>Client readiness</h3></div><button className="text-button" onClick={() => onNavigate('clients')}>Manage clients <span>→</span></button></div>
          <div className="readiness-list">
            {clients.length === 0
              ? <EmptyState icon={Boxes} title="No clients registered" copy="Clients appear here after they request access." />
              : clients.slice(0, 6).map(c => <ClientRow key={c.id} client={c} />)}
          </div>
        </div>
        <div className="panel privacy-panel">
          <div className="privacy-icon"><KeyRound size={18} /></div>
          <p className="eyebrow">Data boundary</p>
          <h3>Raw data stays local</h3>
          <p>Only approved model updates and metrics cross the federation boundary. Client credentials never enter the browser.</p>
          <div className="boundary-line"><span /><span /><span /><strong>NVFlare</strong><span /><span /><span /></div>
          <div className="privacy-footer"><ShieldCheck size={14} /> Isolation is a deployment responsibility</div>
        </div>
      </section>
    </>
  );
}

function Clients({ clients, loading, onCreate, onChange, onRefresh }) {
  return (
    <section>
      <div className="section-toolbar">
        <div><p className="eyebrow">Client registry</p><p className="section-copy">Remote participants enroll here before they can join a run.</p></div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="icon-button" onClick={onRefresh}><RefreshCw size={17} /></button>
          <button className="primary-button" onClick={onCreate}><Plus size={17} /> Add client</button>
        </div>
      </div>
      <div className="panel table-panel">
        <div className="table-head"><span>Client</span><span>Mode</span><span>Status</span><span>Last heartbeat</span><span>Actions</span></div>
        {loading
          ? <div className="loading-row"><RefreshCw size={16} className="spin" /> Loading registry…</div>
          : clients.length === 0
            ? <EmptyState icon={Boxes} title="Registry is empty" copy="Clients appear here after they request access from the portal." />
            : clients.map(c => <ClientTableRow key={c.id} client={c} onChange={onChange} />)}
      </div>
    </section>
  );
}

function ClientTableRow({ client, onChange }) {
  const [busy, setBusy] = useState(false);
  async function act(action) {
    setBusy(true);
    await onChange(client.id, action);
    setBusy(false);
  }
  const canApprove = client.status === 'PENDING';
  const canProvision = client.status === 'APPROVED' && !client.nvflare_identity;
  const canKit = Boolean(client.nvflare_identity) || ['APPROVED', 'READY', 'PROVISIONED', 'PROVISIONING', 'ONLINE', 'OFFLINE'].includes(client.status);
  const canDisable = ['APPROVED', 'ONLINE', 'OFFLINE'].includes(client.status);
  const canEnable = client.status === 'DISABLED';

  return (
    <div className="table-row">
      <div className="client-identity">
        <div className="client-avatar">{client.id.slice(0, 2).toUpperCase()}</div>
        <div><strong>{client.display_name}</strong><span>{client.id}</span></div>
      </div>
      <div><span className="mode-label">{client.mode === 'remote_participant' ? 'Remote' : 'Managed'}</span></div>
      <div><StatusBadge status={client.status} /></div>
      <div className="muted-cell">{client.last_heartbeat ? new Date(client.last_heartbeat).toLocaleString() : '—'}</div>
      <div className="row-actions">
        {canApprove && <button className="small-button approve" disabled={busy} onClick={() => act('approve')}><Check size={14} /> Approve</button>}
        {canProvision && <button className="small-button" disabled={busy} onClick={() => act('provision')}><KeyRound size={14} /> Provision kit</button>}
        {canKit && <button className="small-button" disabled={busy} onClick={() => act('kit')} title="Download client kit zip with start.sh to share with participant"><Download size={14} /> Download kit</button>}
        {canEnable && <button className="small-button" disabled={busy} onClick={() => act('enable')}><CheckCircle2 size={14} /> Enable</button>}
        {canDisable && <button className="small-button danger" disabled={busy} onClick={() => act('disable')}><X size={14} /> Disable</button>}
        <button className="icon-button subtle" disabled={busy} onClick={() => act('remove')}><Trash2 size={15} /></button>
      </div>
    </div>
  );
}

function ClientRow({ client }) {
  return (
    <div className="readiness-row">
      <div className="client-avatar">{client.id.slice(0, 2).toUpperCase()}</div>
      <div className="readiness-name"><strong>{client.display_name}</strong><span>{client.id}</span></div>
      <StatusBadge status={client.status} />
      <span className="readiness-time">{client.last_heartbeat ? new Date(client.last_heartbeat).toLocaleTimeString() : 'No heartbeat'}</span>
    </div>
  );
}

function CreateClientModal({ onClose, onCreate }) {
  const [form, setForm] = useState({ id: '', display_name: '', mode: 'remote_participant', dataset_ref: '', endpoint: '' });
  const set = k => e => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-heading"><div><p className="eyebrow">Client enrollment</p><h2>Add participant</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>
        <p className="modal-copy">Create a registry record. The client will receive their NVFlare identity after provisioning.</p>
        <form onSubmit={e => { e.preventDefault(); onCreate({ ...form, dataset_ref: form.dataset_ref || null, endpoint: form.endpoint || null }); }}>
          <label>Client ID<input required pattern="[a-z][a-z0-9-]{2,62}" placeholder="remote-partner1" value={form.id} onChange={set('id')} /></label>
          <label>Display name<input required placeholder="Research partner" value={form.display_name} onChange={set('display_name')} /></label>
          <label>Mode<select value={form.mode} onChange={set('mode')}><option value="remote_participant">Remote participant</option><option value="managed_kubernetes">Managed local</option></select></label>
          <label>Dataset reference <span className="field-hint">optional label, never raw data</span><input placeholder="partner-dataset" value={form.dataset_ref} onChange={set('dataset_ref')} /></label>
          <label>Endpoint <span className="field-hint">optional private-network address</span><input placeholder="100.x.x.x" value={form.endpoint} onChange={set('endpoint')} /></label>
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit"><Plus size={17} /> Create pending client</button></div>
        </form>
      </div>
    </div>
  );
}

function StatusBadge({ status }) { return <span className={`status-badge ${status?.toLowerCase()}`}><span className="status-dot" />{status?.toLowerCase()}</span>; }
function StatCard({ label, value, detail, icon: Icon, accent }) { return <div className={`stat-card ${accent}`}><div className="stat-icon"><Icon size={18} /></div><span className="stat-label">{label}</span><strong>{value}</strong><span className="stat-detail">{detail}</span></div>; }
function EmptyState({ icon: Icon, title, copy }) { return <div className="empty-state"><Icon size={25} /><strong>{title}</strong><span>{copy}</span></div>; }

createRoot(document.getElementById('root')).render(<App />);
