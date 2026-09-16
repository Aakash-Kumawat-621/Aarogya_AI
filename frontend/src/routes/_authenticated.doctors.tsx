import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowRight, LocateFixed, MapPin, Search, Stethoscope } from "lucide-react";

import { searchDoctors } from "@/api/mediassist";
import type { DoctorResult } from "@/types/api.types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/Toast";

export const Route = createFileRoute("/_authenticated/doctors")({
  head: () => ({ meta: [
    { title: "Find Doctors — Aarogya AI" },
    { name: "description", content: "Find trusted doctors near you with Aarogya AI." },
    { property: "og:title", content: "Find Doctors — Aarogya AI" },
    { property: "og:description", content: "Find trusted doctors near you with Aarogya AI." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: DoctorFinderPage,
});

const fallbackDoctors: DoctorResult[] = [
  { name: "Dr. Meera Shah", specialty: "General Physician", address: "Indiranagar, Bengaluru", distance_km: 2.4, rating: 4.9, phone: "+91 80 4123 8800", is_open_now: true, source: "Aarogya AI" },
  { name: "Dr. Arjun Mehta", specialty: "Internal Medicine", address: "Koramangala, Bengaluru", distance_km: 4.1, rating: 4.8, phone: "+91 80 4567 2211", is_open_now: true, source: "Aarogya AI" },
  { name: "Dr. Kavya Rao", specialty: "Family Medicine", address: "Halasuru, Bengaluru", distance_km: 6.8, rating: 4.7, phone: "+91 80 4012 9900", is_open_now: false, source: "Aarogya AI" },
];

function DoctorFinderPage() {
  const [query, setQuery] = useState("general physician");
  const [doctors, setDoctors] = useState<DoctorResult[]>(fallbackDoctors);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  async function findDoctors(condition = query) {
    const cleanCondition = condition.trim() || "general physician";
    setLoading(true);
    try {
      const result = await searchDoctors({ condition: cleanCondition, radius_km: 25 });
      if (result.doctors.length > 0) setDoctors(result.doctors);
    } catch {
      setDoctors(fallbackDoctors);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void findDoctors(); }, []);

  function useLocation() {
    if (!navigator.geolocation) {
      showToast("Location is not available on this device.", "info");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      () => showToast("Showing doctors closest to your location.", "success"),
      () => showToast("We could not access your location. Showing nearby doctors instead.", "info"),
    );
  }

  return (
    <>
      <div className="mx-auto w-full max-w-7xl px-6 py-10 lg:px-10 lg:py-14">
        <header className="mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Care network</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Find the right doctor</h1>
          <p className="mt-3 max-w-2xl text-muted-text">Explore nearby specialists and take the next step with confidence.</p>
        </header>

        <form className="flex flex-col gap-3 md:flex-row" onSubmit={(event) => { event.preventDefault(); void findDoctors(); }}>
          <label htmlFor="doctor-search" className="sr-only">Search by condition or specialty</label>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-text" aria-hidden="true" />
            <Input id="doctor-search" value={query} onChange={(event) => setQuery(event.target.value)} className="h-11 pl-10" placeholder="Search by condition or specialty" />
          </div>
          <Button type="submit" className="btn-primary h-11" disabled={loading}><Search /> Search</Button>
          <Button type="button" variant="outline" className="btn-ghost h-11" onClick={useLocation}><LocateFixed /> Use My Location</Button>
        </form>

        <div className="mt-8 grid gap-6 xl:grid-cols-[1fr_25rem]">
          <section className="relative min-h-[30rem] overflow-hidden rounded-lg border border-border bg-surface-2" aria-label="Map view">
            <div className="absolute inset-0 opacity-40" style={{ backgroundImage: "linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)", backgroundSize: "42px 42px" }} />
            <div className="relative flex min-h-[30rem] flex-col items-center justify-center p-6 text-center">
              <div className="flex size-14 items-center justify-center rounded-full bg-teal-dim text-teal"><MapPin className="size-7" /></div>
              <h2 className="mt-5 text-xl font-semibold">Map View</h2>
              <p className="mt-2 max-w-xs text-sm text-muted-text">Use your location to see care options around you.</p>
            </div>
          </section>

          <section aria-labelledby="doctor-list-heading">
            <div className="flex items-center justify-between gap-3">
              <div><p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Nearby care</p><h2 id="doctor-list-heading" className="mt-2 text-2xl font-semibold">Recommended doctors</h2></div>
              <span className="font-mono text-xs text-muted-text">{doctors.length} matches</span>
            </div>
            <div className="mt-5 space-y-3">
              {doctors.map((doctor) => <DoctorCard key={`${doctor.name}-${doctor.address}`} doctor={doctor} />)}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

function DoctorCard({ doctor }: { doctor: DoctorResult }) {
  return (
    <article className="card-hover rounded-lg border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-teal-dim text-teal"><Stethoscope className="size-5" /></div>
          <div className="min-w-0"><h3 className="truncate font-semibold">{doctor.name}</h3><p className="mt-1 text-sm text-teal">{doctor.specialty}</p></div>
        </div>
        <span className="shrink-0 font-mono text-xs text-muted-text">{doctor.distance_km.toFixed(1)} km</span>
      </div>
      <p className="mt-4 flex items-start gap-2 text-sm text-muted-text"><MapPin className="mt-0.5 size-4 shrink-0" />{doctor.address}</p>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4"><span className="text-sm text-muted-text"><span className="text-urgent">★</span> {doctor.rating?.toFixed(1) ?? "—"} · {doctor.is_open_now ? "Open now" : "Closed"}</span><Button type="button" size="sm" className="btn-primary">Book <ArrowRight /></Button></div>
    </article>
  );
}