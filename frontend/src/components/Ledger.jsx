import { useMemo, useState } from "react";
import { colorFor, inrExactly, monthLabel, shortDate } from "../format.js";

const PAGE = 25;

/** Every transaction, filterable, with the category editable inline. */
export function Ledger({ transactions, categories, selectedCategory, onClearCategory, onChangeCategory }) {
  const [month, setMonth] = useState("");
  const [search, setSearch] = useState("");
  const [onlyUncategorised, setOnlyUncategorised] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [savingId, setSavingId] = useState(null);

  const months = useMemo(
    () => [...new Set(transactions.map((t) => t.date.slice(0, 7)))].sort().reverse(),
    [transactions]
  );
  const uncategorisedCount = useMemo(() => transactions.filter((t) => t.category === "Other").length, [transactions]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return transactions.filter(
      (t) =>
        (!selectedCategory || t.category === selectedCategory) &&
        (!month || t.date.startsWith(month)) &&
        (!onlyUncategorised || t.category === "Other") &&
        (!q || t.merchant.toLowerCase().includes(q) || t.description.toLowerCase().includes(q))
    );
  }, [transactions, selectedCategory, month, onlyUncategorised, search]);

  const change = async (tx, category) => {
    setSavingId(tx.id);
    try {
      await onChangeCategory(tx, category);
    } finally {
      setSavingId(null);
    }
  };

  return (
    <section className="ledger" aria-labelledby="ledger-title">
      <div className="ledger-head">
        <h2 id="ledger-title">Transactions</h2>
        <div className="filters">
          <input
            type="search"
            placeholder="Search merchant"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search by merchant"
          />
          <select value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
            <option value="">All months</option>
            {months.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m)}
              </option>
            ))}
          </select>
          {uncategorisedCount > 0 && (
            <button
              className={`toggle ${onlyUncategorised ? "is-on" : ""}`}
              aria-pressed={onlyUncategorised}
              onClick={() => setOnlyUncategorised((v) => !v)}
            >
              Needs a category <span className="count">{uncategorisedCount}</span>
            </button>
          )}
        </div>
      </div>

      {selectedCategory && (
        <p className="filter-note">
          Showing {selectedCategory} only.{" "}
          <button className="link" onClick={onClearCategory}>
            Show all categories
          </button>
        </p>
      )}

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Merchant</th>
              <th scope="col">Category</th>
              <th scope="col" className="right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((t) => (
              <tr key={t.id} className={t.category === "Other" ? "is-other" : ""}>
                <td className="date num">{shortDate(t.date)}</td>
                <td>
                  <span className="merchant">{t.merchant}</span>
                  <span className="narration" title={t.description}>{t.description}</span>
                </td>
                <td>
                  <label className="cat-select" style={{ "--dot": colorFor(t.category) }}>
                    <span className="visually-hidden">Category for {t.merchant}</span>
                    <select
                      value={t.category}
                      disabled={savingId === t.id}
                      onChange={(e) => change(t, e.target.value)}
                    >
                      {categories.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  </label>
                </td>
                <td className={`right num amount ${t.amount < 0 ? "out" : "in"}`}>
                  {t.amount < 0 ? "−" : "+"}
                  {inrExactly(Math.abs(t.amount))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="none">No transactions match these filters.</p>}
      </div>
      {rows.length > limit && (
        <button className="btn btn-quiet more" onClick={() => setLimit((l) => l + PAGE)}>
          Show {Math.min(PAGE, rows.length - limit)} more of {rows.length - limit}
        </button>
      )}
    </section>
  );
}
