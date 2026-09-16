import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { LoaderCircle, Save, UserRound } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { supabase } from "@/integrations/supabase/client";
import { useToast } from "@/components/ui/Toast";

export const Route = createFileRoute("/_authenticated/profile")({
  head: () => ({ meta: [
    { title: "Profile — Aarogya AI" },
    { name: "description", content: "Manage your personal Aarogya AI health profile." },
    { property: "og:title", content: "Profile — Aarogya AI" },
    { property: "og:description", content: "Manage your personal Aarogya AI health profile." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: ProfilePage,
});

function ProfilePage() {
  const [email, setEmail] = useState("—");
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("");
  const [saving, setSaving] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    let active = true;
    void supabase.auth.getUser().then(async ({ data }) => {
      const user = data.user;
      if (!user) return;
      const { data: profile } = await supabase.from("profiles").select("display_name, age, gender").eq("id", user.id).maybeSingle();
      if (active) {
        setEmail(user.email ?? "—");
        setName(profile?.display_name ?? user.user_metadata?.["full_name"] ?? "");
        setAge(profile?.age ? String(profile.age) : "");
        setGender(profile?.gender ?? "");
      }
    });
    return () => { active = false; };
  }, []);

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const { data: userData } = await supabase.auth.getUser();
    const user = userData.user;
    if (!user) { showToast("Please sign in again to update your profile.", "error"); setSaving(false); return; }
    const { error } = await supabase.from("profiles").upsert({ id: user.id, display_name: name.trim() || null, age: age ? Number(age) : null, gender: gender || null, updated_at: new Date().toISOString() }, { onConflict: "id" });
    if (error) showToast("Your profile could not be saved.", "error");
    else showToast("Profile saved.", "success");
    setSaving(false);
  }

  return <AppShell><div className="mx-auto w-full max-w-3xl px-6 py-10 lg:px-10 lg:py-14"><header className="mb-10"><p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Your details</p><h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Profile</h1><p className="mt-3 text-muted-text">Keep your personal context current for more useful assessments.</p></header><section className="rounded-lg border border-border bg-card p-6 sm:p-8" aria-labelledby="profile-heading"><div className="flex items-center gap-3"><div className="flex size-11 items-center justify-center rounded-md bg-teal-dim text-teal"><UserRound /></div><div><h2 id="profile-heading" className="font-semibold">Personal information</h2><p className="text-sm text-muted-text">Only you can view these details.</p></div></div><form className="mt-8 space-y-5" onSubmit={saveProfile}><div><label htmlFor="profile-email" className="text-sm font-medium">Email address</label><Input id="profile-email" className="mt-2" value={email} readOnly /></div><div><label htmlFor="profile-name" className="text-sm font-medium">Full name</label><Input id="profile-name" className="mt-2" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your full name" /></div><div className="grid gap-5 sm:grid-cols-2"><div><label htmlFor="profile-age" className="text-sm font-medium">Age</label><Input id="profile-age" className="mt-2" type="number" min="1" max="120" value={age} onChange={(event) => setAge(event.target.value)} placeholder="Your age" /></div><div><label htmlFor="profile-gender" className="text-sm font-medium">Gender</label><select id="profile-gender" className="mt-2 flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={gender} onChange={(event) => setGender(event.target.value)}><option value="">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></div></div><Button type="submit" className="btn-primary" disabled={saving}>{saving ? <LoaderCircle className="animate-spin" /> : <Save />} Save profile</Button></form></section></div></AppShell>;
}