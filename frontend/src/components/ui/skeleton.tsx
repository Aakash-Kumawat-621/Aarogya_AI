import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn("skeleton-shimmer rounded-md", className)} {...props} />;
}

function SkeletonText({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <Skeleton className={cn("h-3.5 rounded-sm", className)} {...props} />;
}

function SkeletonCard({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <Skeleton className={cn("min-h-36 w-full rounded-lg border border-border", className)} {...props} />;
}

export function PageLoadingSkeleton({ variant = "cards" }: { variant?: "cards" | "list" }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-12" aria-label="Loading" role="status">
      <SkeletonText className="w-28" />
      <Skeleton className="mt-4 h-9 w-64 max-w-full" />
      <div className={variant === "list" ? "mt-10 space-y-3" : "mt-10 grid gap-4 md:grid-cols-3"}>
        {[0, 1, 2].map((item) => <SkeletonCard key={item} className={variant === "list" ? "min-h-24" : undefined} />)}
      </div>
      <span className="sr-only">Loading content</span>
    </div>
  );
}

export { Skeleton, SkeletonText, SkeletonCard };
