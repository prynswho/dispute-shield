import React, { useEffect, useState } from 'react';
import { loadPortfolio, loadRun, uploadDisputes, uploadPayments } from './api.js';
import { money, summarizePayments } from './data.js';
import { Metric } from './components/ui.jsx';
import { PaymentDetail } from './components/PaymentDetail.jsx';
import { UploadPanel } from './components/UploadPanel.jsx';
import { Portfolio } from './views/Portfolio.jsx';
import { Payments } from './views/Payments.jsx';
import { Disputes } from './views/Disputes.jsx';
import { Teams } from './views/Teams.jsx';
import { WhatIf } from './views/WhatIf.jsx';
import './styles.css';

const tabs = ['Payments', 'Disputes', 'Teams', 'Portfolio', 'What-if'];
const emptyRun = { run_id: '', payments: [], disputes: [] };

export default function App() {
  const [run, setRun] = useState(emptyRun);
  const [portfolio, setPortfolio] = useState({ reasons: [], teams: [] });
  const [portfolioError, setPortfolioError] = useState('');
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [tab, setTab] = useState('Payments');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showUpload, setShowUpload] = useState(true);
  const [team, setTeam] = useState('');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let active = true;
    loadPortfolio().then((data) => { if (active) setPortfolio({ reasons: data.reasons ?? [], teams: data.teams ?? [] }); })
      .catch((failure) => { if (active) setPortfolioError(failure.message); })
      .finally(() => { if (active) setPortfolioLoading(false); });
    const id = localStorage.getItem('dispute-shield-run');
    if (id) {
      setBusy('restore');
      loadRun(id).then((data) => {
        if (active) { setRun({ ...emptyRun, ...data }); setShowUpload(false); }
      }).catch(() => { localStorage.removeItem('dispute-shield-run'); })
        .finally(() => { if (active) setBusy(''); });
    }
    return () => { active = false; };
  }, []);

  async function handlePayments(files) {
    setBusy('payments'); setError(''); setNotice('');
    try {
      const data = await uploadPayments(files);
      setRun({ ...emptyRun, ...data });
      localStorage.setItem('dispute-shield-run', data.run_id);
      setSelected(null); setTeam(''); setTab('Payments');
      const unscored = data.payments.filter((payment) => payment.dispute_risk_tier == null).length;
      const scored = data.payments.length - unscored;
      const note = unscored ? ` Unscored due to missing invoice links (${unscored.toLocaleString()}).` : '';
      setNotice(`Scored ${scored.toLocaleString()} payments.${note} Payment predictions are ready to download.`);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(''); }
  }

  async function handleDisputes(file) {
    setBusy('disputes'); setError(''); setNotice('');
    try {
      const data = await uploadDisputes(run.run_id, file);
      setRun((current) => ({ ...current, disputes: data.disputes ?? [] }));
      setTab('Disputes');
      setNotice(`Scored ${data.disputes.length.toLocaleString()} disputes. Dispute predictions are ready to download.`);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(''); }
  }

  const summary = summarizePayments(run.payments);
  const unscored = run.payments.filter((payment) => payment.dispute_risk_tier == null).length;
  const teamIds = [...new Set(run.payments.map((row) => row.team_id))];
  return <div className="app-shell">
    <header className="app-header"><a className="brand" href="/" aria-label="Dispute Shield home"><span className="brand-mark" aria-hidden="true">S</span><span>Dispute Shield<small>Payment protection</small></span></a>
      <div className="header-actions">{run.run_id && <span className="run-indicator"><span /> Active scoring run</span>}<button className="secondary" onClick={() => setShowUpload(!showUpload)} aria-expanded={showUpload}>{showUpload ? 'Close uploads' : 'Upload files'} <span aria-hidden="true">↑</span></button></div>
    </header>
    <main>
      <div className="page-heading"><div><h1>Payment and dispute review</h1></div>{run.run_id && <span className="muted">{teamIds.length} teams in this upload</span>}</div>
      {error && <div className="alert error" role="alert"><strong>Upload needs attention</strong><p>{error}</p><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
      {notice && <div className="alert success" role="status">{notice}</div>}
      {busy === 'restore' && <p className="status" role="status">Restoring the previous scoring run…</p>}
      {showUpload && <UploadPanel run={run} busy={busy} onPayments={handlePayments} onDisputes={handleDisputes} />}
      <div className="metrics"><Metric name="Payments scored" value={(run.payments.length - unscored).toLocaleString()} detail={unscored ? `${unscored.toLocaleString()} unscored` : undefined} /><Metric name="Payment volume" value={money(summary.amount)} /><Metric name="High risk payments" value={summary.high.toLocaleString()} /><Metric name="Expected loss" value={run.payments.length > unscored ? money(summary.exposure) : '—'} detail="Estimated across scored payments" /></div>
      <nav className="tabs" aria-label="Workspace views">{tabs.map((name) => <button key={name} className={tab === name ? 'active' : ''} aria-current={tab === name ? 'page' : undefined} onClick={() => setTab(name)}>{name}{name === 'Disputes' && run.disputes.length > 0 && <span>{run.disputes.length}</span>}</button>)}</nav>
      {tab === 'Payments' && <Payments key={run.run_id} run={run} selected={selected} onSelect={setSelected} />}
      {tab === 'Disputes' && <Disputes run={run} />}
      {tab === 'Teams' && <Teams run={run} portfolio={portfolio} selected={team} setSelected={setTeam} onPayment={setSelected} />}
      {tab === 'Portfolio' && <Portfolio portfolio={portfolio} loading={portfolioLoading} error={portfolioError} disputes={run.disputes} />}
      {tab === 'What-if' && <WhatIf />}
      <footer>Probabilities are estimates. Review the underlying invoice and evidence before taking action.</footer>
    </main>
    {selected && <div className="detail-backdrop" onClick={() => setSelected(null)}><div onClick={(event) => event.stopPropagation()}><PaymentDetail payment={selected} close={() => setSelected(null)} /></div></div>}
  </div>;
}
