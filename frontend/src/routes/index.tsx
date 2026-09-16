import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion, useReducedMotion } from "framer-motion";
import { useEffect } from "react";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [{ title: "Aarogya AI — Personal Health Intelligence" }, { name: "description", content: "Private AI-assisted health guidance and clearer next steps." }, { property: "og:title", content: "Aarogya AI — Personal Health Intelligence" }, { property: "og:description", content: "Private AI-assisted health guidance and clearer next steps." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: SplashScreen,
});

function SplashScreen() {
  const navigate = useNavigate();
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void navigate({ to: "/home", replace: true });
    }, 2500);

    return () => window.clearTimeout(timeout);
  }, [navigate]);

  return (
    <main className="flex min-h-screen items-center justify-center overflow-hidden bg-background px-6" aria-label="Aarogya AI loading">
      <motion.div
        className="text-center"
        initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.94 }}
        animate={{ opacity: 1, scale: prefersReducedMotion ? 1 : [1, 1.025, 1] }}
        transition={{ opacity: { duration: 0.65 }, scale: { duration: 2, repeat: prefersReducedMotion ? 0 : Infinity, ease: "easeInOut" } }}
      >
        <div className="text-4xl font-bold text-teal sm:text-5xl">
          Aarogya<span className="text-foreground">AI</span>
        </div>
        <div className="mx-auto mt-5 h-px w-20 bg-teal/60" />
      </motion.div>
    </main>
  );
}
