const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const inrExact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const inr = (x) => (x == null ? "–" : inrFormatter.format(x));
export const inrExactly = (x) => (x == null ? "–" : inrExact.format(x));

export const shortDate = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

export const longDate = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export const monthLabel = (ym) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
};

// Stable colours per category, shared by the ribbon and the ledger.
export const CATEGORY_COLORS = {
  "Rent & Housing": "#3B5BDB",
  "Food & Dining": "#C2410C",
  Groceries: "#2F9E6B",
  Shopping: "#B4387A",
  Transport: "#0B7285",
  Travel: "#7048E8",
  "Bills & Utilities": "#B08900",
  "Subscriptions & Entertainment": "#D9480F",
  Education: "#1971C2",
  Health: "#C92A2A",
  "Cash Withdrawal": "#5C6B80",
  "Investments & Savings": "#2B8A3E",
  Transfers: "#868E96",
  Income: "#237A3B",
  Refunds: "#40916C",
  Other: "#ADB5BD",
};
export const colorFor = (c) => CATEGORY_COLORS[c] ?? "#ADB5BD";
