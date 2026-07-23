interface PageLightboxProps {
  src: string;
  rotation: number;
  alt: string;
  onClose: () => void;
}

/** Full-screen preview so an ambiguous page can be checked without doubt. */
export function PageLightbox({ src, rotation, alt, onClose }: PageLightboxProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        onClick={onClose}
        className="absolute right-6 top-6 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        aria-label="Fermer"
      >
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      <img
        src={src}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] max-w-[90vw] object-contain shadow-2xl"
        style={{ transform: `rotate(${rotation}deg)` }}
      />
    </div>
  );
}
