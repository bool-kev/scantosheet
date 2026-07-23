import { Outlet } from "react-router-dom";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SiteHeader } from "./site-header";

export function AppLayout() {
  return (
    <TooltipProvider>
      <div className="min-h-dvh bg-background">
        <SiteHeader />
        <main>
          <Outlet />
        </main>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}
