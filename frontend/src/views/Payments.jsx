import React, { useState } from 'react';
import { exportUrl } from '../api.js';
import { filterPayments, label } from '../data.js';
import { Empty } from '../components/ui.jsx';
import { PaymentTable } from '../components/PredictionTables.jsx';

export function Payments({ run, selected, onSelect }) {
  const [tier, setTier] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const visiblePayments = filterPayments(run.payments, '', tier, query);
  return <section className="panel"><div className="section-heading"><div><h2>Payment exposure</h2><p className="muted">Scores and evidence actions for the current upload.</p></div>{run.run_id && <a className="download" href={exportUrl(run.run_id, 'payment')}>Download CSV <span aria-hidden="true">↓</span></a>}</div>
        {run.payments.length ? <><div className="filters"><input type="search" aria-label="Search payments" placeholder="Search payment, invoice, or team ID" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} /><select aria-label="Filter by risk tier" value={tier} onChange={(event) => { setTier(event.target.value); setPage(0); }}><option value="">All risk tiers</option>{['high', 'medium', 'low'].map((value) => <option value={value} key={value}>{label(value)} risk</option>)}<option value="unscored">Unscored</option></select><span className="muted">{visiblePayments.length.toLocaleString()} payments</span></div>{visiblePayments.length ? <PaymentTable payments={visiblePayments.slice(page * 100, (page + 1) * 100)} onSelect={onSelect} selected={selected?.payment_id} /> : <Empty title="No matching payments">Try a different search or risk tier.</Empty>}{visiblePayments.length > 100 && <div className="pagination"><button className="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1} of {Math.ceil(visiblePayments.length / 100)}</span><button className="secondary" disabled={(page + 1) * 100 >= visiblePayments.length} onClick={() => setPage(page + 1)}>Next</button></div>}</> : <Empty title="Your payment review starts here">Upload the three payment files to see risk tiers, win probabilities, and recommended actions.</Empty>}
      </section>;
}
