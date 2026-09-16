import { createFileRoute, Link } from "@tanstack/react-router";
import { Activity, AlertTriangle, ArrowDown, ArrowRight, Brain, Search, Shield, Star, Stethoscope } from "lucide-react";
import { animate, motion, useInView, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { PublicLayout } from "@/components/public-layout";
import { ScrollReveal, StaggerReveal } from "@/components/ui/ScrollReveal";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/home")({
  head: () => ({ meta: [{ title: "Aarogya AI — Personal Health Intelligence" }, { name: "description", content: "A premium health intelligence space for clearer next steps." }, { property: "og:title", content: "Aarogya AI — Personal Health Intelligence" }, { property: "og:description", content: "A premium health intelligence space for clearer next steps." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: HomePage,
});

const steps = [
  {
    number: "01",
    title: "Input Symptoms",
    description: "Tell Aarogya AI what you are feeling in your own words.",
    icon: Activity,
  },
  {
    number: "02",
    title: "AI Analysis",
    description: "Your symptoms are assessed for patterns, context, and urgency.",
    icon: Brain,
  },
  {
    number: "03",
    title: "Get Care",
    description: "Receive clear next steps and discover verified doctors near you.",
    icon: Stethoscope,
  },
] as const;

const features = [
  { title: "Symptom Checker", description: "Advanced NLP understands your symptoms in plain English.", icon: Activity },
  { title: "Smart Triage", description: "Instantly evaluates urgency and recommends next steps.", icon: AlertTriangle },
  { title: "Specialist Matching", description: "Finds the right doctor based on AI diagnosis.", icon: Search },
  { title: "Secure History", description: "All your past assessments saved securely.", icon: Shield },
] as const;

const stories = [
  { quote: "Aarogya helped me understand how urgent my symptoms were and what to do next without panic.", name: "Priya S." },
  { quote: "The questions were clear, and the specialist recommendation saved me hours of searching.", name: "Rahul M." },
  { quote: "Having every assessment in one secure place makes follow-up conversations much easier.", name: "Ananya K." },
] as const;

function HomePage() {
  return (
    <PublicLayout>
      <main>
        <Hero />
        <HowItWorks />
        <Features />
        <Impact />
        <Stories />
        <FinalCta />
      </main>
      <Footer />
    </PublicLayout>
  );
}

function Features() {
  return (
    <section id="features" className="bg-background px-5 py-24 sm:py-32" aria-labelledby="features-title">
      <div className="mx-auto max-w-6xl">
        <ScrollReveal>
          <p className="font-mono text-xs uppercase text-teal">Built around your next step</p>
          <h2 id="features-title" className="mt-3 max-w-2xl text-3xl font-bold sm:text-4xl">Clearer health decisions, from first symptom to care.</h2>
        </ScrollReveal>
        <StaggerReveal className="mt-12 grid gap-6 md:grid-cols-2">
          {features.map(({ title, description, icon: Icon }) => (
            <article key={title} className="card-hover rounded-lg border border-border bg-card p-7 sm:p-8">
              <div className="flex size-11 items-center justify-center rounded-md bg-teal-dim text-teal"><Icon aria-hidden="true" /></div>
              <h3 className="mt-6 text-xl font-semibold">{title}</h3>
              <p className="mt-3 leading-7 text-muted-text">{description}</p>
            </article>
          ))}
        </StaggerReveal>
      </div>
    </section>
  );
}

function CountUp({ value, decimals = 0, suffix = "+" }: { value: number; decimals?: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (!inView) return;
    if (reduced) { setDisplay(value); return; }
    const controls = animate(0, value, { duration: 1.4, ease: "easeOut", onUpdate: setDisplay });
    return () => controls.stop();
  }, [inView, reduced, value]);
  return <span ref={ref}>{display.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</span>;
}

function Impact() {
  const stats = [
    { value: 10000, label: "Assessments", suffix: "+" },
    { value: 99.8, label: "Triage Accuracy", suffix: "%", decimals: 1 },
    { value: 500, label: "Verified Doctors", suffix: "+" },
  ];
  return (
    <section className="border-y border-border bg-surface px-5 py-20" aria-label="Aarogya AI impact">
      <div className="mx-auto grid max-w-6xl gap-12 sm:grid-cols-3">
        {stats.map((stat) => <div key={stat.label} className="text-center"><p className="font-mono text-4xl font-bold text-foreground sm:text-5xl"><CountUp {...stat} /></p><p className="mt-3 text-sm text-muted-text">{stat.label}</p></div>)}
      </div>
    </section>
  );
}

function Stories() {
  return (
    <section className="bg-background px-5 py-24 sm:py-32" aria-labelledby="stories-title">
      <div className="mx-auto max-w-6xl">
        <ScrollReveal><p className="font-mono text-xs uppercase text-teal">Patient stories</p><h2 id="stories-title" className="mt-3 text-3xl font-bold sm:text-4xl">Confidence when it matters.</h2></ScrollReveal>
        <div className="mt-12 grid gap-5 md:flex md:snap-x md:overflow-x-auto md:pb-4">
          {stories.map((story) => (
            <blockquote key={story.name} className="rounded-lg border border-border bg-card p-7 md:min-w-[22rem] md:flex-1 md:snap-start">
              <div className="flex gap-1 text-teal" aria-label="5 out of 5 stars">{Array.from({ length: 5 }).map((_, index) => <Star key={index} className="size-4 fill-current" aria-hidden="true" />)}</div>
              <p className="mt-6 leading-7 text-foreground">“{story.quote}”</p>
              <footer className="mt-6 font-mono text-xs text-muted-text">— {story.name}</footer>
            </blockquote>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="hero-atmosphere border-y border-teal/20 bg-surface px-5 py-24 text-center">
      <ScrollReveal><h2 className="text-4xl font-bold sm:text-5xl">Take control of your health today.</h2><Button asChild size="lg" className="btn-primary mt-8 h-12 bg-foreground px-7 text-teal hover:bg-foreground"><Link to="/analyze">Analyze Symptoms Now <ArrowRight aria-hidden="true" /></Link></Button></ScrollReveal>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-background px-5 py-10 text-sm text-muted-text">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 border-t border-border pt-8 sm:flex-row sm:items-center sm:justify-between">
        <p>© 2026 Aarogya AI. All rights reserved.</p>
        <nav className="flex flex-wrap gap-5" aria-label="Footer navigation">{["About", "Privacy", "Terms", "Contact"].map((label) => <a key={label} href={`#${label.toLowerCase()}`} className="transition-colors hover:text-foreground">{label}</a>)}</nav>
      </div>
    </footer>
  );
}

function Hero() {
  const prefersReducedMotion = useReducedMotion();

  const scrollToSteps = () => {
    document.querySelector("#how-it-works")?.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth" });
  };

  return (
    <section className="hero-atmosphere relative flex min-h-[90vh] items-center overflow-hidden px-5 pb-16 pt-28">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        {["left-[12%] top-[25%] size-28", "right-[14%] top-[18%] size-20", "bottom-[16%] left-[30%] size-16", "bottom-[28%] right-[28%] size-24"].map((position, index) => (
          <motion.span
            key={position}
            className={`hero-particle absolute rounded-full ${position}`}
            animate={prefersReducedMotion ? false : { x: [0, index % 2 === 0 ? 16 : -14, 0], y: [0, index % 2 === 0 ? -18 : 15, 0] }}
            transition={{ duration: 7 + index * 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
        ))}
      </div>

      <div className="relative mx-auto w-full max-w-6xl">
        <StaggerReveal>
          <div className="inline-flex rounded-full border border-teal/35 bg-teal-dim px-4 py-2 text-sm font-medium text-muted-text">
            AI-Powered Medical Assistance
          </div>
          <h1 className="mt-7 max-w-4xl text-5xl font-extrabold leading-[1.04] text-foreground sm:text-6xl lg:text-7xl">
            Your Personal Health Guardian
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-text sm:text-xl">
            Instant symptom analysis, accurate triage, and verified doctor recommendations across India.
          </p>
          <div className="mt-10 flex flex-col gap-4 sm:flex-row">
            <Button asChild size="lg" className="btn-primary h-12 px-6 text-base">
              <Link to="/analyze">Start Free Analysis <ArrowRight aria-hidden="true" /></Link>
            </Button>
            <Button type="button" variant="outline" size="lg" className="btn-ghost h-12 px-6 text-base" onClick={scrollToSteps}>
              How it works <ArrowDown aria-hidden="true" />
            </Button>
          </div>
        </StaggerReveal>
      </div>
    </section>
  );
}

function HowItWorks() {
  const sectionRef = useRef<HTMLElement>(null);
  const [activeStep, setActiveStep] = useState(0);
  const prefersReducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start start", "end end"] });
  const x = useTransform(scrollYProgress, [0, 1], ["0%", "-66.6667%"]);

  useMotionValueEvent(scrollYProgress, "change", (latest) => {
    setActiveStep(Math.min(2, Math.floor(latest * 3)));
  });

  return (
    <section id="how-it-works" ref={sectionRef} className="relative h-[300vh] bg-surface" aria-labelledby="how-it-works-title">
      <div className="sticky top-0 flex h-screen flex-col overflow-hidden pt-24">
        <div className="mx-auto flex w-full max-w-6xl items-end justify-between px-5 pb-7">
          <ScrollReveal>
            <p className="font-mono text-xs uppercase text-teal">Three clear steps</p>
            <h2 id="how-it-works-title" className="mt-3 text-3xl font-bold text-foreground sm:text-4xl">How it works</h2>
          </ScrollReveal>
          <p className="font-mono text-sm text-muted-text">0{activeStep + 1} / 03</p>
        </div>

        <div className="mx-auto mb-8 h-px w-[calc(100%-2.5rem)] max-w-6xl bg-border">
          <motion.div className="h-full origin-left bg-teal" style={{ scaleX: scrollYProgress }} />
        </div>

        <motion.div className="flex flex-1" style={{ x: prefersReducedMotion ? "0%" : x, width: "300%" }}>
          {steps.map((step, index) => {
            const Icon = step.icon;
            const active = activeStep === index;
            return (
              <article key={step.title} className="flex w-1/3 shrink-0 items-center px-5 pb-20">
                <div className="mx-auto grid w-full max-w-6xl gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
                  <div className={`flex size-24 items-center justify-center rounded-lg border transition-colors duration-300 sm:size-32 ${active ? "border-teal bg-teal-dim text-teal" : "border-border bg-background text-dim"}`}>
                    <Icon className="size-11 sm:size-14" strokeWidth={1.35} aria-hidden="true" />
                  </div>
                  <div>
                    <p className={`font-mono text-sm transition-colors ${active ? "text-teal" : "text-dim"}`}>STEP {step.number}</p>
                    <h3 className={`mt-4 text-5xl font-extrabold leading-none transition-colors sm:text-7xl lg:text-8xl ${active ? "text-foreground" : "text-dim"}`}>{step.title}</h3>
                    <p className="mt-6 max-w-xl text-lg leading-8 text-muted-text sm:text-xl">{step.description}</p>
                  </div>
                </div>
              </article>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}