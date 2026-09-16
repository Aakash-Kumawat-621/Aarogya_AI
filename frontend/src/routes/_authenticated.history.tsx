import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, ClipboardList } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_authenticated/history")({
  head: () => ({ meta: [
    { title: "Health History — Aarogya AI" },
    { name: "description", content: "Review your past Aarogya AI health assessments." },
    { property: "og:title", content: "Health History — Aarogya AI" },
    { property: "og:description", content: "Review your past Aarogya AI health assessments." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: HistoryPage,
});

const assessments = [
  { id: "assessment-1", date: "18 Sep 2026", concern: "Fever and fatigue", urgency: "Moderate", color: "moderate" },
  { id: "assessment-2", date: "02 Sep 2026", concern: "Seasonal allergies", urgency: "Low", color: "low" },
  { id: "assessment-3", date: "21 Aug 2026", concern: "Persistent cough", urgency: "Urgent", color: "urgent" },
];

function HistoryPage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl px-6 py-10 lg:px-10 lg:py-14">
        <header className="mb-10"><p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Your activity</p><h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Health history</h1><p className="mt-3 max-w-2xl text-muted-text">Revisit your past assessments and keep your next conversation with a clinician focused.</p></header>
        <section aria-labelledby="assessments-heading"><div className="flex items-center justify-between"><h2 id="assessments-heading" className="text-xl font-semibold">Past assessments</h2><span className="font-mono text-xs text-muted-text">{assessments.length} records</span></div>
          <div className="mt-5 space-y-3">{assessments.map((assessment) => <Link key={assessment.id} to="/results/$id" params={{ id: assessment.id }} className="card-hover flex flex-col gap-4 rounded-lg border border-border bg-card p-5 transition-colors hover:bg-surface-2 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-start gap-4"><div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-teal-dim text-teal"><ClipboardList className="size-5" /></div><div><p className="font-semibold">{assessment.concern}</p><p className="mt-1 text-sm text-muted-text">{assessment.date} · Assessment {assessment.id.split("-").pop()}</p></div></div><div className="flex items-center justify-between gap-4 sm:justify-end"><span className={`rounded-full border px-3 py-1 text-xs font-medium text-${assessment.color} border-${assessment.color}/30 bg-${assessment.color}/10`}>{assessment.urgency} urgency</span><ArrowRight className="size-4 text-teal" /></div></Link>)}</div>
        </section>
        <div className="mt-8 rounded-lg border border-dashed border-border bg-card/50 p-6 text-center"><p className="text-sm text-muted-text">Want to add a new assessment?</p><Button asChild className="btn-primary mt-4"><Link to="/analyze">Start an assessment <ArrowRight /></Link></Button></div>
      </div>
    </AppShell>
  );
}