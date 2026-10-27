import { api } from "../api.js";
import { longDate } from "../format.js";

export function Reports() {
  return (
    <section className="panel">
      <h2>Reports</h2>
      <p className="muted">Built from every statement you've uploaded, with the categories as you've set them.</p>
      <div className="report-links">
        <a className="btn btn-primary" href={api.reportUrl("docx")} download>
          Download Word report
        </a>
        <a className="btn btn-secondary" href={api.reportUrl("pptx")} download>
          Download PowerPoint summary
        </a>
      </div>
    </section>
  );
}

export function Statements({ statements, onDelete }) {
  return (
    <section className="panel">
      <h2>Uploaded statements</h2>
      <ul className="statements">
        {statements.map((s) => (
          <li key={s.id}>
            <div>
              <strong>{s.filename}</strong>
              <span className="muted">
                {s.period_start && `${longDate(s.period_start)} to ${longDate(s.period_end)}`}
              </span>
              <span className="muted">
                {s.rows_kept} transactions kept
                {s.duplicates_removed > 0 && `, ${s.duplicates_removed} duplicate${s.duplicates_removed > 1 ? "s" : ""} removed`}
                {s.invalid_rows > 0 && `, ${s.invalid_rows} non-transaction row${s.invalid_rows > 1 ? "s" : ""} skipped`}
              </span>
            </div>
            <button
              className="link danger"
              onClick={() => {
                if (window.confirm(`Delete ${s.filename} and its ${s.rows_kept} transactions?`)) onDelete(s.id);
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
