import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle, XCircle, Clock, Database } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../../app/providers/AuthProvider";
import { useSettings } from "../../app/providers/SettingsProvider";
import { formatPipelineTime, PipelineBinState, useRealtimePipeline } from "../../shared/realtimePipeline";

function eventRows(bin: PipelineBinState | null) {
  if (!bin) return [];
  const rows = bin.events.length > 0 ? bin.events : bin.latestEvent ? [bin.latestEvent] : [];
  return rows.slice(0, 25);
}

function sensorPercent(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? `${value}%` : "-";
}

function sensorValue(value: unknown, suffix = "") {
  return typeof value === "number" && Number.isFinite(value) ? `${value}${suffix}` : "-";
}

function optionalSensorValue(value: unknown, suffix = "") {
  return typeof value === "number" && Number.isFinite(value) ? `${value}${suffix}` : "Optional sensor unavailable";
}

function eventResult(correct: unknown) {
  if (correct === true) {
    return {
      className: "text-emerald-700",
      icon: <CheckCircle className="w-4 h-4" />,
      label: "Correct",
    };
  }
  if (correct === false) {
    return {
      className: "text-rose-700",
      icon: <XCircle className="w-4 h-4" />,
      label: "Incorrect",
    };
  }
  return {
    className: "text-amber-700",
    icon: <Clock className="w-4 h-4" />,
    label: "Not confirmed",
  };
}

function categoryLabel(value: unknown, recyclable?: boolean) {
  const category = typeof value === "string" ? value : "";
  const labels: Record<string, string> = {
    cardboard: "Cardboard",
    paper: "Paper",
    plastic_glass: "Plastic/Glass",
    metal: "Metal",
    trash: "Trash",
  };
  if (category && labels[category]) return labels[category];
  if (category) return category.replace(/[_-]+/g, " ").replace(/^./, (char) => char.toUpperCase());
  return recyclable ? "Recyclable" : "Non-Recyclable";
}

function classificationSourceLabel(value: unknown) {
  const source = typeof value === "string" ? value : "";
  const labels: Record<string, string> = {
    camera: "Camera",
    metal_sensor: "Metal sensor",
  };
  if (!source) return "-";
  return labels[source] || source.replace(/[_-]+/g, " ").replace(/^./, (char) => char.toUpperCase());
}

export const RealTimeMonitoringPage: React.FC = () => {
  const { user } = useAuth();
  const { settings } = useSettings();
  const [params, setParams] = useSearchParams();
  const { bins, loading, error } = useRealtimePipeline(user, settings.refreshRate);
  const [selectedBin, setSelectedBin] = useState<string>((params.get("bin") || "").trim().toUpperCase());

  useEffect(() => {
    const codes = bins.map((bin) => bin.binCode).filter(Boolean);
    if ((!selectedBin || !codes.includes(selectedBin)) && codes.length > 0) setSelectedBin(codes[0]);
  }, [bins, selectedBin]);

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (selectedBin) next.set("bin", selectedBin);
    else next.delete("bin");
    setParams(next, { replace: true });
  }, [selectedBin]);

  const selected = useMemo(() => bins.find((bin) => bin.binCode === selectedBin) || null, [bins, selectedBin]);
  const rows = eventRows(selected);
  const lastSeen = selected?.status.lastSeen || selected?.latestEvent?.timestamp;

  if (!user) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 p-6">
        <h1 className="text-2xl text-gray-900 mb-2">Real-Time Monitoring</h1>
        <p className="text-gray-600">Please login to view monitoring.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
          <h1 className="text-2xl text-gray-900 mb-1">Real-Time Monitoring</h1>
          <p className="text-gray-600">Live Raspberry Pi feed from Supabase Realtime</p>
          <p className="text-sm text-gray-500 mt-1">{user.superAdmin ? "Super Admin: all orgs" : `Org: ${user.orgId}`}</p>
        </div>

        <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-700 rounded-lg">
          <Clock className="w-4 h-4" />
          <span className="text-sm">Last update: {formatPipelineTime(lastSeen)}</span>
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
        <div className="flex items-center gap-2 text-gray-700">
          <Database className="w-4 h-4 text-gray-400" />
          <span className="text-sm">Selected Bin</span>
        </div>

        <select className="min-w-[240px] px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500 bg-white" value={selectedBin} onChange={(e) => setSelectedBin(e.target.value)} disabled={loading}>
          {loading ? <option value="">Loading bins...</option> : bins.length === 0 ? <option value="">No cloud bins available</option> : bins.map((bin) => <option key={`${bin.orgId}_${bin.binCode}`} value={bin.binCode}>{bin.binCode} - {bin.location || bin.orgId}</option>)}
        </select>
      </div>

      {selected && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5"><p className="text-sm text-gray-500">Left Fill</p><p className="text-3xl text-gray-900">{sensorPercent(selected.sensors.leftFillLevel)}</p></div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5"><p className="text-sm text-gray-500">Right Fill</p><p className="text-3xl text-gray-900">{sensorPercent(selected.sensors.rightFillLevel)}</p></div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5"><p className="text-sm text-gray-500">Temperature</p><p className="text-lg text-gray-900 leading-snug">{optionalSensorValue(selected.sensors.temperature, " C")}</p></div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5"><p className="text-sm text-gray-500">Gas Level</p><p className="text-lg text-gray-900 leading-snug">{optionalSensorValue(selected.sensors.gasLevel)}</p></div>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Timestamp</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Bin Code</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Item</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Category</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Source</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Disposal Route</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr><td className="px-6 py-5 text-sm text-gray-600" colSpan={7}>Loading live feed...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td className="px-6 py-6 text-sm text-gray-600" colSpan={7}>No disposal events received from the Pi yet.</td></tr>
              ) : rows.map((event, index) => {
                const result = eventResult(event.correct);
                return (
                  <tr key={event.id || index} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-700">{formatPipelineTime(event.timestamp)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900 font-medium">{selected?.binCode}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">{event.label || "-"}</td>
                    <td className="px-6 py-4 text-sm"><span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${event.recyclable ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>{categoryLabel(event.category, event.recyclable)}</span></td>
                    <td className="px-6 py-4 text-sm text-gray-700">{classificationSourceLabel(event.classificationSource)}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">{event.disposedSide || "-"} / expected {event.expectedSide || "-"}</td>
                    <td className="px-6 py-4 text-sm"><span className={`inline-flex items-center gap-2 ${result.className}`}>{result.icon}{result.label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default RealTimeMonitoringPage;
