import React, { useState } from 'react';
import { label } from '../data.js';
import { Badge } from './ui.jsx';

export function UploadPanel({ run, busy, onPayments, onDisputes }) {
  const [files, setFiles] = useState({});
  const [disputeFile, setDisputeFile] = useState(null);
  return <section className="upload-panel">
    <div className="upload-step">
      <div className="section-heading"><div><span className="eyebrow">Payment files</span><h2>Start a scoring run</h2></div><Badge>{run.run_id ? 'Run available' : 'Ready to upload'}</Badge></div>
      <p className="muted">Upload matching invoice, photo, and payment CSVs.</p>
      <form onSubmit={(event) => { event.preventDefault(); onPayments(files); }}>
        <div className="file-grid">{['invoices', 'photos', 'payments'].map((name) => <label className="file-field" key={name}><span>{label(name)}.csv</span><input type="file" accept=".csv,text/csv" required disabled={!!busy} onChange={(event) => setFiles({ ...files, [name]: event.target.files[0] })} /></label>)}</div>
        <button className="primary" disabled={!!busy || !files.invoices || !files.photos || !files.payments}>{busy === 'payments' ? 'Scoring payments…' : run.run_id ? 'Score a new run' : 'Score payments'} <span aria-hidden="true">→</span></button>
        {run.run_id && <p className="footnote">A new run replaces the current run shown here.</p>}
      </form>
    </div>
    <div className={`upload-step second ${run.run_id ? '' : 'inactive'}`}>
      <span className="eyebrow">Dispute file</span><h2>Add disputes when received</h2>
      <p className="muted">Use disputes linked to the payments in this run. Outcomes can be blank.</p>
      <form onSubmit={(event) => { event.preventDefault(); onDisputes(disputeFile); }}>
        <label className="file-field"><span>disputes.csv</span><input type="file" accept=".csv,text/csv" required disabled={!run.run_id || !!busy} onChange={(event) => setDisputeFile(event.target.files[0])} /></label>
        <button className="secondary" disabled={!run.run_id || !!busy || !disputeFile}>{busy === 'disputes' ? 'Scoring disputes…' : 'Score disputes'} <span aria-hidden="true">→</span></button>
      </form>
    </div>
  </section>;
}

