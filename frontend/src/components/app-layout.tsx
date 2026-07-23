import { Outlet } from "react-router-dom";

import { Toaster } from "@/components/ui/sonner";
import { SiteHeader } from "./site-header";

export function AppLayout() {
  return (
    <div className="min-h-dvh bg-background">
      <SiteHeader />
      <main>
        <Outlet />
      </main>
      <Toaster />
    </div>
  );
}
