import { useEffect, useMemo, useState } from "react";
import { supabase, type BinRow } from "./supabase";
import type { User } from "../app/providers/AuthProvider";

export type PipelineStatus = {
  state?: "normal" | "faulty" | "maintenance" | "offline" | string;
  lastSeen?: number | string;
  message?: string;
};

export type PipelineSensors = {
  fillLevel?: number;
  leftFillLevel?: number;
  rightFillLevel?: number;
  temperature?: number;
  gasLevel?: number;
  [key: string]: unknown;
};

export type PipelineStatistics = {
  totalItems?: number;
  cardboard?: number;
  paper?: number;
  plastic_glass?: number;
  metal?: number;
  trash?: number;
  recyclableItems?: number;
  nonRecyclableItems?: number;
  correctDisposals?: number;
  incorrectDisposals?: number;
  [key: string]: unknown;
};

export type DisposalEvent = {
  id?: string;
  eventId?: string;
  timestamp?: number | string;
  label?: string;
  category?: string;
  recyclable?: boolean;
  disposedSide?: string;
  expectedSide?: string;
  correct?: boolean;
  confidence?: number;
  placementConfirmed?: boolean;
  modelVersion?: string;
  classificationSource?: string;
  imageUrl?: string | null;
  [key: string]: unknown;
};

export type PipelineBinState = {
  orgId: string;
  binCode: string;
  location?: string | null;
  status: PipelineStatus;
  sensors: PipelineSensors;
  statistics: PipelineStatistics;
  faults: Record<string, boolean>;
  latestEvent?: DisposalEvent | null;
  events: DisposalEvent[];
};

type PipelineLoadState = {
  bins: PipelineBinState[];
  loading: boolean;
  error: string | null;
};

type BinStateRow = {
  bin_id: string;
  org_id: string;
  bin_code: string;
  status: Record<string, unknown> | null;
  sensors: Record<string, unknown> | null;
  statistics: Record<string, unknown> | null;
  faults: Record<string, unknown> | null;
  latest_event: Record<string, unknown> | null;
  last_seen: string | null;
};

type BinEventRow = {
  id: string;
  event_id: string | null;
  bin_id: string;
  timestamp: string | null;
  label: string | null;
  category: string | null;
  recyclable: boolean | null;
  disposed_side: string | null;
  expected_side: string | null;
  correct: boolean | null;
  confidence: number | null;
  image_url: string | null;
  payload: Record<string, unknown> | null;
};

function toObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function toFaults(value: unknown): Record<string, boolean> {
  const raw = toObject(value);
  return Object.fromEntries(Object.entries(raw).map(([key, val]) => [key, val === true]));
}

function mapEvent(row: BinEventRow): DisposalEvent {
  return {
    ...(row.payload || {}),
    id: row.id,
    eventId: row.event_id || (row.payload?.eventId as string | undefined) || (row.payload?.event_id as string | undefined),
    timestamp: row.timestamp || undefined,
    label: row.label || undefined,
    category: row.category || undefined,
    recyclable: row.recyclable ?? undefined,
    disposedSide: row.disposed_side || undefined,
    expectedSide: row.expected_side || undefined,
    correct: row.correct ?? undefined,
    confidence: row.confidence ?? undefined,
    imageUrl: row.image_url || undefined,
  };
}

function mapBin(bin: BinRow, state: BinStateRow | undefined, events: BinEventRow[]): PipelineBinState {
  const status = toObject(state?.status) as PipelineStatus;
  if (!status.lastSeen && state?.last_seen) status.lastSeen = state.last_seen;

  return {
    orgId: bin.org_id,
    binCode: bin.bin_code,
    location: bin.location,
    status: Object.keys(status).length ? status : { state: bin.status === "Active" ? "normal" : bin.status.toLowerCase() },
    sensors: toObject(state?.sensors) as PipelineSensors,
    statistics: toObject(state?.statistics) as PipelineStatistics,
    faults: toFaults(state?.faults),
    latestEvent: state?.latest_event ? (toObject(state.latest_event) as DisposalEvent) : null,
    events: events.map(mapEvent),
  };
}

export function formatPipelineTime(value: unknown): string {
  if (!value) return "-";
  if (typeof value === "number") return new Date(value).toLocaleString();
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? value : new Date(parsed).toLocaleString();
  }
  return "-";
}

export function useRealtimePipeline(user: User | null, refreshRateSeconds = "10"): PipelineLoadState {
  const [state, setState] = useState<PipelineLoadState>({ bins: [], loading: true, error: null });

  useEffect(() => {
    if (!user) {
      setState({ bins: [], loading: false, error: null });
      return;
    }

    let active = true;
    setState((current) => ({ ...current, loading: true, error: null }));

    const load = async () => {
      let binsRequest = supabase.from("bins").select("*").order("created_at", { ascending: false });
      if (!user.superAdmin) binsRequest = binsRequest.eq("org_id", user.orgId);

      const { data: binsData, error: binsError } = await binsRequest;
      if (binsError) {
        if (active) setState({ bins: [], loading: false, error: binsError.message });
        return;
      }

      const bins = ((binsData || []) as BinRow[]);
      const binIds = bins.map((bin) => bin.id);

      if (binIds.length === 0) {
        if (active) setState({ bins: [], loading: false, error: null });
        return;
      }

      const [{ data: statesData, error: statesError }, { data: eventsData, error: eventsError }] = await Promise.all([
        supabase.from("bin_states").select("*").in("bin_id", binIds),
        supabase
          .from("bin_events")
          .select("*")
          .in("bin_id", binIds)
          .order("timestamp", { ascending: false })
          .limit(100),
      ]);

      if (statesError || eventsError) {
        if (active) setState({ bins: [], loading: false, error: statesError?.message || eventsError?.message || "Pipeline load failed." });
        return;
      }

      const stateByBin = new Map(((statesData || []) as BinStateRow[]).map((row) => [row.bin_id, row]));
      const eventsByBin = ((eventsData || []) as BinEventRow[]).reduce<Map<string, BinEventRow[]>>((acc, row) => {
        acc.set(row.bin_id, [...(acc.get(row.bin_id) || []), row]);
        return acc;
      }, new Map());

      if (active) {
        setState({
          bins: bins.map((bin) => mapBin(bin, stateByBin.get(bin.id), eventsByBin.get(bin.id) || [])),
          loading: false,
          error: null,
        });
      }
    };

    load();
    const refreshMs = Math.max(5000, Number(refreshRateSeconds || 10) * 1000);
    const refreshTimer = window.setInterval(() => {
      load();
    }, refreshMs);

    const channel = supabase
      .channel(`pipeline:${user.superAdmin ? "all" : user.orgId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "bins" }, () => load())
      .on("postgres_changes", { event: "*", schema: "public", table: "bin_states" }, () => load())
      .on("postgres_changes", { event: "*", schema: "public", table: "bin_events" }, () => load())
      .subscribe();

    return () => {
      active = false;
      window.clearInterval(refreshTimer);
      supabase.removeChannel(channel);
    };
  }, [user, refreshRateSeconds]);

  return state;
}

export function usePipelineTotals(bins: PipelineBinState[]) {
  return useMemo(() => {
    return bins.reduce(
      (acc, bin) => {
        const stats = bin.statistics;
        acc.totalItems += Number(stats.totalItems || 0);
        acc.recyclableItems += Number(stats.recyclableItems || 0);
        acc.nonRecyclableItems += Number(stats.nonRecyclableItems || 0);
        acc.correctDisposals += Number(stats.correctDisposals || 0);
        acc.incorrectDisposals += Number(stats.incorrectDisposals || 0);
        if ((bin.status.state || "").toLowerCase() === "normal") acc.normalBins += 1;
        if ((bin.status.state || "").toLowerCase() === "faulty") acc.faultyBins += 1;
        return acc;
      },
      {
        totalItems: 0,
        recyclableItems: 0,
        nonRecyclableItems: 0,
        correctDisposals: 0,
        incorrectDisposals: 0,
        normalBins: 0,
        faultyBins: 0,
      }
    );
  }, [bins]);
}
