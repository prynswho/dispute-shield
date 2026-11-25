import React, { useEffect, useState } from 'react';
import { loadPolicies, policyExportUrl } from '../api.js';
import { Badge } from '../components/ui.jsx';
import { PolicyResults, PolicyScenarios } from '../components/PolicyResults.jsx';

export function WhatIf() {
  const [policies, setPolicies] = useState([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [mode, setMode] = useState('open_expected');
  const [modes, setModes] = useState([]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    loadPolicies(mode).then((data) => {
      if (active) {
        setPolicies(data.policies);
        setSelected((current) => data.policies.some((policy) => policy.policy === current)
          ? current : data.policies[0]?.policy ?? '');
        setModes(data.analysis_modes);
      }
    }).catch((failure) => {
      if (active) setError(failure.message);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [mode]);

  if (loading) return <p className="status" role="status">Loading policy estimates…</p>;
  if (error) return <p className="alert error" role="alert">{error}</p>;
  const policy = policies.find((item) => item.policy === selected);
  if (!policy) return <p className="status">No policy estimates are available.</p>;
  return <div className="stack">
    <div className="policy-picker">
      <label htmlFor="policy-select">Policy</label>
      <select id="policy-select" value={selected} onChange={(event) => setSelected(event.target.value)}>
        {policies.map((item) => <option key={item.policy} value={item.policy}>{item.name}</option>)}
      </select>
      <label htmlFor="analysis-select">Outcome analysis</label>
      <select id="analysis-select" value={mode} onChange={(event) => setMode(event.target.value)}>
        {modes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
      <a className="download" href={policyExportUrl(mode)}>Download what-if CSV ↓</a>
    </div>
    <section className="panel">
      <div className="section-heading">
        <div><h2>{policy.name}</h2><p className="muted">{policy.description} Historical estimates over {policy.period.toLowerCase()}.</p></div>
        <Badge>{policy.confidence} confidence</Badge>
      </div>
      <PolicyResults policy={policy} />
      <p className="policy-note">Negative changes mean fewer cases or lower losses. Fractional case counts are expectations.</p>
      {policy.outcome_counts && <p className="policy-note">
        Historical open cases ({policy.outcome_counts.open}) are probability weighted in the point estimate.
        {mode === 'withdrawn_sensitivity'
          ? ` Withdrawn cases (${policy.outcome_counts.withdrawn}) are also modelled in this unvalidated sensitivity analysis.`
          : ` Withdrawn cases (${policy.outcome_counts.withdrawn}) retain zero observed loss.`}
      </p>}
    </section>
    <section className="panel">
      <div className="section-heading"><div><h2>Scenario assumptions</h2>
        <p className="muted">{policy.gap_description}</p>
      </div></div>
      <PolicyScenarios policy={policy} />
      <div className="policy-copy">
        {policy.population_notes.map((note) => <p key={note}>{note}</p>)}
      </div>
    </section>
    <section className="panel">
      <div className="section-heading"><h2>Method and limitations</h2></div>
      <div className="policy-copy">
        <h3>Assumptions</h3>
        <ul>{policy.assumptions.map((text) => <li key={text}>{text}</li>)}</ul>
        <h3>Why confidence is low</h3>
        <ul>{policy.limitations.map((text) => <li key={text}>{text}</li>)}</ul>
        <p className="footnote">{policy.source}</p>
      </div>
    </section>
  </div>;
}
