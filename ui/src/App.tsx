import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertCircle, Archive, Bell, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Clock3, Code2, Columns2, Copy, Download, Folder, Grid2X2, History, Menu, Moon, MoreHorizontal, PanelLeft, Play, Plus, RefreshCcw, RotateCcw, Save, Search, Settings, Sparkles, Sun, Trash2, Upload, X, Zap, GitBranch } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || '';
type Provider = { name: string; model?: string; status: string; latency_ms?: number };
type FileSymbol = { file: string; kind: string; name: string; signature: string; start_line: number };
type Repository = { id: string; name: string; python_files: number; symbols: FileSymbol[]; package_files?: string[] };
type TaskEvent = { level: string; phase: string; message: string; timestamp?: string };
type Task = { id: string; status: string; description?: string; phase?: string; iterations?: number; events: TaskEvent[]; plan: string[]; retrieved_context: FileSymbol[]; review: string; review_result?: { score: number; issues: string[]; suggestions: string[] }; diff: string; tests?: { passed?: number; failed?: number; errors?: number; skipped?: number; runtime_seconds?: number; output?: string; success?: boolean } };
type Theme = 'light' | 'dark';

function App() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('agent-theme') as Theme) || 'light');
  const [providers, setProviders] = useState<Provider[]>([]);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [prompt, setPrompt] = useState('');
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [view, setView] = useState<'diff' | 'original' | 'suggested'>('suggested');
  const [fileOriginal, setFileOriginal] = useState('');
  const [fileEdited, setFileEdited] = useState('');
  const [repositoryFiles, setRepositoryFiles] = useState<string[]>([]);
  const [loadingFile, setLoadingFile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [maxIterations, setMaxIterations] = useState(5);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [showParams, setShowParams] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const addFileInput = useRef<HTMLInputElement>(null);

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('agent-theme', theme); }, [theme]);
  useEffect(() => { const load = async () => { try { const response = await fetch(`${API_URL}/api/providers/status`); if (response.ok) setProviders(await response.json()); } catch { setNotice('Backend unavailable. You can still explore the workspace.'); } }; void load(); }, []);

  useEffect(() => {
    const loadTasks = async () => { try { const res = await fetch(`${API_URL}/api/tasks`); if (res.ok) setAllTasks(await res.json()); } catch {} };
    void loadTasks();
    const t = setInterval(loadTasks, 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!repository) { setRepositoryFiles([]); setActiveFile(null); return; }
    fetch(`${API_URL}/api/repositories/${repository.id}/files`).then(res => res.json()).then(data => {
      const files = data.files || [];
      setRepositoryFiles(files);
      if (files.length > 0 && !activeFile) setActiveFile(files[0]);
    }).catch(() => setRepositoryFiles([]));
  }, [repository, activeFile]);

  useEffect(() => {
    if (!repository || !activeFile) {
      setFileOriginal(''); setFileEdited('');
      return;
    }
    setLoadingFile(true);
    const fetchContent = async (isOriginal: boolean) => {
      try {
        const res = await fetch(`${API_URL}/api/repositories/${repository.id}/files/content?path=${encodeURIComponent(activeFile)}&original=${isOriginal}`);
        return res.ok ? (await res.json()).content || '' : '// Error loading file';
      } catch { return '// Network error'; }
    };
    void Promise.all([fetchContent(true), fetchContent(false)]).then(([orig, edit]) => {
      setFileOriginal(orig); setFileEdited(edit);
      setLoadingFile(false);
    });
  }, [repository, activeFile, task?.iterations]);

  useEffect(() => {
    if (!task || (task.status !== 'queued' && task.status !== 'running')) return;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/api/tasks/${task.id}`);
        if (response.ok) {
          setTask(await response.json());
        }
      } catch {}
    }, 2000);
    return () => clearInterval(timer);
  }, [task]);

  const uploadRepository = async (files: FileList | File[]) => {
    const selected = Array.from(files); if (!selected.length) return; setBusy(true); setNotice('');
    try { const isZip = selected.length === 1 && selected[0].name.toLowerCase().endsWith('.zip'); const form = new FormData(); if (isZip) form.append('file', selected[0]); else selected.forEach((file) => form.append('files', file)); const response = await fetch(`${API_URL}${isZip ? '/api/repositories/upload' : '/api/repositories/files'}`, { method: 'POST', body: form }); if (!response.ok) throw new Error('Upload failed'); const created = await response.json(); const summary = await fetch(`${API_URL}/api/repositories/${created.id}`); setRepository(summary.ok ? { ...(await summary.json()), id: created.id } : { id: created.id, name: selected[0].name, python_files: selected.length, symbols: [] }); setNotice('Repository uploaded and ready for analysis.'); } catch { setNotice('Could not reach the backend. Check that the API is running and try again.'); } finally { setBusy(false); }
  };
  
  const appendFiles = async (files: FileList | File[]) => {
    if (!repository) return;
    const selected = Array.from(files); if (!selected.length) return; setBusy(true); setNotice('');
    try {
      for (const file of selected) {
        const content = await file.text();
        await fetch(`${API_URL}/api/repositories/${repository.id}/files/content`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: file.name, content })
        });
        setRepositoryFiles(prev => Array.from(new Set([...prev, file.name])).sort());
      }
      setActiveFile(selected[0].name);
    } catch { setNotice('Could not add file.'); } finally { setBusy(false); }
  };
  const runAgent = async () => {
    if (!repository || prompt.trim().length < 5) return; setBusy(true); setNotice(''); setShowParams(false);
    try { 
      const targetPrompt = activeFile ? `[Target File: ${activeFile}]\n\n${prompt}` : prompt;
      const payload: any = { repository_id: repository.id, description: targetPrompt, max_iterations: maxIterations };
      if (selectedProvider !== 'auto') payload.provider = selectedProvider;
      const response = await fetch(`${API_URL}/api/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); 
      if (!response.ok) throw new Error('Task failed'); 
      setTask(await response.json()); 
      setNotice('Agent task started.'); 
    } catch { setNotice('The task could not be started. Upload a repository and check the backend connection.'); } finally { setBusy(false); }
  };
  
  const createNewFile = async () => {
    if (!repository) return;
    const name = window.prompt('Enter new filename (e.g. app/newfile.py):');
    if (!name) return;
    try {
      setBusy(true);
      await fetch(`${API_URL}/api/repositories/${repository.id}/files/content`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: name, content: '' }) });
      setRepositoryFiles(prev => Array.from(new Set([...prev, name])).sort());
      setActiveFile(name);
    } catch { setNotice('Could not create file.'); } finally { setBusy(false); }
  };

  const runPytest = async () => {
    if (!task) return; setTesting(true); setTestResult(null);
    try {
      const res = await fetch(`${API_URL}/api/tasks/${task.id}/tests`, { method: 'POST' });
      if (res.ok) setTestResult(await res.json()); else setNotice('Test run failed.');
    } catch { setNotice('Test run failed to connect.'); } finally { setTesting(false); }
  };
  const statusLabel = task?.status?.replace(/_/g, ' ') || 'Ready';

  return <div className="app-shell">
    <header className="topbar"><div className="brand-group"><button className="icon-button mobile-only" aria-label="Open menu" onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><div className="brand-mark"><Sparkles size={25} /></div><div><strong>Agentic</strong><span>Software Engineer</span></div></div><div className="top-actions"><button className="icon-button" aria-label="Theme" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}</button><button className="new-project" onClick={() => fileInput.current?.click()}><Plus size={17} /> New Project</button></div></header>
    <div className="layout">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="side-section">
          <div className="section-title">Select Agent Model</div>
          <div style={{ padding: '0 12px 12px' }}>
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              style={{
                width: '100%',
                padding: '6px',
                borderRadius: '6px',
                border: '1px solid var(--line)',
                background: 'var(--bg)',
                color: 'var(--ink)',
                fontSize: '12px',
                cursor: 'pointer'
              }}
            >
              <option value="auto">Auto (Best Available)</option>
              <option value="mistral">Mistral (codestral)</option>
              <option value="huggingface">Hugging Face (Qwen2.5)</option>
              <option value="groq">Groq (gpt-oss-120b)</option>
              <option value="gemini">Gemini (3.5-flash)</option>
            </select>
          </div>
        </div>
        <div className="side-section repositories">
          <div className="section-title">User Repositories <Plus size={16} style={{cursor: 'pointer'}} onClick={() => addFileInput.current?.click()} /><ChevronDown size={15} /></div>
          {repositoryFiles.map((file) => <button className="repo-file" key={file} onClick={() => setActiveFile(file)}><Folder size={15} />{file.split('/').pop()}</button>)}
        </div>
      </aside>
      <main className="main-content"><div className="content-header"><div><p className="eyebrow">Workspace / {repository?.name || 'New repository'}</p><h1>Build with confidence.</h1></div><div className="header-status"><span className="status-dot" /> {statusLabel}</div></div>{notice && <div className="notice"><AlertCircle size={16} />{notice}<button onClick={() => setNotice('')}><X size={15} /></button></div>}
        <section className="card upload-card"><div className="card-title"><span>Upload Code</span><div><button className="plain-button" onClick={() => addFileInput.current?.click()}><Plus size={16} /></button><button className="plain-button" onClick={() => fileInput.current?.click()}><RotateCcw size={16} /></button><button className="plain-button" onClick={() => { setRepository(null); setRepositoryFiles([]); setActiveFile(null); }}><Trash2 size={16} /></button></div></div>
        {!repository ? (
          <div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void uploadRepository(event.dataTransfer.files); }} onClick={() => fileInput.current?.click()}><div className="upload-icon"><Upload size={24} /></div><strong>Drag & drop your files or repository</strong><span>or <b>click to upload</b> (.zip, .py, .js, .cpp)</span><small>Safe analysis in a temporary workspace</small></div>
        ) : (
          <div className="drop-zone" style={{border: 'none', background: 'var(--panel-soft)', cursor: 'default'}}><div className="upload-icon" style={{color: 'var(--green)'}}><Check size={24} /></div><strong>{repository.name}</strong><span>{repositoryFiles.length} files uploaded</span><small>Workspace ready for analysis</small></div>
        )}
        <div className="update-line"><span>Recent updates: <b>{activeFile || 'None'}</b></span><span>Project status: <em>{repository ? 'Ready to run' : 'Awaiting upload'}</em></span></div>
        <input ref={fileInput} className="hidden-input" type="file" accept=".zip,.py,.js,.cpp,.txt,.json,.md" multiple onChange={(event) => { if (event.target.files) void uploadRepository(event.target.files); }} />
        <input ref={addFileInput} className="hidden-input" type="file" accept=".py,.js,.cpp,.txt,.json,.md" multiple onChange={(event) => { if (event.target.files) void appendFiles(event.target.files); }} />
        </section>
        <section className="card prompt-card"><div className="card-title"><div style={{display: 'flex', alignItems: 'center', gap: '8px'}}><span>Agent Prompt</span>{activeFile && <span style={{fontSize: '10px', background: 'var(--blue)', color: '#fff', padding: '2px 6px', borderRadius: '4px'}}>Targeting: {activeFile.split('/').pop()}</span>}</div><span className="prompt-hint">Describe the outcome you want</span></div><div className="prompt-row"><input value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={activeFile ? `Describe what you want to change in ${activeFile.split('/').pop()}...` : "Implement JWT authentication..."} onKeyDown={(event) => { if (event.key === 'Enter') void runAgent(); }} /><button className="primary-button" disabled={!repository || prompt.trim().length < 5 || busy} onClick={() => void runAgent()}><Sparkles size={16} />{busy ? 'Working...' : 'Generate Code'}</button><div style={{position: 'relative'}}><button className="secondary-button" onClick={() => setShowParams(!showParams)}><Settings size={16} /> Params</button>{showParams && <div style={{position: 'absolute', bottom: '100%', right: 0, marginBottom: '5px', padding: '10px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: '8px', boxShadow: 'var(--shadow)', zIndex: 50, display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', whiteSpace: 'nowrap'}}>Max Iterations: <input type="number" min={1} max={10} value={maxIterations} onChange={e => setMaxIterations(Number(e.target.value))} style={{width: '40px', padding: '4px', border: '1px solid var(--line)', borderRadius: '4px', background: 'var(--bg)', color: 'var(--ink)'}} /></div>}</div></div>
        </section>
        <section className="card editor-card"><div className="editor-toolbar"><div className="card-title"><span>Split-screen code editor & diff view</span><Columns2 size={16} /></div><div className="file-tabs">{repositoryFiles.map(file => <button key={file} className={activeFile === file ? 'selected' : ''} onClick={() => setActiveFile(file)}>{file.split('/').pop()}</button>)}</div></div><div className="view-switcher"><button className={view === 'original' ? 'selected' : ''} onClick={() => setView('original')}>Original</button><button className={view === 'suggested' ? 'selected' : ''} onClick={() => setView('suggested')}>Side-by-Side Diff</button><button className={view === 'diff' ? 'selected' : ''} onClick={() => setView('diff')}>Raw Patch</button></div><div className="editor-grid">
          {loadingFile || task?.status === 'running' ? <div className="loading-state"><RefreshCcw className="spinner" size={24} /><span>{task?.status === 'running' ? 'Agent is generating code...' : 'Loading...'}</span></div> : <>
            {view === 'original' && <CodePane title={`${activeFile || 'No file'} [Original]`} code={fileOriginal} />}
            {view === 'suggested' && <><CodePane title={`${activeFile || 'No file'} [Original]`} code={fileOriginal} muted={true} /><div className="splitter"><ChevronLeft size={14} /><span /><ChevronRight size={14} /></div><CodePane title={`${activeFile || 'No file'} [Edited]`} code={fileEdited} actions={testResult?.success ? <div style={{display: 'flex', gap: '8px', marginRight: '8px'}}>
              <button className="plain-button" style={{height: 'auto', gap: '4px', display: 'flex', color: 'var(--muted)', fontSize: '10px'}} onClick={() => { void navigator.clipboard.writeText(fileEdited); setNotice('Code copied to clipboard'); }}><Copy size={12} /> Copy</button>
              <button className="plain-button" style={{height: 'auto', gap: '4px', display: 'flex', color: 'var(--muted)', fontSize: '10px'}} onClick={() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([fileEdited], { type: 'text/plain' })); a.download = activeFile ? activeFile.split('/').pop()! : 'edited.py'; a.click(); }}><Download size={12} /> Download</button>
            </div> : null} /></>}
            {view === 'diff' && <div className="code-pane suggested"><div className="pane-title">Raw Patch View 
              <button className="plain-button" style={{height: 'auto', gap: '4px', display: 'flex', color: 'var(--muted)', fontSize: '10px'}} onClick={() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([task?.diff || ''], { type: 'text/plain' })); a.download = 'patch.diff'; a.click(); }}><Download size={12} /> Download Patch</button>
            </div><textarea value={task?.diff || 'No diff available'} readOnly spellCheck={false} /></div>}
          </>}
        </div></section>
        <section className="lower-grid"><div className="card plan-card"><div className="card-title"><span>Agent plan</span><span className="plan-count">{task?.plan?.length || 0} steps</span></div>{(task?.plan || []).map((step, index) => <div className="plan-row" key={step}><span>{String(index + 1).padStart(2, '0')}</span><p>{step}</p><Check size={15} /></div>)}</div><div className="card review-card"><div className="card-title"><span>Review score</span><History size={16} /></div><div className="score"><strong>{task?.review_result?.score ?? '--'}</strong><span>/10</span></div><p>{task?.review || 'Run an agent task to receive an evidence-based review of the proposed changes.'}</p><button className="secondary-button full-width" disabled={!task || testing} onClick={runPytest}><Play size={15} /> {testing ? 'Running Pytest...' : 'Run pytest in sandbox'}</button>{testResult && <div style={{marginTop: '10px', fontSize: '11px', color: 'var(--muted)', background: 'var(--code)', padding: '8px', borderRadius: '4px', overflowX: 'auto'}}>{testResult.success ? '✅ Tests Passed' : '❌ Tests Failed'} - {testResult.passed} passed, {testResult.failed} failed. {testResult.output ? <pre style={{marginTop: '4px', color: testResult.success ? 'var(--green)' : 'red'}}>{testResult.output.substring(0, 500)}{testResult.output.length > 500 ? '...' : ''}</pre> : null}</div>}</div></section>
      </main>
      <aside className="timeline-panel"><div className="panel-heading"><span>Activity Timeline</span><button className="plain-button"><MoreHorizontal size={17} /></button></div><div className="timeline">{(task?.events || []).map((event, index) => <div className="timeline-item" key={`${event.message}-${index}`}><div className={`timeline-node ${event.level}`}><Sparkles size={13} /></div><div className="timeline-event"><div className="event-meta"><span>{event.timestamp || 'Now'}</span><span>{event.phase}</span></div><strong>{event.message}</strong><span className="event-detail"><i />{event.phase === 'User' ? 'Code uploaded' : event.message}</span><span className="event-detail"><Clock3 size={12} />{event.timestamp || 'Live update'}</span></div></div>)}</div></aside>
    </div></div>;
}

function CodePane({ title, code, muted, actions }: { title: string; code: string; muted?: boolean; actions?: React.ReactNode }) { return <div className={`code-pane ${muted ? 'muted' : ''}`}><div className="pane-title">{title}<span style={{marginLeft: 'auto', display: 'flex', gap: '8px'}}>{actions}</span><span><Code2 size={14} /> Python</span></div><pre>{code.split('\n').map((line, index) => <code key={`${index}-${line}`} className={line.includes('return') || line.includes('auth') ? 'highlight-line' : ''}><b>{String(index + 20).padStart(2, ' ')}</b>{line}</code>)}</pre></div>; }

export default App;
