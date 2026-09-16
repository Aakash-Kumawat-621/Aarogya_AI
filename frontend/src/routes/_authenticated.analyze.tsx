import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, FileText, Image, LoaderCircle, UploadCloud, MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { startSession, respondSession } from "@/api/mediassist";
import type { ConversationResponse, FollowUpQuestion } from "@/types/api.types";

export const Route = createFileRoute("/_authenticated/analyze")({
  head: () => ({
    meta: [
      { title: "Analyze Symptoms — Aarogya AI" },
      { name: "description", content: "Share your symptoms with Aarogya AI for a guided health assessment." },
    ],
  }),
  component: AnalyzePage,
});

type Profile = { name: string; age: string; gender: string; conditions: string };

function AnalyzePage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [profile, setProfile] = useState<Profile>({ name: "", age: "", gender: "", conditions: "" });
  const [symptoms, setSymptoms] = useState("");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  
  const [sessionData, setSessionData] = useState<ConversationResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  function updateProfile(field: keyof Profile, value: string) {
    setProfile((prev) => ({ ...prev, [field]: value }));
  }

  async function submitInitialAnalysis(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    
    try {
      const formData = new FormData();
      formData.append("symptoms_text", symptoms);
      formData.append("patient", JSON.stringify(profile));
      
      const res = await startSession(formData);
      
      if (res.status === "needs_followup") {
        setSessionData(res);
        setStep(3);
      } else {
        if (res.diagnosis) {
          sessionStorage.setItem("latest_diagnosis", JSON.stringify({ diagnosis: res.diagnosis, urgency: res.urgency }));
        }
        await navigate({ to: "/results/$id", params: { id: res.session_id } });
      }
    } catch (err) {
      console.error(err);
      await navigate({ to: "/results/$id", params: { id: "mock-id" } });
    } finally {
      setSubmitting(false);
    }
  }

  async function submitChatAnswers(event: React.FormEvent) {
    event.preventDefault();
    if (!sessionData) return;
    setSubmitting(true);
    
    try {
      const res = await respondSession(sessionData.session_id, answers);
      if (res.status === "needs_followup") {
        setSessionData(res);
        setAnswers({});
      } else {
        if (res.diagnosis) {
          sessionStorage.setItem("latest_diagnosis", JSON.stringify({ diagnosis: res.diagnosis, urgency: res.urgency }));
        }
        await navigate({ to: "/results/$id", params: { id: res.session_id } });
      }
    } catch (err) {
      console.error(err);
      await navigate({ to: "/results/$id", params: { id: "mock-id" } });
    } finally {
      setSubmitting(false);
    }
  }

  if (submitting) return <AnalysisLoading />;

  return (
    <>
      <main className="mx-auto w-full max-w-4xl px-6 py-10 lg:px-10 lg:py-14">
        <header className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Guided assessment</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Analyze your symptoms</h1>
          <p className="mt-3 max-w-2xl text-muted-text">A few details help us give you a more useful, personalized starting point.</p>
        </header>

        <div className="mb-8" aria-label={`Step ${step} of 3`}>
          <div className="flex items-center justify-between text-sm">
            <span className={step >= 1 ? "font-medium text-teal" : "text-muted-text"}>
              <span className="mr-2 inline-flex size-6 items-center justify-center rounded-full bg-teal text-xs text-primary-foreground">{step > 1 ? <Check className="size-3.5" /> : "1"}</span>
              Patient profile
            </span>
            <span className={step >= 2 ? "font-medium text-teal" : "text-muted-text"}>
              <span className={step >= 2 ? "mr-2 inline-flex size-6 items-center justify-center rounded-full bg-teal text-xs text-primary-foreground" : "mr-2 inline-flex size-6 items-center justify-center rounded-full bg-surface-2 text-xs"}>{step > 2 ? <Check className="size-3.5" /> : "2"}</span>
              Symptoms & media
            </span>
            <span className={step === 3 ? "font-medium text-teal" : "text-muted-text"}>
              <span className={step === 3 ? "mr-2 inline-flex size-6 items-center justify-center rounded-full bg-teal text-xs text-primary-foreground" : "mr-2 inline-flex size-6 items-center justify-center rounded-full bg-surface-2 text-xs"}>3</span>
              Clarification
            </span>
          </div>
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-teal transition-all duration-300" style={{ width: step === 1 ? "33%" : step === 2 ? "66%" : "100%" }} />
          </div>
        </div>

        <form onSubmit={step === 1 ? (event) => { event.preventDefault(); setStep(2); } : step === 2 ? submitInitialAnalysis : submitChatAnswers} className="rounded-lg border border-border bg-card p-6 sm:p-8">
          {step === 1 && <ProfileStep profile={profile} updateProfile={updateProfile} />}
          {step === 2 && <SymptomsStep symptoms={symptoms} setSymptoms={setSymptoms} files={files} setFiles={setFiles} />}
          {step === 3 && sessionData && <ChatStep session={sessionData} answers={answers} setAnswers={setAnswers} />}
          
          <div className="mt-8 flex flex-col-reverse justify-between gap-3 border-t border-border pt-6 sm:flex-row">
            {step === 2 && <Button type="button" variant="ghost" className="btn-ghost" onClick={() => setStep(1)}><ArrowLeft /> Back</Button>}
            {step === 3 && <span />}
            {step === 1 && <span />}
            <Button type="submit" className="btn-primary">
              {step === 1 && <>Next <ArrowRight /></>}
              {step === 2 && <>Analyze Symptoms <ArrowRight /></>}
              {step === 3 && <>Submit Answers <ArrowRight /></>}
            </Button>
          </div>
        </form>
      </main>
    </>
  );
}

function ChatStep({ session, answers, setAnswers }: { session: ConversationResponse; answers: Record<string, string>; setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>> }) {
  return (
    <section aria-labelledby="chat-step-heading" className="animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-full bg-teal/20 text-teal"><MessageSquare className="size-5" /></div>
        <div>
          <h2 id="chat-step-heading" className="text-xl font-semibold">AI Clarification Needed</h2>
          <p className="text-sm text-teal">Turn {session.turn}</p>
        </div>
      </div>
      
      {session.initial_analysis && (
        <div className="mt-6 rounded-md bg-surface-2 p-4 text-sm leading-relaxed text-muted-text border-l-2 border-teal">
          {session.initial_analysis}
        </div>
      )}

      <div className="mt-8 space-y-6">
        {session.questions?.map((q) => (
          <div key={q.id} className="rounded-lg border border-border bg-background p-5 shadow-sm">
            <label className="block text-sm font-medium mb-3">{q.text}</label>
            {q.type === "multiple_choice" && q.options ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {q.options.map((opt) => (
                  <label key={opt} className={`flex cursor-pointer items-center rounded-md border p-3 transition-colors ${answers[q.id] === opt ? "border-teal bg-teal-dim text-teal font-medium" : "border-input hover:border-teal/50 hover:bg-surface-2"}`}>
                    <input type="radio" name={q.id} value={opt} checked={answers[q.id] === opt} onChange={(e) => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))} className="sr-only" required />
                    <span className="text-sm">{opt}</span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {["Yes", "No", "Not sure"].map((opt) => (
                  <label key={opt} className={`flex cursor-pointer items-center rounded-md border p-3 transition-colors ${answers[q.id] === opt ? "border-teal bg-teal-dim text-teal font-medium" : "border-input hover:border-teal/50 hover:bg-surface-2"}`}>
                    <input type="radio" name={q.id} value={opt} checked={answers[q.id] === opt} onChange={(e) => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))} className="sr-only" required />
                    <span className="text-sm">{opt}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function ProfileStep({ profile, updateProfile }: { profile: Profile; updateProfile: (field: keyof Profile, value: string) => void }) {
  return (
    <section aria-labelledby="profile-step-heading">
      <h2 id="profile-step-heading" className="text-xl font-semibold">Tell us about yourself</h2>
      <p className="mt-2 text-sm text-muted-text">This information helps place your symptoms in context.</p>
      <div className="mt-7 grid gap-5 sm:grid-cols-2">
        <Field label="Name" htmlFor="patient-name"><Input id="patient-name" value={profile.name} onChange={(event) => updateProfile("name", event.target.value)} placeholder="Your name" required /></Field>
        <Field label="Age" htmlFor="patient-age"><Input id="patient-age" type="number" min="1" max="120" value={profile.age} onChange={(event) => updateProfile("age", event.target.value)} placeholder="Age" required /></Field>
        <Field label="Gender" htmlFor="patient-gender"><select id="patient-gender" value={profile.gender} onChange={(event) => updateProfile("gender", event.target.value)} required className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"><option value="">Select gender</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="prefer-not-to-say">Prefer not to say</option></select></Field>
        <Field label="Existing conditions" htmlFor="patient-conditions"><Input id="patient-conditions" value={profile.conditions} onChange={(event) => updateProfile("conditions", event.target.value)} placeholder="e.g. asthma, diabetes" /></Field>
      </div>
    </section>
  );
}

function SymptomsStep({ symptoms, setSymptoms, files, setFiles }: { symptoms: string; setSymptoms: (value: string) => void; files: Record<string, string>; setFiles: React.Dispatch<React.SetStateAction<Record<string, string>>> }) {
  return (
    <section aria-labelledby="symptoms-step-heading">
      <h2 id="symptoms-step-heading" className="text-xl font-semibold">Describe what you are experiencing</h2>
      <p className="mt-2 text-sm text-muted-text">Include when it started, what makes it better or worse, and anything else you have noticed.</p>
      <label htmlFor="symptoms" className="mt-7 block text-sm font-medium">Symptoms in detail</label>
      <textarea id="symptoms" rows={6} minLength={10} value={symptoms} onChange={(event) => setSymptoms(event.target.value)} placeholder="Describe your symptoms in detail..." required className="mt-2 flex w-full resize-y rounded-md border border-input bg-background px-3 py-3 text-sm text-foreground shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
      <p className="mt-2 text-xs text-dim">Your information is used to prepare this assessment.</p>
      <div className="mt-7 grid gap-4 sm:grid-cols-3">
        <UploadZone label="X-Ray / Scan" name="scan" icon={<Image />} fileName={files["scan"]} setFiles={setFiles} />
        <UploadZone label="Body Photo" name="body-photo" icon={<UploadCloud />} fileName={files["body-photo"]} setFiles={setFiles} />
        <UploadZone label="Prescription" name="prescription" icon={<FileText />} fileName={files["prescription"]} setFiles={setFiles} />
      </div>
    </section>
  );
}

function UploadZone({ label, name, icon, fileName, setFiles }: { label: string; name: string; icon: React.ReactNode; fileName: string | undefined; setFiles: React.Dispatch<React.SetStateAction<Record<string, string>>> }) {
  return (
    <label htmlFor={name} className="flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-border bg-background px-3 py-5 text-center transition-colors hover:border-teal/60 hover:bg-teal-dim">
      <span className="text-teal">{icon}</span>
      <span className="mt-3 text-sm font-medium">{fileName || label}</span>
      <span className="mt-1 text-xs text-muted-text">Optional — upload file</span>
      <input id={name} type="file" className="sr-only" onChange={(event) => setFiles((current) => ({ ...current, [name]: event.target.files?.[0]?.name ?? "" }))} />
    </label>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return <label htmlFor={htmlFor} className="block text-sm font-medium">{label}<span className="mt-2 block">{children}</span></label>;
}

function AnalysisLoading() {
  return (
    <>
      <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-4xl flex-col justify-center px-6 py-12 lg:px-10">
        <div className="mx-auto w-full max-w-xl text-center" role="status" aria-label="Analyzing symptoms">
          <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-teal-dim text-teal"><LoaderCircle className="size-7 animate-spin" /></div>
          <h1 className="mt-6 text-2xl font-semibold">Reviewing your symptoms</h1>
          <p className="mt-2 text-muted-text">We are preparing your personalized assessment.</p>
          <div className="mt-10 space-y-4 rounded-lg border border-border bg-card p-6 text-left"><SkeletonText className="w-2/5" /><Skeleton className="h-7 w-4/5" /><SkeletonText className="w-full" /><SkeletonText className="w-3/4" /><Skeleton className="mt-4 h-20 w-full" /></div>
          <span className="sr-only">Analysis in progress</span>
        </div>
      </main>
    </>
  );
}
