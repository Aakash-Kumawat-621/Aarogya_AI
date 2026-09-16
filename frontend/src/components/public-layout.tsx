import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "@tanstack/react-router";

import { Button } from "@/components/ui/button";
import { PageTransition } from "@/components/ui/PageTransition";

const links = [
  { label: "Home", to: "/home" },
  { label: "Sign in", to: "/login" },
  { label: "Sign up", to: "/signup" },
] as const;

export function PublicLayout({ children }: { children: ReactNode }) {
  const [compact, setCompact] = useState(false);
  const location = useLocation();
  useEffect(() => {
    const onScroll = () => setCompact(window.scrollY > 60);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className={`fixed inset-x-0 top-0 z-40 border-b transition-[background-color,backdrop-filter,padding,border-color] duration-300 ${compact ? "border-border bg-background/85 py-3 backdrop-blur-xl" : "border-transparent bg-transparent py-5"}`}>
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5">
          <Link to="/home" className="flex items-center gap-3" aria-label="Aarogya AI home">
            <span className="flex size-9 items-center justify-center rounded-md bg-teal font-bold text-primary-foreground">A</span>
            <span className="font-semibold">Aarogya AI</span>
          </Link>
          <nav className="flex items-center gap-2 sm:gap-5" aria-label="Public navigation">
            {links.map((link) => {
              const active = location.pathname === link.to;
              return link.to === "/signup" ? (
                <Button key={link.to} asChild size="sm" className="btn-primary"><Link to={link.to}>{link.label}</Link></Button>
              ) : (
                <Link key={link.to} to={link.to} className={`public-nav-link px-1 py-2 text-sm text-muted-text hover:text-foreground ${active ? "is-active text-foreground" : ""}`}>{link.label}</Link>
              );
            })}
          </nav>
        </div>
      </header>
      <PageTransition key={location.pathname}>{children}</PageTransition>
    </div>
  );
}