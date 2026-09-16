import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowRight, ClipboardList, HeartPulse, Stethoscope } from "lucide-react";

import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: "Health Dashboard — Aarogya AI" },
      { name: "description", content: "Start a health assessment and review your Aarogya AI activity." },
      { property: "og:title", content: "Health Dashboard — Aarogya AI" },
      { property: "og:description", content: "Start a health assessment and review your Aarogya AI activity." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: DashboardPage,
});

function DashboardPage() {
  const [name, setName] = useState("there");

  useEffect(() => {
    let active = true;
    void supabase.auth.getUser().then(({ data }) => {
      const fullName = data.user?.user_metadata?.["full_name"];
      const firstName = typeof fullName === "string" ? fullName.trim().split(/\s+/)[0] : "";
      if (active && firstName) setName(firstName);
    });
    return () => { active = false; };
  }, []);

  return (
    <>
      <main className="mx-auto w-full max-w-6xl px-6 py-10 lg:px-10 lg:py-14">
        <header className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Personal health space</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Welcome back, {name}</h1>
          <p className="mt-3 max-w-xl text-muted-text">Keep your next health decision clear, focused, and grounded in useful information.</p>
        </header>

        <section className="grid gap-4 md:grid-cols-[1.5fr_1fr_1fr]" aria-label="Dashboard overview">
          <div className="card-hover rounded-lg border border-teal/40 bg-teal-dim p-6">
            <div className="flex size-11 items-center justify-center rounded-md bg-teal text-primary-foreground"><HeartPulse className="size-5" /></div>
            <h2 className="mt-6 text-xl font-semibold">New Analysis</h2>
            <p className="mt-2 max-w-sm text-sm text-muted-text">Describe what you are experiencing and get a clear next step.</p>
            <Button asChild className="btn-primary mt-6"><Link to="/analyze">Begin assessment <ArrowRight /></Link></Button>
          </div>

          <StatCard icon={<ClipboardList />} label="Assessments Taken" value="0" />
          <StatCard icon={<Stethoscope />} label="Saved Doctors" value="0" />
        </section>

        <section className="mt-12" aria-labelledby="recent-history-heading">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Your activity</p>
              <h2 id="recent-history-heading" className="mt-2 text-2xl font-semibold">Recent history</h2>
            </div>
            <Link to="/history" className="hidden items-center gap-2 text-sm text-teal hover:underline sm:flex">View history <ArrowRight className="size-4" /></Link>
          </div>

          <div className="mt-5 flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/50 px-6 text-center">
            <ClipboardList className="size-8 text-dim" />
            <p className="mt-4 font-medium">No recent assessments.</p>
            <p className="mt-1 text-sm text-muted-text">Start one now to see your health journey here.</p>
            <Button asChild variant="ghost" className="btn-ghost mt-4 text-teal"><Link to="/analyze">Start an assessment <ArrowRight /></Link></Button>
          </div>
        </section>
      </main>
    </>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="card-hover rounded-lg border border-border bg-card p-6">
      <div className="flex size-10 items-center justify-center rounded-md bg-surface-2 text-teal">{icon}</div>
      <p className="mt-6 text-sm text-muted-text">{label}</p>
      <p className="mt-2 font-mono text-3xl text-foreground">{value}</p>
    </div>
  );
}