import { useRef } from "react";
import { useInView, useReducedMotion } from "framer-motion";

export function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.12, once: true });
  const prefersReducedMotion = useReducedMotion();

  return {
    ref,
    inView: prefersReducedMotion ? true : inView,
    prefersReducedMotion: Boolean(prefersReducedMotion),
  };
}