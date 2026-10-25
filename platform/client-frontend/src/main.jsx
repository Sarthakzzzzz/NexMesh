import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, CheckCircle2, Copy, Download, Eye, EyeOff, LockKeyhole, Send, ShieldCheck, Terminal, XCircle } from 'lucide-react';
import './styles.css';

const API_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' && window.location.hostname ? `http://${window.location.hostname}:8000` : 'http://127.0.0.1:8000');
const saved = JSON.parse(localStorage.getItem('nexmesh-client') || 'null');

async function api(path, options = {}) {
  const r = await fetch(`${API_URL}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

function App() {
  const [identity, setIdentity] = useState(saved);
  const [client, setClient] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(saved));
  const [dataPath, setDataPath] = useState(localStorage.getItem('nexmesh-data-path') || '');

  async function refresh() {
    if (!identity) return;
    setLoading(true);
    try {
      const headers = { 'X-Nexmesh-Client-Token': identity.client_token };
      const [status, assigned] = await Promise.all([
        api(`/agent/${identity.client_id}/status`, { headers }),
        api(`/agent/${identity.client_id}/jobs`, { headers }),
      ]);
      setClient(status); setJobs(assigned); setError('');
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, [identity]);
  useEffect(() => {
    if (!identity) return;
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [identity]);

  async function requestConnection(form) {
    try {
      const result = await api('/client-requests', { method: 'POST', body: JSON.stringify(form) });
      const next = { client_id: result.client_id, client_token: result.client_token };
      localStorage.setItem('nexmesh-client', JSON.stringify(next));
      setIdentity(next); setError('');
    } catch (e) { setError(e.message); }
  }

  function saveDataPath(p) { setDataPath(p); localStorage.setItem('nexmesh-data-path', p); }
  async function forget() {
    if (!confirm('Leave federation and delete client enrollment from coordinator?')) return;
    try {
      if (identity) {
        await api(`/agent/${identity.client_id}/leave`, {
          method: 'POST',
          headers: { 'X-Nexmesh-Client-Token': identity.client_token },
        });
      }
    } catch (e) {
      console.warn('Failed to notify coordinator of leave:', e);
    }
    localStorage.removeItem('nexmesh-client');
    localStorage.removeItem('nexmesh-data-path');
    setIdentity(null);
    setClient(null);
    setJobs([]);
  }

  if (!identity) return <RequestAccess onSubmit={requestConnection} error={error} />;

  const approved = ['APPROVED', 'PROVISIONING', 'READY', 'ONLINE', 'OFFLINE'].includes(client?.status);
  const provisioned = Boolean(client?.nvflare_identity || ['APPROVED', 'PROVISIONING', 'READY', 'ONLINE', 'OFFLINE'].includes(client?.status));
  const kitUrl = `${API_URL}/agent/${identity.client_id}/kit`;

  const agentCmd = [
    `python agent.py`,
    `  --coordinator ${API_URL}`,
    `  --client-id ${identity.client_id}`,
    `  --token ${identity.client_token}`,
    `  --kit-dir ./nvflare-kit`,
    `  --data-path ${dataPath || '/path/to/your/dataset.pt'}`,
  ].join(' \\\n');

  return (
    <main className="portal">
      <header className="portal-header">
        <div className="logo">NX</div>
        <div><p className="kicker">NexMesh participant</p><h1>Client portal</h1></div>
        <button className="quiet-button" onClick={forget}>Leave Federation</button>
      </header>

      <section className="identity-banner">
        <div>
          <p className="kicker">Your enrollment</p>
          <h2>{client?.display_name || identity.client_id}</h2>
          <span className="identity-id">{identity.client_id}</span>
        </div>
        <Status status={client?.status || 'CONNECTING'} />
        <button className="refresh" onClick={refresh} disabled={loading}>{loading ? 'Checking…' : 'Refresh'}</button>
      </section>

      {error && <div className="error"><XCircle size={16} />{error}</div>}

      <section className="portal-grid">
        <div className="panel">
          <div className="panel-title"><div><p className="kicker">Approval</p><h3>Connection state</h3></div><ShieldCheck size={19} /></div>
          <div className="timeline">
            <Step label="Request sent" active />
            <Step label="Coordinator approval" active={approved} />
            <Step label="Kit provisioned" active={!!provisioned} />
            <Step label="Agent running" active={client?.status === 'ONLINE'} />
          </div>
          <p className="muted">Refreshes automatically every 15 seconds.</p>
        </div>
        <div className="panel privacy">
          <LockKeyhole size={20} />
          <p className="kicker">Data boundary</p>
          <h3>Your data stays here</h3>
          <p>Only model weight updates leave this machine. The coordinator never receives your raw dataset.</p>
        </div>
      </section>

      {approved && (
        <section className="panel agent-setup">
          <div className="panel-title"><div><p className="kicker">One-time setup</p><h3>Run the agent on your machine</h3></div><Terminal size={19} /></div>
          <p className="muted">The agent connects to the NVFlare server and handles training automatically. No NVFlare knowledge needed.</p>

          <label className="data-path-label">
            Your dataset path
            <input placeholder="/home/you/data/mnist.pt" value={dataPath} onChange={e => saveDataPath(e.target.value)} />
          </label>

          <div className="steps-list">
            <AgentStep n={1} label="Download your client kit package">
              {provisioned
                ? <KitDownload kitUrl={kitUrl} clientToken={identity.client_token} clientId={identity.client_id} />
                : <p className="muted waiting">⏳ Waiting for the host to approve your client…</p>}
              <p className="muted" style={{ marginTop: '6px' }}>The zip includes <code>start.sh</code>, <code>agent.py</code>, <code>requirements.txt</code>, and your signed certificates.</p>
            </AgentStep>

            <AgentStep n={2} label="Unzip the kit">
              <CodeBlock code={`unzip ${identity.client_id}-kit.zip -d ./client-kit`} />
            </AgentStep>

            <AgentStep n={3} label="Run the client agent (One Click / Command)">
              <div style={{ marginBottom: '8px' }}>
                <span className="kicker" style={{ fontSize: '11px', fontWeight: 600 }}>Windows (Command Prompt or Double-Click):</span>
                <CodeBlock code={`cd client-kit\nstart.bat`} />
              </div>
              <div>
                <span className="kicker" style={{ fontSize: '11px', fontWeight: 600 }}>Linux / macOS / WSL / Git Bash:</span>
                <CodeBlock code={`cd ./client-kit\nbash start.sh ${dataPath ? dataPath : ''}`} />
              </div>
              <p className="muted" style={{ marginTop: '8px' }}>Automatically sets up Python virtualenv, installs requirements, detects your GPU/CPU, and connects.</p>
            </AgentStep>
          </div>

          <TokenReveal token={identity.client_token} />

          <div className="agent-note"><CheckCircle2 size={15} /> Once running, the agent connects to the NVFlare server and trains automatically when a job is dispatched.</div>
        </section>
      )}

      <section className="jobs">
        <div className="section-title">
          <div><p className="kicker">Assigned work</p><h2>Training jobs</h2></div>
          <span className="job-count">{jobs.length} assigned</span>
        </div>
        {jobs.length === 0
          ? <div className="empty panel"><Activity size={22} /><strong>No assigned jobs yet</strong><span>Jobs appear here when the host assigns this client to a run.</span></div>
          : jobs.map(job => <JobCard key={job.id} job={job} />)}
      </section>
    </main>
  );
}

function TokenReveal({ token }) {
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);
  function copy() { navigator.clipboard.writeText(token); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  return (
    <div className="token-reveal">
      <span className="kicker">Your client token</span>
      <div className="token-row">
        <code>{show ? token : '•'.repeat(32)}</code>
        <button className="icon-btn" onClick={() => setShow(s => !s)}>{show ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        <button className="icon-btn" onClick={copy}>{copied ? <CheckCircle2 size={14} /> : <Copy size={14} />}</button>
      </div>
      <p className="muted">Save this token — it's already pre-filled in the agent command above.</p>
    </div>
  );
}

function KitDownload({ kitUrl, clientToken, clientId }) {
  const [state, setState] = useState('idle');
  async function download() {
    setState('downloading');
    try {
      const r = await fetch(kitUrl, { headers: { 'X-Nexmesh-Client-Token': clientToken } });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Error ${r.status}`);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(await r.blob());
      a.download = `${clientId}-kit.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setState('done');
    } catch (e) { setState('error:' + e.message); }
  }
  if (state === 'downloading') return <span className="muted">Downloading kit package…</span>;
  if (state === 'done') return <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}><span className="muted" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}><CheckCircle2 size={15} color="#10b981" /> Kit downloaded.</span><button className="package-link btn" onClick={download}><Download size={14} /> Re-download</button></div>;
  if (state.startsWith('error:')) return <span className="error-inline">{state.slice(6)}</span>;
  return <button className="package-link btn" style={{ padding: '8px 16px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '8px' }} onClick={download}><Download size={16} /> Download Client Kit (.zip)</button>;
}

function AgentStep({ n, label, children }) {
  return (
    <div className="agent-step">
      <span className="step-num">{n}</span>
      <div><strong>{label}</strong>{children}</div>
    </div>
  );
}

function CodeBlock({ code }) {
  const [copied, setCopied] = useState(false);
  function copy() { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  return (
    <div className="code-block">
      <pre>{code}</pre>
      <button className="copy-btn" onClick={copy}>{copied ? <CheckCircle2 size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}</button>
    </div>
  );
}

function JobCard({ job }) {
  return (
    <article className="job-card panel">
      <div className="job-head">
        <div><p className="kicker">{job.id}</p><h3>{job.name || 'Federated training job'}</h3></div>
        <Status status={job.status} />
      </div>
      {job.requirements && <p className="requirements">{job.requirements}</p>}
      {job.result
        ? <div className="result-box"><CheckCircle2 size={15} /><pre>{JSON.stringify(job.result, null, 2)}</pre></div>
        : <p className="muted">The agent will train and submit results automatically.</p>}
    </article>
  );
}

function RequestAccess({ onSubmit, error }) {
  const [form, setForm] = useState({ display_name: '', endpoint: '' });
  return (
    <main className="request-shell">
      <div className="request-card">
        <div className="logo">NX</div>
        <p className="kicker">NexMesh participant</p>
        <h1>Request access to a federation</h1>
        <p className="intro">Send your identity to the coordinator. Approval is required before any job is assigned to you.</p>
        {error && <div className="error"><XCircle size={16} />{error}</div>}
        <form onSubmit={e => { e.preventDefault(); onSubmit({ ...form, endpoint: form.endpoint || null }); }}>
          <label>Your name or organisation<input required placeholder="Research partner" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} /></label>
          <label>Private endpoint <span>optional</span><input placeholder="100.x.x.x" value={form.endpoint} onChange={e => setForm({ ...form, endpoint: e.target.value })} /></label>
          <button className="submit" type="submit"><Send size={16} /> Send connection request</button>
        </form>
        <div className="security-note"><LockKeyhole size={15} /> Your token is stored only in this browser.</div>
      </div>
    </main>
  );
}

function Step({ label, active }) {
  return (
    <div className={active ? 'step active' : 'step'}>
      <span>{active ? <CheckCircle2 size={16} /> : <span className="step-dot" />}</span>
      <strong>{label}</strong>
    </div>
  );
}

function Status({ status }) {
  return <span className={`status ${status?.toLowerCase()}`}><span />{status?.toLowerCase()}</span>;
}

createRoot(document.getElementById('root')).render(<App />);
