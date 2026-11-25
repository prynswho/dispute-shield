import React from 'react';
import { probability, money, paymentActions } from '../data.js';
import { Empty, Metric, Badge } from '../components/ui.jsx';
import { PaymentTable, DisputeTable } from '../components/PredictionTables.jsx';

export function Teams({ run, portfolio, selected, setSelected, onPayment }) {
  const teams = [...new Set([...run.payments.map((row) => row.team_id), ...portfolio.teams.map((row) => row.team_id)])].sort();
  const payments = run.payments.filter((row) => row.team_id === selected);
  const disputes = run.disputes.filter((row) => row.team_id === selected);
  const history = portfolio.teams.find((row) => row.team_id === selected);
  const gaps = Object.entries(payments.reduce((counts, payment) => {
    for (const action of paymentActions(payment)) counts[action] = (counts[action] || 0) + 1;
    return counts;
  }, {})).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const historicalGaps = history?.gaps ?? [];
  return <div className="stack">
    <div className="team-picker"><label htmlFor="team-select">Team ID</label><select id="team-select" value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Choose a team</option>{teams.map((team) => <option key={team}>{team}</option>)}</select></div>
    {!selected ? <section className="panel"><Empty title="Explore a team">Choose a team to review its payments, disputes, and evidence gaps.</Empty></section> : <>
      <div className="metrics"><Metric name="Uploaded payments" value={payments.length} /><Metric name="Uploaded disputes" value={disputes.length} /><Metric name="Historical win rate" value={history && history.wins + history.losses ? probability(history.wins / (history.wins + history.losses)) : '—'} /><Metric name="Historical dollars lost" value={history ? money(history.usd_lost) : '—'} /></div>
      <section className="panel"><div className="section-heading"><h2>Main evidence gaps</h2></div>{gaps.length ? <ul className="gap-list">{gaps.map(([action, count]) => <li key={action}><span>{action}</span><Badge>{count} payments</Badge></li>)}</ul> : <p className="status">No gaps identified in uploaded payments for this team.</p>}</section>
      {historicalGaps.length > 0 && <section className="panel"><div className="section-heading"><h2>Historical invoice gaps</h2></div><ul className="gap-list">{historicalGaps.map((gap) => <li key={gap.label}><span>{gap.label}</span><Badge>{gap.count} invoices</Badge></li>)}</ul></section>}
      <section className="panel"><div className="section-heading"><h2>Payments</h2></div>{payments.length ? <PaymentTable payments={payments} onSelect={onPayment} /> : <p className="status">No uploaded payments for this team.</p>}</section>
      <section className="panel"><div className="section-heading"><h2>Disputes</h2></div>{disputes.length ? <DisputeTable disputes={disputes} /> : <p className="status">No uploaded disputes for this team.</p>}</section>
    </>}
  </div>;
}

