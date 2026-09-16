import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Bell, Mail, MessageSquare, Trash2 } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/Toast";

export const Route = createFileRoute("/_authenticated/settings")({
  head: () => ({ meta: [
    { title: "Settings — Aarogya AI" },
    { name: "description", content: "Manage notifications and account settings in Aarogya AI." },
    { property: "og:title", content: "Settings — Aarogya AI" },
    { property: "og:description", content: "Manage notifications and account settings in Aarogya AI." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: SettingsPage,
});

function SettingsPage() {
  const [emailAlerts, setEmailAlerts] = useState(true);
  const [smsAlerts, setSmsAlerts] = useState(false);
  const { showToast } = useToast();

  function requestDelete() {
    showToast("Account deletion requests are handled by our support team.", "info");
  }

  return <AppShell><div className="mx-auto w-full max-w-3xl px-6 py-10 lg:px-10 lg:py-14"><header className="mb-10"><p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Preferences</p><h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Settings</h1><p className="mt-3 text-muted-text">Choose how Aarogya AI keeps you informed.</p></header><section className="rounded-lg border border-border bg-card p-6 sm:p-8" aria-labelledby="notification-heading"><div className="flex items-center gap-3"><div className="flex size-11 items-center justify-center rounded-md bg-teal-dim text-teal"><Bell /></div><div><h2 id="notification-heading" className="font-semibold">Notifications</h2><p className="text-sm text-muted-text">You can change these preferences anytime.</p></div></div><div className="mt-8 divide-y divide-border"><ToggleRow id="email-alerts" icon={<Mail />} label="Email alerts" description="Receive assessment updates and care reminders by email." checked={emailAlerts} onChange={setEmailAlerts} /><ToggleRow id="sms-alerts" icon={<MessageSquare />} label="SMS alerts" description="Receive time-sensitive reminders by text message." checked={smsAlerts} onChange={setSmsAlerts} /></div></section><section className="mt-6 rounded-lg border border-emergency/30 bg-emergency/5 p-6 sm:p-8" aria-labelledby="danger-heading"><div className="flex items-center gap-3 text-emergency"><Trash2 className="size-5" /><h2 id="danger-heading" className="font-semibold">Danger zone</h2></div><p className="mt-3 max-w-xl text-sm text-muted-text">Deleting your account permanently removes your saved health information and cannot be undone.</p><Button type="button" variant="destructive" className="mt-5" onClick={requestDelete}>Delete Account</Button></section></div></AppShell>;
}

function ToggleRow({ id, icon, label, description, checked, onChange }: { id: string; icon: React.ReactNode; label: string; description: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <div className="flex items-center justify-between gap-5 py-5 first:pt-0 last:pb-0"><div className="flex items-start gap-3"><div className="mt-0.5 text-teal">{icon}</div><div><label htmlFor={id} className="font-medium">{label}</label><p className="mt-1 text-sm text-muted-text">{description}</p></div></div><button id={id} type="button" role="switch" aria-checked={checked} aria-label={`${label}: ${checked ? "on" : "off"}`} onClick={() => onChange(!checked)} className={`relative h-7 w-12 shrink-0 rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ${checked ? "border-teal bg-teal" : "border-border bg-surface-2"}`}><span className={`absolute top-1 size-5 rounded-full bg-foreground transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} /></button></div>;
}