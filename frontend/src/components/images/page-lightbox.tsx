import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

interface PageLightboxProps {
  src: string;
  rotation: number;
  alt: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Full-screen preview so an ambiguous page can be checked without doubt. */
export function PageLightbox({ src, rotation, alt, open, onOpenChange }: PageLightboxProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-[90vw] items-center justify-center border-none bg-transparent p-0 shadow-none ring-0 sm:max-w-[90vw]">
        <DialogTitle className="sr-only">{alt}</DialogTitle>
        <img
          src={src}
          alt={alt}
          className="max-h-[85vh] max-w-full object-contain"
          style={{ transform: `rotate(${rotation}deg)` }}
        />
      </DialogContent>
    </Dialog>
  );
}
