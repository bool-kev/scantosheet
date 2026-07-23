import { DocumentList } from "../components/document-list";
import { UploadDropzone } from "../components/upload-dropzone";

export function HomePage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Documents</h1>
        <p className="mt-1 text-muted-foreground">
          Convertissez vos PDF scannés en tableaux Excel grâce à l'OCR — 100&nbsp;% en local.
        </p>
      </header>

      <section className="mb-10">
        <UploadDropzone />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Historique</h2>
        <DocumentList />
      </section>
    </div>
  );
}
