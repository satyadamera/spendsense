import { useRef, useState } from "react";

const ACCEPT = ".csv,.xlsx,.xls";

/** Button that opens a file picker. */
export function UploadButton({ onFile, busy, variant = "primary" }) {
  const input = useRef(null);
  return (
    <>
      <button className={`btn btn-${variant}`} onClick={() => input.current?.click()} disabled={busy}>
        {busy ? "Importing…" : "Upload statement"}
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </>
  );
}

/** First-run screen: a drop zone that explains what to upload. */
export function EmptyState({ onFile, busy }) {
  const [over, setOver] = useState(false);
  return (
    <section
      className={`empty ${over ? "is-over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <h1>Where did the money go?</h1>
      <p>
        Drop a bank or UPI statement here, exported as CSV or Excel. SpendSense cleans it up, sorts every
        transaction into a category and builds Word and PowerPoint reports you can share.
      </p>
      <UploadButton onFile={onFile} busy={busy} />
      <p className="hint">
        No statement handy? Use the files in <code>sample_data/</code>. They're made up.
      </p>
    </section>
  );
}
