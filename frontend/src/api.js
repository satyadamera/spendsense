// Thin wrapper around the SpendSense REST API.
const BASE = import.meta.env.VITE_API_URL ?? "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
    const err = new Error(detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body;
}

function query(params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v != null && v !== "" && q.set(k, v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  categories: () => request("/api/categories"),
  statements: () => request("/api/statements"),
  summary: () => request("/api/summary"),
  transactions: (params = {}) => request(`/api/transactions${query(params)}`),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/statements", { method: "POST", body: form });
  },
  deleteStatement: (id) => request(`/api/statements/${id}`, { method: "DELETE" }),
  setCategory: (id, category) =>
    request(`/api/transactions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, apply_to_merchant: true }),
    }),
  reportUrl: (fmt) => `${BASE}/api/reports/${fmt}`,
};
