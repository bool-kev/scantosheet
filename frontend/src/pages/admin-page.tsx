import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import type { ApiKey, ApiKeyCreated, ApiKeyRole } from "../api/types";
import { ApiKeyField } from "../components/api-key-field";
import {
  useApiKeys,
  useCreateApiKey,
  useHealth,
  useRevokeApiKey,
} from "../hooks/useApiKeys";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Turn an admin API failure into actionable guidance. */
function describeKeyError(error: ApiError): string {
  switch (error.status) {
    case 401:
      return "Clé administrateur manquante ou invalide. Renseignez-la ci-dessus.";
    case 403:
      return "Cette clé est valide mais n'a pas le rôle admin.";
    case 503:
      return error.message; // server explains ADMIN_API_KEY is not configured
    default:
      return error.message;
  }
}

/** Shown once, right after creation — the secret is unrecoverable afterwards. */
function CreatedKeyBanner({ created }: { created: ApiKeyCreated }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mb-6 rounded-xl border border-emerald-300 bg-emerald-50 p-4">
      <p className="font-medium text-emerald-900">
        Clé créée pour « {created.label} »
      </p>
      <p className="mt-1 text-sm text-emerald-800">
        Copiez-la maintenant : elle ne sera <strong>plus jamais affichée</strong>.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-lg bg-white px-3 py-2 font-mono text-sm text-slate-800">
          {created.key}
        </code>
        <button
          onClick={() => {
            navigator.clipboard.writeText(created.key);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          }}
          className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          {copied ? "Copié !" : "Copier"}
        </button>
      </div>
    </div>
  );
}

export function AdminPage() {
  const { data: health } = useHealth();
  const authEnabled = health?.auth_enabled ?? false;

  const keys = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();

  const [label, setLabel] = useState("");
  const [role, setRole] = useState<ApiKeyRole>("user");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!label.trim()) {
      setError("Le libellé est obligatoire.");
      return;
    }
    createKey.mutate(
      { label: label.trim(), role },
      {
        onSuccess: (data) => {
          setCreated(data);
          setLabel("");
        },
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : "Échec de la création"),
      },
    );
  };

  const onRevoke = (key: ApiKey) => {
    if (window.confirm(`Révoquer la clé « ${key.label} » ?`)) {
      revokeKey.mutate(key.id, {
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : "Échec de la révocation"),
      });
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <Link to="/" className="text-sm text-brand-600 hover:underline">
        ← Retour
      </Link>
      <h1 className="mt-1 text-3xl font-bold text-slate-900">Clés API</h1>
      <p className="mt-1 text-slate-500">
        Cet espace exige <strong>toujours</strong> une clé administrateur, même
        lorsque l'import reste ouvert. Chaque clé
        <code className="mx-1">user</code> ne voit que les documents qu'elle a envoyés.
      </p>

      {!authEnabled && (
        <p className="mt-4 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600">
          L'accès aux imports est <strong>ouvert</strong> (
          <code>AUTH_ENABLED=false</code>) : l'interface fonctionne sans clé. Les
          clés créées ici ne seront exigées sur l'API documents qu'une fois cette
          option activée.
        </p>
      )}

      <section className="mt-6">
        <ApiKeyField />
      </section>

      {created && (
        <div className="mt-6">
          <CreatedKeyBanner created={created} />
        </div>
      )}

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold text-slate-800">Créer une clé</h2>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-sm font-medium text-slate-600">
            Libellé
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Service Comptabilité"
              className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="flex flex-col text-sm font-medium text-slate-600">
            Rôle
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as ApiKeyRole)}
              className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="user">user — ses documents uniquement</option>
              <option value="admin">admin — tout + gestion des clés</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={createKey.isPending}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-40"
          >
            {createKey.isPending ? "Création…" : "Créer la clé"}
          </button>
        </form>
        {error && (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
      </section>

      <section className="mt-6">
        <h2 className="mb-3 font-semibold text-slate-800">Clés existantes</h2>
        {keys.isLoading && <p className="text-sm text-slate-400">Chargement…</p>}
        {keys.isError && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {describeKeyError(keys.error as ApiError)}
          </p>
        )}
        {keys.data && keys.data.length === 0 && (
          <p className="text-sm text-slate-400">Aucune clé pour le moment.</p>
        )}
        {keys.data && keys.data.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Libellé</th>
                  <th className="px-4 py-3 font-medium">Préfixe</th>
                  <th className="px-4 py-3 font-medium">Rôle</th>
                  <th className="px-4 py-3 font-medium">Statut</th>
                  <th className="px-4 py-3 font-medium">Dernier usage</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {keys.data.map((key) => (
                  <tr key={key.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-700">{key.label}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      sts_{key.prefix}_…
                    </td>
                    <td className="px-4 py-3 text-slate-600">{key.role}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          key.is_active
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {key.is_active ? "Active" : "Révoquée"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {formatDate(key.last_used_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {key.is_active && (
                        <button
                          onClick={() => onRevoke(key)}
                          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                        >
                          Révoquer
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
