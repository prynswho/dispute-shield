export const money = (value) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 2,
}).format(Number(value) || 0);

export const probability = (value) => value === null || value === undefined || value === ''
  ? '—'
  : new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 1 }).format(value);

export const label = (value) => String(value ?? '').replaceAll('_', ' ');

export function paymentActions(payment) {
  return (payment.actions ?? []).map((action) => {
    if (typeof action === 'string') return action;
    return action.message ?? action.action ?? action.description ?? JSON.stringify(action);
  });
}

export function filterPayments(payments, team, tier, query) {
  const search = query.trim().toLowerCase();
  return payments.filter((payment) =>
    (!team || payment.team_id === team)
    && (!tier || (payment.dispute_risk_tier ?? 'unscored') === tier)
    && (!search || [payment.payment_id, payment.invoice_id, payment.team_id]
      .some((value) => String(value).toLowerCase().includes(search))));
}

export function summarizePayments(payments) {
  return {
    amount: payments.reduce((sum, row) => sum + Number(row.amount_usd || 0), 0),
    exposure: payments.reduce((sum, row) => sum + Number(row.expected_loss_usd || 0), 0),
    high: payments.filter((row) => row.dispute_risk_tier === 'high').length,
  };
}
