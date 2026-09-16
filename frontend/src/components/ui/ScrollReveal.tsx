import { Children, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { useScrollReveal } from "@/hooks/useScrollReveal";

type Direction = "up" | "left" | "right";

const directionOffset: Record<Direction, { x: number; y: number }> = {
  up: { x: 0, y: 24 },
  left: { x: -24, y: 0 },
  right: { x: 24, y: 0 },
};

export function ScrollReveal({ children, delay = 0, direction = "up" }: { children: ReactNode; delay?: number; direction?: Direction }) {
  const { ref, inView, prefersReducedMotion } = useScrollReveal();
  const offset = directionOffset[direction];

  return (
    <motion.div
      ref={ref}
      initial={prefersReducedMotion ? false : { opacity: 0, ...offset }}
      animate={inView ? { opacity: 1, x: 0, y: 0 } : { opacity: 0, ...offset }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.6, delay: prefersReducedMotion ? 0 : delay / 1000, ease: [0.25, 0.1, 0.25, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerReveal({ children, className }: { children: ReactNode; className?: string }) {
  const prefersReducedMotion = useReducedMotion();
  return (
    <motion.div
      initial={prefersReducedMotion ? false : "hidden"}
      whileInView="visible"
      viewport={{ amount: 0.12, once: true }}
      variants={{ hidden: {}, visible: { transition: prefersReducedMotion ? { duration: 0 } : { delayChildren: 0, staggerChildren: 0.08 } } }}
    >
      {Children.map(children, (child) => (
        <motion.div
          variants={{ hidden: { opacity: 0, y: prefersReducedMotion ? 0 : 24 }, visible: { opacity: 1, y: 0, transition: { duration: prefersReducedMotion ? 0 : 0.6, ease: [0.25, 0.1, 0.25, 1] } } }}
        >
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
}