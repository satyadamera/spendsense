import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { colorFor, inr, longDate, monthLabel, shortDate } from "../format.js";

/** The page's lead: the period's story in one sentence. */
export function Headline({ totals, topCategory }) {
  const sameYear = totals.period_start.slice(0, 4) === totals.period_end.slice(0, 4);
  return (
    <header className="headline">
      <h1>
        You spent <span className="num">{inr(totals.spend)}</span> between{" "}
        {sameYear ? shortDate(totals.period_start) : longDate(totals.period_start)} and{" "}
        {longDate(totals.period_end)}.
      </h1>
      {topCategory && (
        <p className="lede">
          {topCategory.category} took the biggest share: {inr(topCategory.amount)}, or {topCategory.share}% of it.
          Transfers to your own accounts and investments aren't counted as spending.
        </p>
      )}
    </header>
  );
}

/** Full-width ribbon: every category's share of spending. Click a segment to filter the ledger. */
export function CategoryRibbon({ categories, selected, onSelect }) {
  if (!categories.length) return null;
  const toggle = (c) => onSelect(selected === c ? null : c);
  return (
    <section className="ribbon-wrap" aria-label="Spending by category">
      <div className="ribbon" role="list">
        {categories.map((c) => (
          <button
            key={c.category}
            role="listitem"
            className={`seg ${selected && selected !== c.category ? "is-dim" : ""}`}
            style={{ flexGrow: c.amount, background: colorFor(c.category) }}
            title={`${c.category}: ${inr(c.amount)} (${c.share}%)`}
            aria-label={`${c.category}, ${inr(c.amount)}, ${c.share}% of spending`}
            aria-pressed={selected === c.category}
            onClick={() => toggle(c.category)}
          />
        ))}
      </div>
      <ul className="legend">
        {categories.map((c) => (
          <li key={c.category}>
            <button
              className={`legend-item ${selected === c.category ? "is-selected" : ""} ${
                selected && selected !== c.category ? "is-dim" : ""
              }`}
              onClick={() => toggle(c.category)}
              aria-pressed={selected === c.category}
            >
              <span className="swatch" style={{ background: colorFor(c.category) }} />
              <span className="legend-name">{c.category}</span>
              <span className="legend-amt num">{inr(c.amount)}</span>
              <span className="legend-share num">{c.share}%</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

const axisInr = (v) => (v >= 100000 ? `₹${(v / 100000).toFixed(1)}L` : v >= 1000 ? `₹${v / 1000}k` : `₹${v}`);

function MonthTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="chart-tip">
      <strong>{monthLabel(label)}</strong>
      <span>Income {inr(row.income)}</span>
      <span>Spending {inr(row.spend)}</span>
      <span className={row.net < 0 ? "neg" : "pos"}>Left over {inr(row.net)}</span>
    </div>
  );
}

export function MonthlyChart({ monthly }) {
  const data = monthly;
  return (
    <section className="panel">
      <h2>Month by month</h2>
      <div className="chart-key">
        <span><i style={{ background: "var(--income)" }} /> Income</span>
        <span><i style={{ background: "var(--spend)" }} /> Spending</span>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={data} barGap={4} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--rule)" />
            <XAxis dataKey="month" tickFormatter={(m) => monthLabel(m).split(" ")[0].slice(0, 3)}
              tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 13 }} />
            <YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={48}
              tick={{ fill: "var(--muted)", fontSize: 12 }} />
            <Tooltip content={<MonthTooltip />} cursor={{ fill: "var(--wash)" }} />
            <Bar dataKey="income" fill="var(--income)" radius={[3, 3, 0, 0]} maxBarSize={36} />
            <Bar dataKey="spend" fill="var(--spend)" radius={[3, 3, 0, 0]} maxBarSize={36} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export function Totals({ totals, insights }) {
  const rows = [
    ["Income", inr(totals.income)],
    ["Spending", inr(totals.spend)],
    ["Invested", inr(totals.invested)],
    ["Savings rate", totals.savings_rate == null ? "–" : `${totals.savings_rate}%`],
    ["Transactions", totals.transactions],
  ];
  return (
    <section className="panel">
      <h2>The numbers</h2>
      <dl className="totals">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="num">{v}</dd>
          </div>
        ))}
      </dl>
      {insights.length > 0 && (
        <>
          <h3>Worth knowing</h3>
          <ul className="insights">
            {insights.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
