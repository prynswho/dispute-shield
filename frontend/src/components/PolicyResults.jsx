import React, { useState } from 'react';
import { money } from '../data.js';

const labels = {
  disputes: 'Disputes',
  disputes_lost: 'Disputes lost',
  usd_lost: 'Dollars lost',
};
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

export function policyValue(metric, value) {
  return metric === 'usd_lost' ? money(value) : number.format(value);
}

export function PolicyResults({ policy }) {
  return <div className="table-scroll"><table>
    <caption className="sr-only">Baseline and estimated policy changes over {policy.period}</caption>
    <thead><tr><th>Metric</th><th>{policy.baseline_label ?? 'Historical baseline'}</th><th>Central change</th><th>Scenario range of change</th></tr></thead>
    <tbody>{policy.results.map((row) => <tr key={row.metric}>
      <td>{labels[row.metric]}</td>
      <td>{policyValue(row.metric, policy.baseline[row.metric])}</td>
      <td>{policyValue(row.metric, row.estimated_change)}</td>
      <td>{policyValue(row.metric, row.low)} to {policyValue(row.metric, row.high)}</td>
    </tr>)}</tbody>
  </table></div>;
}

export function PolicyScenarios({ policy }) {
  const [treatment, setTreatment] = useState('predicted');
  const hasAttrition = policy.scenarios.some((scenario) => scenario.attrition_rate !== undefined);
  const hasOutcomes = policy.scenarios.some((scenario) => scenario.open_treatment !== undefined);
  const treatments = [...new Map(policy.scenarios.filter((scenario) => scenario.open_treatment)
    .map((scenario) => [scenario.open_treatment, scenario.open_treatment_label])).entries()];
  const visible = policy.scenarios.filter((scenario) =>
    !hasOutcomes || treatment === 'all' || scenario.open_treatment === treatment);
  return <>{hasOutcomes && <div className="policy-copy">
    <label htmlFor="scenario-outcomes">Scenario open outcomes </label>
    <select id="scenario-outcomes" value={treatment} onChange={(event) => setTreatment(event.target.value)}>
      {treatments.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      <option value="all">All outcome treatments</option>
    </select>
    <p>The reported range includes all outcome treatments. The table shows {visible.length} of {policy.scenarios.length} combinations.</p>
  </div>}<div className="table-scroll"><table>
    <caption className="sr-only">Attrition and evidence benefit by scenario</caption>
    <thead><tr><th>Evidence scenario</th>{hasOutcomes && <th>Open outcomes</th>}{hasAttrition && <th>Job attrition</th>}<th>Gap closed</th><th>Disputes change</th><th>Disputes lost change</th><th>Dollars lost change</th><th>From attrition</th><th>From evidence</th></tr></thead>
    <tbody>{visible.map((scenario) => <tr key={scenario.key}>
      <td>{scenario.label}</td>
      {hasOutcomes && <td>{scenario.open_treatment_label}</td>}
      {hasAttrition && <td>{scenario.attrition_rate * 100}%</td>}
      <td>{scenario.gap_share * 100}%</td>
      <td>{policyValue('disputes', scenario.change.disputes)}</td>
      <td>{policyValue('disputes_lost', scenario.change.disputes_lost)}</td>
      <td>{money(scenario.change.usd_lost)}</td>
      <td>{money(scenario.attrition_change.usd_lost)}</td>
      <td>{money(scenario.evidence_change.usd_lost)}</td>
    </tr>)}</tbody>
  </table></div></>;
}
