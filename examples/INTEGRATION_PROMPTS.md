# Prompts d'intégration ScanToSheet — Laravel (backend) + React (frontend)

Architecture cible :

```text
React  ──►  Laravel (détient la clé API)  ──►  ScanToSheet
  ▲                    ▲
  └── statut ──────────┘◄── webhook (callback signé HMAC)
```

**Le React n'appelle jamais ScanToSheet directement.** La clé API reste dans
Laravel : tout code JS livré au navigateur est public, une clé qui y transiterait
serait lisible par n'importe quel utilisateur.

Conséquence utile : Laravel peut **recevoir le webhook** de ScanToSheet, donc
aucun polling vers ScanToSheet n'est nécessaire.

---

## 0. À configurer côté ScanToSheet (avant tout)

```bash
AUTH_ENABLED=true          # sinon l'API documents est ouverte à tous
PUBLIC_BASE_URL=https://scantosheet.mon-domaine.fr   # liens envoyés dans le webhook
WEBHOOK_SECRET=<32 octets hex>                        # signature des callbacks
```

Générer la clé destinée à Laravel :

```bash
curl -X POST https://scantosheet.mon-domaine.fr/api/admin/keys \
  -H "X-API-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"label": "Backend Laravel", "role": "user"}'
```

> `CORS_ORIGINS` de ScanToSheet n'a **pas** besoin d'être modifié : seul Laravel
> l'appelle, en serveur-à-serveur, et le CORS ne concerne que les navigateurs.
> C'est le CORS **de Laravel** qui doit autoriser l'origine du React.

---

## 1. Prompt — backend Laravel

````text
Tu intègres ScanToSheet — une API REST auto-hébergée qui convertit des PDF
scannés en tableaux Excel par OCR — dans cette application Laravel. Laravel sert
de backend-for-frontend : il détient la clé API, expose des routes internes à
notre SPA React, et reçoit les callbacks de fin de traitement.

## Configuration

Ajoute dans `.env` et un `config/scantosheet.php` dédié (jamais d'appel direct à
env() hors config) :

  SCANTOSHEET_URL=https://scantosheet.mon-domaine.fr
  SCANTOSHEET_API_KEY=sts_xxx_yyy
  SCANTOSHEET_WEBHOOK_SECRET=<le même secret que WEBHOOK_SECRET côté ScanToSheet>

## Service client

Crée `App\Services\ScanToSheet\ScanToSheetClient` utilisant `Http::` :

- en-tête `X-API-Key` injecté systématiquement
- `timeout(120)` sur l'upload (gros PDF), `timeout(30)` ailleurs
- `throw()` désactivé : mappe les codes en exceptions métier explicites
  (`ScanToSheetException` avec le champ `detail` renvoyé par l'API)

Méthodes :

  upload(UploadedFile $file, string $language, bool $preprocessing,
         bool $mergePages, string $callbackUrl): array
  get(int $id): array
  preview(int $id): array
  download(int $id, string $fmt = 'xlsx'): StreamInterface
  delete(int $id): void

Upload multipart :

  Http::withHeaders(['X-API-Key' => config('scantosheet.api_key')])
    ->timeout(120)
    ->attach('file', $file->get(), $file->getClientOriginalName())
    ->post(config('scantosheet.url').'/api/documents', [
        'language'      => $language,
        'preprocessing' => $preprocessing ? 'true' : 'false',
        'merge_pages'   => $mergePages ? 'true' : 'false',
        'callback_url'  => $callbackUrl,
    ]);

## Persistance locale

Migration + modèle `OcrDocument` faisant le lien entre NOTRE utilisateur et le
document distant — sans cela, n'importe quel utilisateur connecté pourrait lire
les extractions d'un autre :

  id, user_id (FK), scantosheet_id (unique), filename, status,
  page_count, error_message, completed_at, timestamps

Toutes les lectures doivent être filtrées par `user_id` (policy ou global scope).

## Routes internes consommées par le React

  POST   /api/ocr/documents            upload (auth requise)
  GET    /api/ocr/documents            liste de l'utilisateur courant
  GET    /api/ocr/documents/{id}       statut + données
  GET    /api/ocr/documents/{id}/download?fmt=xlsx|csv
  DELETE /api/ocr/documents/{id}

`{id}` est l'id LOCAL, jamais l'id ScanToSheet : ne laisse pas le client choisir
l'identifiant distant.

Le téléchargement doit streamer sans charger le fichier en mémoire :

  return response()->streamDownload(
      fn () => print($client->download($doc->scantosheet_id, $fmt)),
      "{$doc->filename}_extracted.{$fmt}"
  );

## Webhook — le point sensible

Route publique `POST /api/ocr/webhook` (dans `routes/api.php`, donc sans session
ni CSRF ; si tu la places ailleurs, exclus-la explicitement du CSRF).

Elle DOIT vérifier la signature avant toute chose, sinon n'importe qui
connaissant l'URL peut marquer des documents comme terminés :

  $raw       = $request->getContent();          // corps BRUT, jamais ré-encodé
  $timestamp = $request->header('X-ScanToSheet-Timestamp');
  $signature = $request->header('X-ScanToSheet-Signature'); // "sha256=<hex>"

  $expected = hash_hmac('sha256', $timestamp.'.'.$raw,
                        config('scantosheet.webhook_secret'));

  abort_unless(
      $signature && hash_equals($expected, substr($signature, 7)),
      401
  );
  abort_if(abs(time() - (int) $timestamp) > 300, 401); // anti-rejeu

Payload reçu :

  {
    "event": "document.completed" | "document.failed",
    "document_id": 12, "filename": "scan.pdf", "status": "done",
    "page_count": 16, "language": "fra", "error_message": null,
    "download_url": "...", "download_csv_url": "...", "preview_url": "..."
  }

Traitement : retrouver l'`OcrDocument` par `scantosheet_id`, mettre à jour
`status`/`page_count`/`error_message`, puis **répondre 200 immédiatement** et
faire le reste en job asynchrone. ScanToSheet abandonne après 10 s et réessaie
3 fois (backoff 1s/3s/9s) sur 5xx ; un 4xx est un rejet définitif, sans retry.

La livraison n'est pas garantie : prévois une commande artisan de
réconciliation qui interroge ScanToSheet pour les documents restés `queued` ou
`processing` au-delà de N minutes.

## Notification du front

Diffuse un événement `OcrDocumentUpdated` (broadcasting/Echo) vers le
canal privé de l'utilisateur, pour que le React se mette à jour sans poller.
Si le broadcasting n'est pas en place, expose un endpoint de statut léger que le
React interroge — mais dis-le-moi, car c'est un repli, pas la cible.

## Divers

- CORS Laravel : autoriser l'origine du React (`config/cors.php`), et exposer
  `Content-Disposition` sinon le front ne pourra pas lire le nom du fichier.
- Validation d'upload : `mimes:pdf`, `max:51200` (50 Mo), avant tout appel réseau.
- Tests : signature de webhook valide/invalide/périmée, cloisonnement par
  utilisateur, upload d'un non-PDF rejeté, réponse 409 si téléchargement
  demandé avant la fin.

Commence par me proposer un plan et la structure de fichiers avant de coder.
````

---

## 2. Prompt — frontend React

````text
Tu implémentes l'interface d'un module OCR dans cette application React +
TypeScript. Le backend Laravel expose déjà les routes ci-dessous et détient
seul la clé de l'API OCR : ce code ne doit contenir AUCUNE clé API et ne jamais
appeler le service OCR directement.

## Endpoints du backend Laravel

  POST   /api/ocr/documents            multipart: file, language, preprocessing,
                                       merge_pages
  GET    /api/ocr/documents            -> OcrDocument[]
  GET    /api/ocr/documents/{id}       -> OcrDocumentDetail
  GET    /api/ocr/documents/{id}/download?fmt=xlsx|csv
  DELETE /api/ocr/documents/{id}

## Types

  type OcrStatus = "queued" | "processing" | "done" | "error";

  interface Cell { value: string; confidence: number }

  interface PageData {
    page_number: number;
    data: Cell[][];
    mean_confidence: number;
    warning: string | null;
  }

  interface OcrDocument {
    id: number;
    filename: string;
    status: OcrStatus;
    page_count: number;
    error_message: string | null;
    created_at: string;
  }

  interface OcrDocumentDetail extends OcrDocument { pages: PageData[] }

## Fonctionnalités

1. Client API typé centralisé (un module), zéro `any`.
2. Upload par glisser-déposer : PDF uniquement, 50 Mo max, barre de progression.
   Options : langue (français, anglais, arabe, français+anglais), prétraitement
   d'image, fusionner les pages.
3. Liste des documents avec badge de statut, tri par date, suppression.
4. Aperçu : tableau éditable, cellules dont `confidence < 70` mises en évidence,
   navigation page par page.
5. Téléchargement Excel et CSV.
6. Erreurs : afficher le message renvoyé par le backend.

## Contraintes techniques impératives

- **Le traitement est asynchrone** : après l'upload le document est `queued`.
  N'affiche pas de données tant que `status !== "done"`. Le backend nous notifie
  par websocket (Laravel Echo) — abonne-toi au canal privé de l'utilisateur et
  mets à jour le cache à réception. N'implémente du polling QUE si le
  broadcasting n'est pas disponible, avec un intervalle de 2 s et un timeout.

- **Le téléchargement ne peut pas être un `<a href>`** si les requêtes portent
  des en-têtes d'authentification (token Bearer, XSRF). Passe par `fetch` puis
  un Blob, et lis le nom dans `Content-Disposition` :

    const res = await fetch(url, { headers, credentials: "include" });
    if (!res.ok) throw new Error((await res.json()).message);
    const name = res.headers.get("Content-Disposition")
      ?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)?.[1];
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = decodeURIComponent(name ?? "export.xlsx");
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(objectUrl);

- **Barre de progression** : `fetch` n'expose pas la progression d'envoi. Utilise
  `XMLHttpRequest` avec `xhr.upload.onprogress` pour le POST uniquement.

- Un document en `error` doit afficher `error_message`, pas un écran vide.

## Livrables

- Client API typé + hooks de données (React Query ou équivalent)
- Composants : dropzone, liste, aperçu éditable
- Tests : passage à `done` via l'événement temps réel, gestion du statut `error`,
  rejet d'un fichier non-PDF, déclenchement du téléchargement

Commence par me proposer un plan et la structure de fichiers avant de coder.
````
