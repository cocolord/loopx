import { CircleAlert, Clock3, FileSearch } from "lucide-react";

import type { PresentationSurface, RunGoal } from "../data/status";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";

type BadgeVariant = "neutral" | "success" | "warning" | "info" | "danger";

const stateVariant: Record<string, BadgeVariant> = {
  empty: "neutral",
  invalid: "danger",
  ready: "success",
  review_due: "warning",
};

function StateBadge({ value }: { value: string }) {
  return <Badge variant={stateVariant[value] ?? "neutral"}>{value}</Badge>;
}

// Core status is a compact, provider-neutral index. It carries lifecycle state
// plus a content-addressed `detail_ref` pointer, never the full provider-owned
// view. This surface therefore renders the compact contract only. Rich domain
// rendering (for example the finance decision-research view) belongs to a
// follow-up that fetches the referenced projection through a serving channel.
export function DecisionResearchSurface({
  goals,
  surface,
}: {
  goals: RunGoal[];
  surface: PresentationSurface;
}) {
  if (surface.state === "invalid") {
    return (
      <Card data-testid="decision-research-surface">
        <CardHeader>
          <div>
            <CardTitle>{surface.title}</CardTitle>
            <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">
              The active-revision projection failed safe validation.
            </p>
          </div>
          <StateBadge value="invalid" />
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100">
            <div className="flex items-center gap-2 font-semibold">
              <CircleAlert className="h-4 w-4" />
              Projection unavailable
            </div>
            <p className="mt-2">{surface.diagnostic}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (surface.state === "empty") {
    return (
      <Card data-testid="decision-research-surface">
        <CardHeader>
          <div>
            <CardTitle>{surface.title}</CardTitle>
            <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">
              {surface.empty_state_title}
            </p>
          </div>
          <StateBadge value="pending" />
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-dashed border-slate-300 p-5 text-sm leading-6 text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
            {surface.empty_state_detail}
          </div>
        </CardContent>
      </Card>
    );
  }

  const goalIsKnown = goals.some((goal) => goal.id === surface.goal_id);

  return (
    <div className="space-y-5" data-testid="decision-research-surface">
      {surface.state === "review_due" ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          <div className="flex items-center gap-2 font-semibold">
            <Clock3 className="h-4 w-4" />
            Review due
          </div>
          <p className="mt-1">
            This projection remains published, but its declared review deadline has passed.
          </p>
        </div>
      ) : null}

      {!goalIsKnown ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          The projection references goal <span className="font-mono">{surface.goal_id}</span>, which is not present in the current status goal list.
        </div>
      ) : null}

      <Card data-testid="decision-research-surface-summary">
        <CardHeader>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">{surface.title}</Badge>
              <StateBadge value={surface.state} />
              <Badge variant="neutral">{surface.visibility}</Badge>
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-300">
              A validated projection is published for this surface. This dashboard
              shows the compact status index; the full view is served separately by
              content-addressed reference.
            </p>
          </div>
          <FileSearch className="h-5 w-5 text-slate-400 dark:text-zinc-500" />
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-zinc-400">
                View schema
              </dt>
              <dd className="mt-1 font-mono text-slate-800 dark:text-zinc-200">
                {surface.view_schema}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-zinc-400">
                Generated at
              </dt>
              <dd className="mt-1 text-slate-800 dark:text-zinc-200">
                {surface.generated_at}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-zinc-400">
                Extension revision
              </dt>
              <dd className="mt-1 font-mono text-slate-800 dark:text-zinc-200">
                {surface.detail_ref.extension_revision}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-zinc-400">
                Payload SHA-256
              </dt>
              <dd
                className="mt-1 break-all font-mono text-xs text-slate-800 dark:text-zinc-200"
                data-testid="research-detail-ref-hash"
              >
                {surface.detail_ref.payload_sha256}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

// The compact status contract does not carry provider view summaries, so there
// is nothing for a summaries strip to render yet. This is kept as a stable
// no-op export so the dashboard page wiring stays unchanged until a serving
// channel is added.
export function DecisionResearchDashboardSummaries({
  onSelect,
  surfaces,
}: {
  onSelect: (extensionId: string, surfaceId: string) => void;
  surfaces: PresentationSurface[];
}) {
  void onSelect;
  void surfaces;
  return null;
}
