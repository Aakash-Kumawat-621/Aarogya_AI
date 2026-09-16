import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Info, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PageLoadingSkeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/_authenticated/results/$id")({
  head: () => ({
    meta: [
      { title: "Analysis Results — Aarogya AI" },
      { name: "description", content: "Review your guided Aarogya AI symptom assessment and next steps." },
      { property: "og:title", content: "Analysis Results — Aarogya AI" },
      { property: "og:description", content: "Review your guided Aarogya AI symptom assessment and next steps." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ResultsPage,
});

function ResultsPage() {
  const { id } = Route.useParams();
  if (!id) return <PageLoadingSkeleton />;

  const [resultData, setResultData] = useState<{ diagnosis: any, urgency: any } | null>(null);
  
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("latest_diagnosis");
      if (stored) {
        setResultData(JSON.parse(stored));
      }
    } catch (e) {}
  }, []);
  
  const conditionName = resultData?.diagnosis?.condition_name || "Viral Fever";
  const confidence = resultData?.diagnosis?.confidence || 85;
  const urgencyLevel = resultData?.urgency?.level || "moderate";
  const explanation = resultData?.diagnosis?.explanation || "Your symptoms are most consistent with a viral infection that may be causing fever and fatigue. Most cases improve with rest, hydration, and careful monitoring, but a clinician can help confirm the cause and guide treatment.";

  return (
    <>
      <main className="mx-auto w-full max-w-5xl px-6 py-10 lg:px-10 lg:py-14">
        <header className="mb-10 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Assessment complete</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Your analysis results</h1>
            <p className="mt-3 text-sm text-muted-text">A starting point for your next health decision · Assessment {id}</p>
          </div>
          <div className="flex items-center gap-2 text-sm text-low"><CheckCircle2 className="size-4" /> Ready to review</div>
        </header>

        <section className="rounded-lg border border-border bg-card p-6 sm:p-8" aria-labelledby="diagnosis-heading">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm text-muted-text">Diagnosis match</p>
              <h2 id="diagnosis-heading" className="mt-2 text-2xl font-semibold sm:text-3xl">{conditionName}</h2>
              <p className="mt-2 text-sm text-muted-text">Based on the symptoms shared in this assessment.</p>
            </div>
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-moderate/40 bg-moderate/10 px-3 py-1.5 text-sm text-moderate"><AlertTriangle className="size-4" /> {urgencyLevel.charAt(0).toUpperCase() + urgencyLevel.slice(1)} urgency</span>
          </div>
          <div className="mt-8 max-w-2xl">
            <div className="flex items-center justify-between text-sm"><span className="text-muted-text">Confidence</span><span className="font-mono text-teal">{confidence}%</span></div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-2"><div className="h-full w-[85%] rounded-full bg-teal" /></div>
          </div>
        </section>

        <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-lg border border-border bg-card p-6 sm:p-8" aria-labelledby="explanation-heading">
            <div className="flex items-center gap-3"><div className="flex size-9 items-center justify-center rounded-md bg-teal-dim text-teal"><Info className="size-4" /></div><h2 id="explanation-heading" className="text-xl font-semibold">What this may mean</h2></div>
            <p className="mt-6 leading-7 text-muted-text">Your symptoms are most consistent with a viral infection that may be causing fever and fatigue. Most cases improve with rest, hydration, and careful monitoring, but a clinician can help confirm the cause and guide treatment.</p>
          </section>
          <section className="rounded-lg border border-border bg-card p-6 sm:p-8" aria-labelledby="action-heading">
            <h2 id="action-heading" className="text-xl font-semibold">Recommended next steps</h2>
            <ul className="mt-6 space-y-4 text-sm text-muted-text">
              <li className="flex gap-3"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" />Rest and drink plenty of fluids.</li>
              <li className="flex gap-3"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" />Monitor your temperature and symptoms.</li>
              <li className="flex gap-3"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" />Speak with a general physician if symptoms continue.</li>
            </ul>
            <Button asChild className="btn-primary mt-7 w-full"><Link to="/doctors">Find Doctors <ArrowRight /></Link></Button>
          </section>
        </div>

        <aside className="mt-6 flex gap-4 rounded-lg border border-urgent/30 bg-urgent/10 p-5 text-sm text-muted-text" aria-label="Medical disclaimer"><ShieldAlert className="mt-0.5 size-5 shrink-0 text-urgent" /><p><span className="font-medium text-foreground">Important:</span> This AI-generated assessment is for informational purposes only and is not a diagnosis or substitute for professional medical advice. Seek urgent care for severe or rapidly worsening symptoms.</p></aside>
      </main>
    </>
  );
}