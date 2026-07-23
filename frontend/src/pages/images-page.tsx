import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { ApiError, api } from "../api/client";
import type { ImageBatchSummary } from "../api/types";
import { ImageDropzone } from "../components/images/image-dropzone";
import { PageGrid } from "../components/images/page-grid";
import { PdfOptionsBar } from "../components/images/pdf-options-bar";
import { SavedBatchesList } from "../components/images/saved-batches-list";
import { useImageBatch, useWarnBeforeUnload } from "../hooks/useImageBatch";
import { useSaveBatch } from "../hooks/useImagePdf";

export function ImagesPage() {
  const navigate = useNavigate();
  const batch = useImageBatch();
  useWarnBeforeUnload(batch.isDirty);
  const saveBatchMutation = useSaveBatch();

  const [createDocument, setCreateDocument] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);

  const handleOpenSavedBatch = async (summary: ImageBatchSummary) => {
    setError(null);
    try {
      const detail = await api.getBatch(summary.id);
      await batch.hydrate(detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'ouvrir ce lot");
    }
  };

  const handleGenerate = async () => {
    if (batch.items.length === 0) return;
    setError(null);
    setIsGenerating(true);
    setProgress(0);
    try {
      const result = await api.buildPdf(
        batch.items.map((item) => item.file),
        batch.items.map((item) => item.rotation),
        {
          quality: batch.quality,
          pageSize: batch.pageSize,
          filename: batch.name,
          createDocument,
          language: "fra",
          preprocessing: true,
          mergePages: false,
        },
        setProgress,
      );
      if (result.kind === "document") {
        toast.success("Document créé, extraction en cours…");
        navigate(`/documents/${result.document.id}`);
      } else {
        api.downloadBlobFile(result.blob, result.filename);
        toast.success("PDF généré et téléchargé.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Échec de la génération du PDF");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSave = () => {
    setError(null);
    saveBatchMutation.mutate(
      {
        files: batch.items.map((item) => item.file),
        rotations: batch.items.map((item) => item.rotation),
        options: { name: batch.name, quality: batch.quality, pageSize: batch.pageSize },
        onProgress: setProgress,
      },
      {
        onSuccess: (saved) => {
          batch.markSaved(saved.id);
          toast.success("Lot enregistré.");
        },
        onError: (err) => {
          setError(err instanceof ApiError ? err.message : "Échec de l'enregistrement du lot");
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Images → PDF</h1>
        <p className="mt-1 text-muted-foreground">
          Chargez des images, organisez-les en glisser-déposer, puis générez un PDF unique.
        </p>
      </header>

      <section className="mb-6">
        <ImageDropzone onFiles={batch.addFiles} onRejected={setError} />
      </section>

      <section className="mb-6">
        <PdfOptionsBar
          name={batch.name}
          onNameChange={batch.setName}
          quality={batch.quality}
          onQualityChange={batch.setQuality}
          pageSize={batch.pageSize}
          onPageSizeChange={batch.setPageSize}
          createDocument={createDocument}
          onCreateDocumentChange={setCreateDocument}
          onSortByName={batch.sortByName}
          onSortByDate={batch.sortByDate}
          onGenerate={handleGenerate}
          onSave={handleSave}
          disabled={batch.items.length === 0}
          isGenerating={isGenerating}
          isSaving={saveBatchMutation.isPending}
          progress={progress}
        />
      </section>

      {error && (
        <p className="mb-6 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <section className="mb-10">
        <PageGrid
          items={batch.items}
          onMove={batch.move}
          onRotate={batch.rotate}
          onRemove={batch.remove}
          onSetPosition={batch.setPosition}
        />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Lots enregistrés</h2>
        <SavedBatchesList onOpen={handleOpenSavedBatch} />
      </section>
    </div>
  );
}
