import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { adminClient, normalizeOrgId } from "../_shared/admin.ts";

const allowedCategories = new Set(["cardboard", "paper", "plastic_glass", "metal", "trash"]);
const allowedSides = new Set(["recyclable", "non_recyclable"]);

async function sha256Hex(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function normalizeText(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);

  try {
    const deviceToken = req.headers.get("x-device-token") || req.headers.get("authorization")?.replace("Bearer ", "");
    if (!deviceToken) return jsonResponse({ error: "Missing device token." }, 401);

    const body = await req.json();
    const orgId = normalizeOrgId(body.orgId, "techbin");
    const binCode = String(body.binCode ?? "BIN-001").trim().toUpperCase();
    const binId = `${orgId}_${binCode}`;
    const tokenHash = await sha256Hex(deviceToken);
    const client = adminClient();

    const { data: device, error: deviceError } = await client
      .from("pi_devices")
      .select("id,bin_id,active")
      .eq("bin_id", binId)
      .eq("token_hash", tokenHash)
      .eq("active", true)
      .single();

    if (deviceError || !device) return jsonResponse({ error: "Invalid device token." }, 401);

    const now = new Date().toISOString();
    const latestEvent = body.latestEvent ?? body.event ?? null;
    const event = latestEvent && typeof latestEvent === "object" && !Array.isArray(latestEvent)
      ? latestEvent as Record<string, unknown>
      : null;
    const eventId = event ? normalizeText(event.eventId ?? event.event_id) : null;
    const category = event ? normalizeText(event.category) : null;
    const disposedSide = event ? normalizeText(event.disposedSide ?? event.disposed_side) : null;
    const expectedSide = event ? normalizeText(event.expectedSide ?? event.expected_side) : null;

    if (latestEvent && !event) return jsonResponse({ error: "latestEvent must be an object." }, 400);
    if (event && !eventId) return jsonResponse({ error: "latestEvent.eventId is required for disposal events." }, 400);
    if (category && !allowedCategories.has(category)) {
      return jsonResponse({ error: "latestEvent.category must be one of: cardboard, paper, plastic_glass, metal, trash." }, 400);
    }
    if (disposedSide && !allowedSides.has(disposedSide)) {
      return jsonResponse({ error: "latestEvent.disposedSide must be recyclable or non_recyclable." }, 400);
    }
    if (expectedSide && !allowedSides.has(expectedSide)) {
      return jsonResponse({ error: "latestEvent.expectedSide must be recyclable or non_recyclable." }, 400);
    }

    const { error: stateError } = await client.from("bin_states").upsert({
      bin_id: binId,
      org_id: orgId,
      bin_code: binCode,
      status: body.status ?? { state: "normal", lastSeen: now },
      sensors: body.sensors ?? {},
      statistics: body.statistics ?? {},
      faults: body.faults ?? {},
      latest_event: latestEvent,
      last_seen: body.lastSeen ?? now,
      updated_at: now,
    });
    if (stateError) throw stateError;

    if (event && eventId) {
      const { error: eventError } = await client.from("bin_events").upsert({
        event_id: eventId,
        bin_id: binId,
        org_id: orgId,
        bin_code: binCode,
        timestamp: event.timestamp ?? now,
        label: event.label ?? null,
        category,
        recyclable: event.recyclable ?? null,
        disposed_side: disposedSide,
        expected_side: expectedSide,
        correct: event.correct ?? null,
        confidence: event.confidence ?? null,
        image_url: event.imageUrl ?? event.image_url ?? null,
        payload: event,
      }, {
        onConflict: "bin_id,event_id",
        ignoreDuplicates: true,
      });
      if (eventError) throw eventError;
    }

    await client.from("pi_devices").update({ last_seen: now }).eq("id", device.id);
    return jsonResponse({ ok: true, binId });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : "Ingest failed." }, 400);
  }
});
