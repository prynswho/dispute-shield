import React, { useEffect, useRef } from 'react';
import { money, probability, paymentActions } from '../data.js';
import { RiskBadge } from './ui.jsx';

export function PaymentDetail({ payment, close }) {
  const closeButton = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    closeButton.current?.focus();
    function handleKey(event) {
      if (event.key === 'Escape') close();
      if (event.key === 'Tab') {
        event.preventDefault();
        closeButton.current?.focus();
      }
    }
    document.addEventListener('keydown', handleKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  const actions = paymentActions(payment);
  return <aside className="detail" role="dialog" aria-modal="true" aria-label="Payment details">
    <div className="section-heading"><div><span className="eyebrow">Payment review</span><h2 className="id">{payment.payment_id}</h2></div><button ref={closeButton} className="icon-button" onClick={close} aria-label="Close payment details">×</button></div>
    <dl className="details-grid"><div><dt>Invoice</dt><dd className="id">{payment.invoice_id || 'Missing ID'}</dd></div><div><dt>Team</dt><dd className="id">{payment.team_id}</dd></div>
      <div><dt>Amount</dt><dd>{money(payment.amount_usd)}</dd></div><div><dt>Risk tier</dt><dd><RiskBadge tier={payment.dispute_risk_tier} /></dd></div>
      <div><dt>Dispute risk</dt><dd>{probability(payment.dispute_risk_score)}</dd></div><div><dt>Payment win probability</dt><dd>{probability(payment.payment_win_prob)}</dd></div></dl>
    <div className="callout"><strong>Invoice readiness</strong><p>{payment.dispute_risk_tier == null ? 'A matching invoice is needed to score this payment.' : 'Invoice win probability is left blank because historical invoice timing could not support a reliable estimate.'}</p></div>
    <h3>Evidence gaps & next actions</h3>
    {actions.length ? <ul className="action-list">{actions.map((action, index) => <li key={index}>{action}</li>)}</ul> : <p className="muted">No additional action was identified from the supplied fields.</p>}
    <p className="footnote">Win probability is conditional on a dispute. Expected loss combines dispute risk, payment win probability, payment amount, and the $25 dispute fee.</p>
  </aside>;
}

