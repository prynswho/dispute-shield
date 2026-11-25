import assert from 'node:assert/strict';
import test from 'node:test';
import { filterPayments, probability, summarizePayments } from '../src/data.js';

const payments = [
  { payment_id: 'p-one', invoice_id: 'i-one', team_id: 'team-a', amount_usd: 100, expected_loss_usd: 1.25, dispute_risk_tier: 'high' },
  { payment_id: 'p-two', invoice_id: 'i-two', team_id: 'team-b', amount_usd: 250, expected_loss_usd: null, dispute_risk_tier: 'low' },
];

test('payment filters preserve matching rows and support invoice search', () => {
  assert.deepEqual(filterPayments(payments, 'team-a', 'high', ' I-ONE '), [payments[0]]);
  assert.deepEqual(filterPayments(payments, 'team-a', 'low', ''), []);
});

test('summary counts exposure and high-risk rows without treating null exposure as a score', () => {
  assert.deepEqual(summarizePayments(payments), { amount: 350, exposure: 1.25, high: 1 });
  assert.deepEqual(summarizePayments([]), { amount: 0, exposure: 0, high: 0 });
  assert.equal(probability(null), '—');
  assert.equal(probability(0), '0%');
});
