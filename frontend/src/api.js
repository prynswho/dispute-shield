async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = 'The request could not be completed.';
    try {
      const body = await response.json();
      message = typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail ?? body);
    } catch {
      message = `Request failed (${response.status}).`;
    }
    throw new Error(message);
  }
  return response.json();
}

export function uploadPayments(files) {
  const form = new FormData();
  for (const name of ['invoices', 'photos', 'payments']) {
    form.append(name, files[name]);
  }
  return request('/api/uploads/payments', { method: 'POST', body: form });
}

export function uploadDisputes(runId, file) {
  const form = new FormData();
  form.append('disputes', file);
  return request(`/api/uploads/${encodeURIComponent(runId)}/disputes`, {
    method: 'POST',
    body: form,
  });
}

export const loadRun = (runId) => request(`/api/uploads/${encodeURIComponent(runId)}`);
export const loadPortfolio = () => request('/api/portfolio');
export const loadPolicies = (mode = 'open_expected') =>
  request(`/api/policies?mode=${encodeURIComponent(mode)}`);
export const policyExportUrl = (mode = 'open_expected') =>
  `/api/policies/whatif_results.csv?mode=${encodeURIComponent(mode)}`;
export const loadCatalog = () => request('/api/catalog');

export function exportUrl(runId, type) {
  return `/api/uploads/${encodeURIComponent(runId)}/${type}_predictions.csv`;
}
