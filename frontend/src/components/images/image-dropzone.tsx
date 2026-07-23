import { useCallback } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";

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
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition ${
        isDragActive
          ? "border-brand-500 bg-brand-50"
          : "border-slate-300 hover:border-brand-500 hover:bg-slate-50"
      }`}
    >
      <input {...getInputProps()} />
      <svg
        className="mb-3 h-10 w-10 text-slate-400"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3 12V6.75A2.25 2.25 0 015.25 4.5h13.5A2.25 2.25 0 0121 6.75V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15v-1.5zM10.5 8.25h.008v.008h-.008V8.25z"
        />
      </svg>
      <p className="text-sm font-medium text-slate-700">
        {isDragActive
          ? "Déposez les images ici…"
          : "Glissez-déposez des images, ou cliquez pour parcourir"}
      </p>
      <p className="mt-1 text-xs text-slate-400">
        JPEG, PNG, WEBP, TIFF, BMP · plusieurs fichiers à la fois
      </p>
    </div>
  );
}
