import { KeyRound, Images, ScanLine } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { ThemeToggle } from "./theme-toggle";

const NAV_ITEMS = [
  { to: "/", label: "Documents", icon: ScanLine, end: true },
  { to: "/images", label: "Images → PDF", icon: Images, end: false },
  { to: "/admin", label: "Clés API", icon: KeyRound, end: false },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/85 backdrop-blur supports-backdrop-filter:bg-background/60">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4">
        <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <ScanLine className="size-5 text-primary" aria-hidden="true" />
          <span>ScanToSheet</span>
        </NavLink>

        <nav className="flex flex-1 items-center gap-1">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  isActive && "bg-accent text-accent-foreground",
                )
              }
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        <ThemeToggle />
      </div>
    </header>
  );
}
