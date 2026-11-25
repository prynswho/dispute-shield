import React from 'react';
import { money, probability, label } from '../data.js';
import { Badge, RiskBadge } from './ui.jsx';

export function PaymentTable({ payments, onSelect, selected }) {
  return <div className="table-scroll"><table>
    <thead><tr><th>Payment / team</th><th>Amount</th><th>Dispute risk</th><th>Win if disputed</th><th>Expected loss</th><th><span className="sr-only">Details</span></th></tr></thead>
    <tbody>{payments.map((payment) => <tr key={payment.payment_id} className={selected === payment.payment_id ? 'selected' : ''}>
      <td><strong className="id">{payment.payment_id}</strong><small>{payment.team_id}</small></td>
      <td>{money(payment.amount_usd)}</td>
      <td><RiskBadge tier={payment.dispute_risk_tier} /><small>{probability(payment.dispute_risk_score)}</small></td>
      <td>{probability(payment.payment_win_prob)}</td>
      <td>{payment.expected_loss_usd == null ? '—' : money(payment.expected_loss_usd)}</td>
      <td><button className="text-button" onClick={() => onSelect(payment)}>Review <span aria-hidden="true">↗</span></button></td>
    </tr>)}</tbody>
  </table></div>;
}

export function DisputeTable({ disputes }) {
  return <div className="table-scroll"><table>
    <thead><tr><th>Dispute / payment</th><th>Team</th><th>Reason</th><th>Win probability</th><th>Recommendation</th><th>Result</th></tr></thead>
    <tbody>{disputes.map((dispute) => <tr key={dispute.dispute_id}>
      <td><strong className="id">{dispute.dispute_id}</strong><small>{dispute.payment_id}</small></td>
      <td className="id">{dispute.team_id}</td><td>{label(dispute.reason)}</td>
      <td>{probability(dispute.win_prob)}</td>
      <td><Badge kind={dispute.recommendation}>{dispute.recommendation}</Badge></td>
      <td>{dispute.outcome ? label(dispute.outcome) : <span className="muted">Pending</span>}</td>
    </tr>)}</tbody>
  </table></div>;
}

