import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { clearApiKey, getApiKey, setApiKey } from "../api/client";

/** Lets the operator paste the API key used for every request. */
export function ApiKeyField() {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(getApiKey());
  const [reveal, setReveal] = useState(false);
  const [saved, setSaved] = useState(false);

  const persist = (next: string) => {
    setApiKey(next);
    setValue(next);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
    // Every cached response was fetched with the previous identity.
    queryClient.invalidateQueries();
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <label className="block text-sm font-medium text-slate-700">
        Clé administrateur
      </label>
      <p className="mt-0.5 text-xs text-slate-400">
        Requise pour gérer les clés. Envoyée dans l'en-tête <code>X-API-Key</code>{" "}
        et stockée dans ce navigateur uniquement.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <input
          type={reveal ? "text" : "password"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="sts_…"
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
        />
        <button
          type="button"
          onClick={() => setReveal((r) => !r)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
        >
          {reveal ? "Masquer" : "Afficher"}
        </button>
        <button
          type="button"
          onClick={() => persist(value)}
          className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
        >
          Enregistrer
        </button>
        <button
          type="button"
          onClick={() => {
            clearApiKey();
            setValue("");
            queryClient.invalidateQueries();
          }}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
        >
          Effacer
        </button>
      </div>
      {saved && <p className="mt-2 text-sm text-emerald-700">Clé enregistrée.</p>}
    </div>
  );
}
