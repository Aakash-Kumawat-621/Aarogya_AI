import { FormEvent, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, HeartPulse, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { supabase } from "@/integrations/supabase/client";
import { PublicLayout } from "@/components/public-layout";
import { lovable } from "@/integrations/lovable";
import { useToast } from "@/components/ui/Toast";

export const Route = createFileRoute("/signup")({
  head: () => ({ meta: [{ title: "Create account — Aarogya AI" }, { name: "description", content: "Create your private Aarogya AI health space." }, { property: "og:title", content: "Create account — Aarogya AI" }, { property: "og:description", content: "Create your private Aarogya AI health space." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: SignUpPage,
});

function SignUpPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: name }, emailRedirectTo: window.location.origin },
    });
    if (signUpError) {
      showToast(signUpError.message, "error");
      setLoading(false);
      return;
    }
    if (!data.session) {
      showToast("Check your email to verify your account.", "success");
      setLoading(false);
      return;
    }
    await navigate({ to: "/dashboard", replace: true });
  }

  async function handleGoogle() {
    setLoading(true);
    const result = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/dashboard`
      }
    });
    if (result.error) { showToast(result.error.message, "error"); setLoading(false); }
  }

  return (
    <PublicLayout><main className="grid min-h-screen bg-background pt-20 md:grid-cols-2">
      <section className="auth-pattern relative hidden overflow-hidden bg-surface p-12 md:flex md:flex-col md:justify-between"><div className="flex items-center gap-3"><div className="flex size-11 items-center justify-center rounded-md bg-teal text-lg font-bold text-primary-foreground">A</div><span className="text-xl font-semibold">Aarogya AI</span></div><div className="relative max-w-lg"><HeartPulse className="mb-8 size-16 text-teal" strokeWidth={1.2} /><p className="text-4xl font-bold leading-tight">A private health space that grows with you.</p><p className="mt-5 text-muted-text">Start with your symptoms. Leave with a clearer next step.</p></div><p className="font-mono text-xs text-dim">CARE, CLARIFIED</p></section>
      <section className="flex items-center justify-center px-6 py-14"><div className="w-full max-w-md">
        <div className="rounded-xl border border-border bg-card p-8 shadow-2xl shadow-background/30">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Start here</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">Create your health space</h1>
          <p className="mt-2 text-sm text-muted-text">Keep your health context close and private.</p>
          <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
            <Input placeholder="Full name" value={name} onChange={(event) => setName(event.target.value)} required />
            <Input type="email" placeholder="Email address" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <Input type="password" placeholder="Create password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required />
            <Button className="btn-primary w-full" disabled={loading}>{loading ? <LoaderCircle className="animate-spin" /> : <ArrowRight />} Create Account</Button>
          </form>
          <div className="my-6 flex items-center gap-3 text-xs text-dim"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>
          <Button type="button" variant="outline" className="btn-ghost w-full bg-foreground text-background hover:text-background" onClick={handleGoogle} disabled={loading}><span className="font-bold">G</span> Continue with Google</Button>
          <p className="mt-6 text-center text-sm text-muted-text">Already have an account? <Link className="text-teal hover:underline" to="/login">Sign in</Link></p>
        </div>
      </div></section>
    </main></PublicLayout>
  );
}