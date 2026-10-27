import { useEffect, useState } from "react";
import { useSpendData } from "./useSpendData.js";
import { EmptyState, UploadButton } from "./components/Upload.jsx";
import { CategoryRibbon, Headline, MonthlyChart, Totals } from "./components/Overview.jsx";
import { Ledger } from "./components/Ledger.jsx";
import { Reports, Statements } from "./components/Sidebar.jsx";

export default function App() {
  const data = useSpendData();
  const { summary, loading, error } = data;
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null); // { kind: "ok" | "error", text }
  const [category, setCategory] = useState(null);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), notice.kind === "error" ? 9000 : 6000);
    return () => clearTimeout(t);
  }, [notice]);

  const handleFile = async (file) => {
    setBusy(true);
    try {
      const res = await data.upload(file);
      const s = res.statement;
      const extras = res.warnings.length ? ` ${res.warnings.join(" ")}` : "";
      setNotice({ kind: "ok", text: `Imported ${s.rows_kept} transactions from ${s.filename}.${extras}` });
    } catch (e) {
      setNotice({ kind: "error", text: `Couldn't import ${file.name}. ${e.message}` });
    } finally {
      setBusy(false);
    }
  };

  const handleCategory = async (tx, newCategory) => {
    try {
      await data.setCategory(tx, newCategory);
      setNotice({
        kind: "ok",
        text: `Moved ${tx.merchant} to ${newCategory}. Future uploads will put it there too.`,
      });
    } catch (e) {
      setNotice({ kind: "error", text: `Couldn't change the category. ${e.message}` });
    }
  };

  const handleDelete = async (id) => {
    try {
      await data.removeStatement(id);
      setCategory(null);
      setNotice({ kind: "ok", text: "Statement deleted." });
    } catch (e) {
      setNotice({ kind: "error", text: `Couldn't delete the statement. ${e.message}` });
    }
  };

  return (
    <div className="app">
      <nav className="topbar">
        <span className="brand">SpendSense</span>
        {summary && <UploadButton onFile={handleFile} busy={busy} variant="secondary" />}
      </nav>

      {notice && (
        <div className={`notice ${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>
          {notice.text}
          <button className="link" onClick={() => setNotice(null)} aria-label="Dismiss">
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <p className="loading">Loading your statements…</p>
      ) : error ? (
        <div className="notice error" role="alert">{error}</div>
      ) : !summary ? (
        <EmptyState onFile={handleFile} busy={busy} />
      ) : (
        <main>
          <Headline totals={summary.totals} topCategory={summary.by_category[0]} />
          <CategoryRibbon categories={summary.by_category} selected={category} onSelect={setCategory} />
          <div className="grid">
            <MonthlyChart monthly={summary.monthly} />
            <Totals totals={summary.totals} insights={summary.insights} />
          </div>
          <div className="grid grid-ledger">
            <Ledger
              transactions={data.transactions}
              categories={data.categories}
              selectedCategory={category}
              onClearCategory={() => setCategory(null)}
              onChangeCategory={handleCategory}
            />
            <aside className="side">
              <Reports />
              <Statements statements={data.statements} onDelete={handleDelete} />
            </aside>
          </div>
        </main>
      )}
    </div>
  );
}
