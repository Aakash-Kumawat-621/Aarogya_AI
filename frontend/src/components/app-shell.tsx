import {
  Activity,
  BarChart3,
  ClipboardList,
  Home,
  LogOut,
  Menu,
  Settings,
  Stethoscope,
  UserRound,
  X,
} from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import { AnimatePresence } from "framer-motion";

import { Button } from "@/components/ui/button";
import { PageTransition } from "@/components/ui/PageTransition";
import { supabase } from "@/integrations/supabase/client";

const navItems = [
  { label: "Home", to: "/dashboard", icon: Home },
  { label: "Analyze", to: "/analyze", icon: Activity },
  { label: "Doctors", to: "/doctors", icon: Stethoscope },
  { label: "History", to: "/history", icon: ClipboardList },
  { label: "Profile", to: "/profile", icon: UserRound },
  { label: "Settings", to: "/settings", icon: Settings },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  async function handleSignOut() {
    await supabase.auth.signOut();
    await navigate({ to: "/home", replace: true });
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-sidebar/95 px-4 backdrop-blur lg:hidden">
        <Brand />
        <Button
          variant="ghost"
          size="icon"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <X /> : <Menu />}
        </Button>
      </header>

      <aside className="fixed inset-y-0 left-0 z-50 hidden w-60 flex-col border-r border-border bg-sidebar lg:flex">
        <Brand />
        <nav className="flex-1 space-y-1 px-3 py-6" aria-label="Primary navigation">
          {navItems.map((item) => (
            <NavItem key={item.to} item={item} active={location.pathname === item.to} />
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <Button
            variant="ghost"
            type="button"
            onClick={handleSignOut}
            className="btn-ghost h-auto w-full justify-start px-3 py-2.5 text-destructive hover:bg-destructive/10"
          >
            <LogOut className="size-4" />
            <span>Sign out</span>
          </Button>
          <div className="mt-3 flex items-center gap-3 rounded-md bg-surface-2 px-3 py-3">
            <div className="flex size-9 items-center justify-center rounded-full bg-teal-dim text-sm font-semibold text-teal">AK</div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">Aarogya user</p>
              <p className="truncate text-xs text-muted-text">Personal health space</p>
            </div>
          </div>
        </div>
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-30 bg-background/90 pt-20 backdrop-blur lg:hidden">
          <nav className="space-y-1 px-4" aria-label="Mobile navigation">
            {navItems.map((item) => (
              <NavItem key={item.to} item={item} active={location.pathname === item.to} onNavigate={() => setMobileOpen(false)} />
            ))}
          </nav>
        </div>
      ) : null}

      <main className="min-h-screen pt-16 lg:ml-60 lg:pt-0"><AnimatePresence mode="wait"><PageTransition key={location.pathname}>{children}</PageTransition></AnimatePresence></main>

      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-border bg-sidebar/95 p-2 backdrop-blur lg:hidden" aria-label="Mobile tab navigation">
        {navItems.slice(0, 3).concat(navItems[4]).map((item) => (
          <NavItem key={item.to} item={item} active={location.pathname === item.to} compact />
        ))}
      </nav>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex h-16 items-center gap-3 border-b border-border px-5">
      <div className="flex size-8 items-center justify-center rounded-md bg-teal text-sm font-bold text-primary-foreground">
        A
      </div>
      <div>
        <p className="text-sm font-semibold tracking-tight">Aarogya AI</p>
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-teal">care, clarified</p>
      </div>
    </div>
  );
}

function NavItem({ item, active, compact = false, onNavigate }: { item: (typeof navItems)[number]; active: boolean; compact?: boolean; onNavigate?: () => void }) {
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      className={`relative flex items-center justify-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors lg:justify-start ${
        active ? "bg-teal-dim text-teal" : "text-muted-text hover:bg-surface-2 hover:text-foreground"
      } ${compact ? "flex-col gap-1 px-2 py-1.5 text-[10px]" : ""}`}
    >
      {active ? <span className="absolute inset-y-0 left-0 w-0.5 rounded-full bg-teal" /> : null}
      <Icon className="size-4" />
      <span>{item.label}</span>
    </Link>
  );
}

export function PagePlaceholder({ name }: { name: string }) {
  return <div className="flex min-h-screen items-center justify-center px-6 text-xl font-medium">{name}</div>;
}

export function MetricPlaceholder({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-border bg-card p-5"><p className="text-sm text-muted-text">{label}</p><p className="mt-2 font-mono text-2xl text-teal">{value}</p></div>;
}

export function AnalyticsPlaceholder() {
  return <BarChart3 className="size-5 text-teal" />;
}