import { useCallback } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { Images } from "lucide-react";

import { cn } from "@/lib/utils";

interface ImageDropzoneProps {
  onFiles: (files: File[]) => void;
  onRejected?: (message: string) => void;
}

export function ImageDropzone({ onFiles, onRejected }: ImageDropzoneProps) {
  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      if (rejected.length > 0) {
        onRejected?.(rejected[0].errors[0]?.message ?? "Fichier refusé");
      }
      if (accepted.length > 0) {
        onFiles(accepted);
      }
    },
    [onFiles, onRejected],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "image/webp": [".webp"],
      "image/tiff": [".tif", ".tiff"],
      "image/bmp": [".bmp"],
    },
    multiple: true,
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
        isDragActive
          ? "border-primary bg-accent"
          : "border-border hover:border-primary/50 hover:bg-muted/50",
      )}
    >
      <input {...getInputProps()} />
      <Images className="mb-3 size-9 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm font-medium">
        {isDragActive
          ? "Déposez les images ici…"
          : "Glissez-déposez des images, ou cliquez pour parcourir"}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        JPEG, PNG, WEBP, TIFF, BMP · plusieurs fichiers à la fois
      </p>
    </div>
  );
}
