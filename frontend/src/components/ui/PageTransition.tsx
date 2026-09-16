import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

export function PageTransition({ children }: { children: ReactNode }) {
  const prefersReducedMotion = useReducedMotion();
  return (
    <motion.div
      className="min-h-full"
      initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={prefersReducedMotion ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.97 }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.25, ease: "easeInOut" }}
    >
      {children}
    </motion.div>
  );
}