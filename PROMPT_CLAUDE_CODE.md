# Prompt d'initialisation — ScanToSheet

> Copie-colle ce prompt dans Claude Code pour bootstrapper le projet.

---

## Prompt

```
Tu es le lead developer du projet ScanToSheet. Lis le fichier CLAUDE.md à la racine du projet — il contient l'architecture, le stack technique, les conventions et les décisions de design. Lis aussi USER_STORIES.md pour comprendre les fonctionnalités attendues.

Ton objectif : implémenter le projet de manière incrémentale, en commençant par un MVP fonctionnel.

## Phase 1 — Fondations (commence ici)

1. Initialise la structure du projet telle que décrite dans CLAUDE.md
2. Crée le `docker-compose.yml` avec les services backend et frontend
3. Backend :
   - Initialise FastAPI avec le health check `/api/health`
   - Configure SQLAlchemy + SQLite avec le modèle `Document` (id, filename, status, page_count, language, created_at, updated_at)
   - Implémente l'endpoint `POST /api/documents` : upload du PDF, validation (type MIME, taille), sauvegarde sur disque, création en DB avec status "queued"
   - Implémente `GET /api/documents` : liste paginée des documents
4. Frontend :
   - Initialise React + Vite + TypeScript + Tailwind
   - Page d'accueil avec zone de drag-and-drop pour upload (react-dropzone)
   - Liste des documents uploadés avec leur statut
   - Client API typé dans `src/api/client.ts`
5. Dockerfiles pour backend et frontend, docker-compose fonctionnel

Quand la Phase 1 est terminée, je dois pouvoir faire `docker compose up --build` et :
- Voir l'interface sur http://localhost:5173
- Uploader un PDF
- Voir le document apparaître dans la liste avec statut "queued"

## Phase 2 — OCR Pipeline

1. Service `pdf.py` : convertir chaque page du PDF en image PNG (pdf2image, 300 DPI)
2. Service `preprocess.py` : pipeline d'amélioration d'image
   - Conversion en niveaux de gris
   - Binarisation (seuillage adaptatif)
   - Suppression du bruit (filtre médian)
   - Correction d'inclinaison (deskew)
3. Service `ocr.py` : extraction de texte via pytesseract
   - Retourne le texte + données de confiance par mot (image_to_data)
   - Support multi-langues (fra, eng, ara)
4. Traitement asynchrone : quand un PDF est uploadé, lance le pipeline en BackgroundTask
   - Statut passe de "queued" → "processing" → "done" / "error"
5. Endpoint `GET /api/documents/{id}` retourne le texte OCR extrait

## Phase 3 — Détection de tableaux & structuration

1. Service `table.py` :
   - Détection de lignes horizontales/verticales via OpenCV (HoughLinesP ou morphologie)
   - Reconstruction de la grille (intersections → cellules)
   - Mapping du texte OCR dans les cellules correspondantes
   - Fallback : si pas de tableau détecté, structurer le texte ligne par ligne (split par espaces/tabs)
2. Endpoint `GET /api/documents/{id}/preview` : retourne les données structurées page par page (JSON array of arrays)
3. Frontend : page de preview avec tableau HTML éditable, cellules à faible confiance en surbrillance

## Phase 4 — Export Excel

1. Service `excel.py` :
   - Génère un `.xlsx` avec openpyxl
   - Option : 1 feuille par page ou tout fusionné
   - Auto-dimensionnement des colonnes
   - En-têtes en gras
2. Endpoint `GET /api/documents/{id}/download`
3. Endpoint `PUT /api/documents/{id}/data` pour corriger les données avant export
4. Frontend : boutons de téléchargement (Excel / CSV) sur la page de preview

## Contraintes techniques

- Zéro appels API externes. Tout tourne en local.
- Vérifie les magic bytes des fichiers uploadés, pas seulement l'extension.
- Gère les erreurs proprement : si l'OCR échoue sur une page, continue avec les autres et remonte un warning.
- Chaque service doit être testable indépendamment.
- Utilise des logs structurés (structlog) pour faciliter le debug.
- Garde le Dockerfile backend léger : installe Tesseract et Poppler via apt, pas de compilation depuis les sources.

## Style de travail

- Implémente phase par phase. Ne passe à la suivante que quand la phase actuelle fonctionne.
- Après chaque phase, donne-moi les commandes pour tester.
- Si un choix technique n'est pas clair, propose 2 options avec les trade-offs et demande-moi.
- Commit après chaque phase avec un message conventionnel.
```

---

## Utilisation

1. Crée un dossier `scantosheet/`
2. Place `CLAUDE.md` et `USER_STORIES.md` à la racine
3. Ouvre Claude Code dans ce dossier : `claude`
4. Colle le prompt ci-dessus
5. Laisse Claude Code implémenter phase par phase

## Commandes utiles pendant le développement

```bash
# Lancer le stack complet
docker compose up --build

# Lancer uniquement le backend en dev (hors Docker)
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# Lancer uniquement le frontend en dev
cd frontend && npm install && npm run dev

# Tester l'upload via curl
curl -X POST http://localhost:8000/api/documents \
  -F "file=@scan_test.pdf" \
  -F "language=fra"

# Voir les logs OCR
docker compose logs -f backend
```
