import { Link } from "react-router-dom";

import { DocumentList } from "../components/document-list";
import { UploadDropzone } from "../components/upload-dropzone";

export function HomePage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">ScanToSheet</h1>
          <p className="mt-1 text-slate-500">
            Convertissez vos PDF scannés en tableaux Excel grâce à l'OCR — 100 % en local.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/images"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Images → PDF
          </Link>
          <Link
            to="/admin"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Clés API
          </Link>
        </div>
      </header>

      <section className="mb-10">
        <UploadDropzone />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Historique</h2>
        <DocumentList />
      </section>
    </div>
  );
}
