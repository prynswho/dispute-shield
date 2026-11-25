import React from 'react';
import { exportUrl } from '../api.js';
import { Empty } from '../components/ui.jsx';
import { DisputeTable } from '../components/PredictionTables.jsx';

export function Disputes({ run }) {
  return <section className="panel"><div className="section-heading"><div><h2>Dispute decisions</h2><p className="muted">Win estimates based on the evidence submitted.</p></div>{run.disputes.length > 0 && <a className="download" href={exportUrl(run.run_id, 'dispute')}>Download CSV <span aria-hidden="true">↓</span></a>}</div>{run.disputes.length ? <DisputeTable disputes={run.disputes} /> : <Empty title="Ready when a dispute arrives">Score payments first, then upload the linked dispute file.</Empty>}</section>;
}
