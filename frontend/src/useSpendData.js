import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";

/** All server state for the dashboard, plus the actions that change it. */
export function useSpendData() {
  const [categories, setCategories] = useState([]);
  const [statements, setStatements] = useState([]);
  const [summary, setSummary] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [stmts, txns] = await Promise.all([api.statements(), api.transactions()]);
      setStatements(stmts);
      setTransactions(txns);
      setSummary(txns.length ? await api.summary() : null);
      setError(null);
    } catch (e) {
      setError(
        e.status ? e.message : "Can't reach the SpendSense API. Start it with: uvicorn app.main:app --reload"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => {});
    refresh();
  }, [refresh]);

  const upload = useCallback(
    async (file) => {
      const result = await api.upload(file);
      await refresh();
      return result;
    },
    [refresh]
  );

  const setCategory = useCallback(
    async (tx, category) => {
      await api.setCategory(tx.id, category);
      await refresh();
    },
    [refresh]
  );

  const removeStatement = useCallback(
    async (id) => {
      await api.deleteStatement(id);
      await refresh();
    },
    [refresh]
  );

  return { categories, statements, summary, transactions, loading, error, upload, setCategory, removeStatement };
}
