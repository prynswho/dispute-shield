import assert from 'node:assert/strict';
import test from 'node:test';
import { exportUrl, uploadPayments, uploadDisputes, loadPortfolio, loadPolicies, policyExportUrl } from '../src/api.js';

test('payment upload sends the three named CSV fields', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (path, options) => {
    assert.equal(path, '/api/uploads/payments');
    assert.equal(options.method, 'POST');
    assert.deepEqual([...options.body.keys()], ['invoices', 'photos', 'payments']);
    return { ok: true, json: async () => ({ run_id: 'synthetic', payments: [] }) };
  };
  try {
    const csv = new Blob(['id\n1'], { type: 'text/csv' });
    assert.equal((await uploadPayments({ invoices: csv, photos: csv, payments: csv })).run_id, 'synthetic');
  } finally { globalThis.fetch = original; }
});

test('dispute upload preserves the active run and API errors reach the user', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (path, options) => {
    assert.equal(path, '/api/uploads/synthetic/disputes');
    assert.deepEqual([...options.body.keys()], ['disputes']);
    return { ok: false, json: async () => ({ detail: 'Unknown payment ID in disputes.csv' }) };
  };
  try {
    await assert.rejects(uploadDisputes('synthetic', new Blob(['dispute_id'])), /Unknown payment ID/);
  } finally { globalThis.fetch = original; }
  assert.equal(exportUrl('synthetic', 'payment'), '/api/uploads/synthetic/payment_predictions.csv');
});

test('portfolio handles non-JSON server errors', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => { throw new Error(); } });
  try {
    await assert.rejects(loadPortfolio(), /503/);
  } finally { globalThis.fetch = original; }
});

test('policy analysis and export use the same outcome mode', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (path) => {
    assert.equal(path, '/api/policies?mode=withdrawn_sensitivity');
    return { ok: true, json: async () => ({ policies: [] }) };
  };
  try {
    await loadPolicies('withdrawn_sensitivity');
    assert.equal(policyExportUrl('withdrawn_sensitivity'),
      '/api/policies/whatif_results.csv?mode=withdrawn_sensitivity');
    assert.equal(policyExportUrl(), '/api/policies/whatif_results.csv?mode=open_expected');
  } finally { globalThis.fetch = original; }
});
