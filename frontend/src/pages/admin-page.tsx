import { useState } from "react";
import { Check, Copy, Plus } from "lucide-react";

import { ApiError } from "../api/client";
import type { ApiKey, ApiKeyCreated, ApiKeyRole } from "../api/types";
import { ApiKeyField } from "../components/api-key-field";
import { ConfirmDialog } from "../components/confirm-dialog";
import {
  useApiKeys,
  useCreateApiKey,
  useHealth,
  useRevokeApiKey,
} from "../hooks/useApiKeys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
    <Card className="border-emerald-500/30 bg-emerald-500/5">
      <CardContent>
        <p className="font-medium text-emerald-800 dark:text-emerald-400">
          Clé créée pour « {created.label} »
        </p>
        <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400/80">
          Copiez-la maintenant : elle ne sera <strong>plus jamais affichée</strong>.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <code className="min-w-0 flex-1 overflow-x-auto rounded-lg border bg-background px-3 py-2 font-mono text-sm">
            {created.key}
          </code>
          <Button
            onClick={() => {
              navigator.clipboard.writeText(created.key);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
            }}
          >
            {copied ? <Check /> : <Copy />}
            {copied ? "Copié !" : "Copier"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CreateKeyDialog({ onCreated }: { onCreated: (key: ApiKeyCreated) => void }) {
  const createKey = useCreateApiKey();
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [role, setRole] = useState<ApiKeyRole>("user");
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
          onCreated(data);
          setLabel("");
          setRole("user");
          setOpen(false);
        },
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : "Échec de la création"),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> Nouvelle clé
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Créer une clé API</DialogTitle>
            <DialogDescription>
              Une clé <code>user</code> ne voit que les documents qu'elle a envoyés ; une
              clé <code>admin</code> voit tout et peut gérer les autres clés.
            </DialogDescription>
          </DialogHeader>

          <div className="my-4 flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="key-label">Libellé</Label>
              <Input
                id="key-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Service Comptabilité"
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="key-role">Rôle</Label>
              <Select value={role} onValueChange={(v) => setRole(v as ApiKeyRole)}>
                <SelectTrigger id="key-role" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">user — ses documents uniquement</SelectItem>
                  <SelectItem value="admin">admin — tout + gestion des clés</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={createKey.isPending}>
              {createKey.isPending ? "Création…" : "Créer la clé"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function AdminPage() {
  const { data: health } = useHealth();
  const authEnabled = health?.auth_enabled ?? false;

  const keys = useApiKeys();
  const revokeKey = useRevokeApiKey();

  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const onRevoke = (key: ApiKey) => {
    revokeKey.mutate(key.id, {
      onError: (err) =>
        setRevokeError(err instanceof ApiError ? err.message : "Échec de la révocation"),
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Clés API</h1>
        <p className="mt-1 text-muted-foreground">
          Cet espace exige <strong>toujours</strong> une clé administrateur, même lorsque
          l'import reste ouvert. Chaque clé <code>user</code> ne voit que les documents
          qu'elle a envoyés.
        </p>
      </header>

      {!authEnabled && (
        <p className="mb-6 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
          L'accès aux imports est <strong>ouvert</strong> (<code>AUTH_ENABLED=false</code>) :
          l'interface fonctionne sans clé. Les clés créées ici ne seront exigées sur l'API
          documents qu'une fois cette option activée.
        </p>
      )}

      <section className="mb-6">
        <ApiKeyField />
      </section>

      {created && (
        <section className="mb-6">
          <CreatedKeyBanner created={created} />
        </section>
      )}

      <section>
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Clés existantes</CardTitle>
            <CreateKeyDialog onCreated={setCreated} />
          </CardHeader>
          <CardContent>
            {keys.isLoading && (
              <div className="space-y-2">
                {Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            )}
            {keys.isError && (
              <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {describeKeyError(keys.error as ApiError)}
              </p>
            )}
            {revokeError && (
              <p className="mb-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {revokeError}
              </p>
            )}
            {keys.data && keys.data.length === 0 && (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Aucune clé pour le moment.
              </p>
            )}
            {keys.data && keys.data.length > 0 && (
              <div className="overflow-hidden rounded-xl border">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Libellé</TableHead>
                      <TableHead>Préfixe</TableHead>
                      <TableHead>Rôle</TableHead>
                      <TableHead>Statut</TableHead>
                      <TableHead>Dernier usage</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {keys.data.map((key) => (
                      <TableRow key={key.id}>
                        <TableCell className="font-medium">{key.label}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          sts_{key.prefix}_…
                        </TableCell>
                        <TableCell className="text-muted-foreground">{key.role}</TableCell>
                        <TableCell>
                          <Badge
                            className={
                              key.is_active
                                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                                : "bg-muted text-muted-foreground"
                            }
                          >
                            {key.is_active ? "Active" : "Révoquée"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDate(key.last_used_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          {key.is_active && (
                            <ConfirmDialog
                              trigger={
                                <Button variant="outline" size="sm">
                                  Révoquer
                                </Button>
                              }
                              title="Révoquer cette clé ?"
                              description={`« ${key.label} » ne pourra plus authentifier de requêtes. Cette action est irréversible.`}
                              confirmLabel="Révoquer"
                              onConfirm={() => onRevoke(key)}
                            />
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
