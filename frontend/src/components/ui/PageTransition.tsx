import type { ReactNode } from "react";

/**
 * Pure CSS page transition — fades + slides up on mount.
 * Uses CSS @keyframes which are immune to TanStack Router's
 * context-switching issues that broke Framer Motion AnimatePresence.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <div className="page-enter min-h-full">
      {children}
    </div>
  );
}