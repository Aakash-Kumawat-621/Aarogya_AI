import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

type CursorMode = "default" | "expand" | "text";

export function CustomCursor() {
  const cursorRef = useRef<HTMLDivElement>(null);
  const mouse = useRef({ x: -100, y: -100 });
  const current = useRef({ x: -100, y: -100 });
  const [mode, setMode] = useState<CursorMode>("default");
  const [pressed, setPressed] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const finePointer = window.matchMedia("(pointer: fine)").matches;
    if (navigator.maxTouchPoints > 0 || !finePointer || prefersReducedMotion) return;
    setEnabled(true);

    const onMove = (event: MouseEvent) => {
      mouse.current = { x: event.clientX, y: event.clientY };
      const target = event.target instanceof Element ? event.target : null;
      const override = target?.closest("[data-cursor]")?.getAttribute("data-cursor");
      if (override === "text") setMode("text");
      else if (override === "expand") setMode("expand");
      else if (target?.closest("input, textarea, [contenteditable='true']")) setMode("text");
      else if (target?.closest("a, button, [role='button']")) setMode("expand");
      else setMode("default");
    };
    const onDown = () => setPressed(true);
    const onUp = () => window.setTimeout(() => setPressed(false), 100);
    let frame = 0;
    const tick = () => {
      current.current.x += (mouse.current.x - current.current.x) * 0.12;
      current.current.y += (mouse.current.y - current.current.y) * 0.12;
      if (cursorRef.current) {
        cursorRef.current.style.left = `${current.current.x}px`;
        cursorRef.current.style.top = `${current.current.y}px`;
      }
      frame = requestAnimationFrame(tick);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
    };
  }, [prefersReducedMotion]);

  if (!enabled) return null;
  const expanded = mode === "expand";
  return (
    <motion.div
      ref={cursorRef}
      aria-hidden="true"
      className="pointer-events-none fixed z-[9999] rounded-full"
      animate={{
        width: expanded ? 40 : 8,
        height: expanded ? 40 : 8,
        opacity: mode === "text" ? 0 : 0.8,
        scale: pressed ? 0.7 : 1,
        backgroundColor: expanded ? "var(--cursor-clear)" : "var(--teal)",
        borderWidth: expanded ? 2 : 0,
        borderColor: "var(--teal)",
      }}
      transition={{ duration: pressed ? 0.1 : 0.2 }}
      style={{ transform: "translate(-50%, -50%)", borderStyle: "solid" }}
    />
  );
}