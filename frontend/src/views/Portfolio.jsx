import React, { useEffect, useState } from 'react';
import { loadCatalog } from '../api.js';
import { label, probability, money } from '../data.js';
import { Empty } from '../components/ui.jsx';

export function Portfolio({ portfolio, loading, error, disputes }) {
  const [reasons, setReasons] = useState([]);
  const [selectedReason, setSelectedReason] = useState('');
  useEffect(() => {
    let active = true;
    loadCatalog().then((data) => { if (active) setReasons(data.reasons); }).catch(() => {});
    return () => { active = false; };
  }, []);
  const options = [...new Set([...reasons, ...portfolio.reasons.map((row) => row.reason)])];
  const historical = portfolio.reasons.filter((row) => !selectedReason || row.reason === selectedReason);
  const pending = Object.entries(disputes.reduce((groups, row) => {
    if ((!selectedReason || row.reason === selectedReason) && (!row.outcome || row.outcome === 'open')) groups[row.reason] = (groups[row.reason] || 0) + 1;
    return groups;
  }, {}));
  return <div className="stack">
    <div className="policy-picker"><label htmlFor="reason-select">Dispute reason</label>
      <select id="reason-select" value={selectedReason} onChange={(event) => setSelectedReason(event.target.value)}>
        <option value="">All reasons</option>
        {options.map((reason) => <option key={reason} value={reason}>{label(reason)}</option>)}
      </select>
    </div>
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">Historical outcomes</span><h2>Results by dispute reason</h2></div></div>
      {loading ? <p className="status">Loading historical results…</p> : error ? <p role="status" className="status">{error}</p> : !portfolio.reasons.length ? <Empty title="Historical results are unavailable">Historical portfolio results will appear once the summary artifact is prepared.</Empty> :
        <div className="table-scroll"><table><thead><tr><th>Reason</th><th>Disputes</th><th>Wins</th><th>Losses</th><th>Win rate</th><th>Dollars lost</th></tr></thead><tbody>{historical.map((row) => <tr key={row.reason}><td>{label(row.reason)}</td><td>{row.disputes.toLocaleString()}</td><td>{row.wins}</td><td>{row.losses}</td><td>{probability(row.win_rate)}</td><td>{money(row.usd_lost)}</td></tr>)}</tbody></table></div>}
    </section>
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">Current upload</span><h2>Disputes awaiting outcomes</h2></div></div>
      {pending.length ? <div className="reason-grid">{pending.map(([reason, count]) => <div key={reason}><span>{label(reason)}</span><strong>{count}</strong></div>)}</div> : <Empty title="No pending disputes uploaded">Add the dispute CSV after scoring the payment files.</Empty>}
    </section>
  </div>;
}

