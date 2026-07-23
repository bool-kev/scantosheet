import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";

import { clearApiKey, getApiKey, setApiKey } from "../api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
    <Card>
      <CardHeader>
        <CardTitle>Clé administrateur</CardTitle>
        <CardDescription>
          Requise pour gérer les clés. Envoyée dans l'en-tête <code>X-API-Key</code> et
          stockée dans ce navigateur uniquement.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Label htmlFor="admin-key" className="sr-only">
          Clé administrateur
        </Label>
        <div className="flex flex-wrap gap-2">
          <Input
            id="admin-key"
            type={reveal ? "text" : "password"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="sts_…"
            autoComplete="off"
            spellCheck={false}
            className="min-w-0 flex-1 font-mono"
          />
          <Button type="button" variant="outline" size="icon" onClick={() => setReveal((r) => !r)}>
            {reveal ? <EyeOff /> : <Eye />}
            <span className="sr-only">{reveal ? "Masquer" : "Afficher"}</span>
          </Button>
          <Button type="button" onClick={() => persist(value)}>
            Enregistrer
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              clearApiKey();
              setValue("");
              queryClient.invalidateQueries();
            }}
          >
            Effacer
          </Button>
        </div>
        {saved && <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">Clé enregistrée.</p>}
      </CardContent>
    </Card>
  );
}
