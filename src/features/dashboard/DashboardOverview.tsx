import React, { useMemo } from "react";
import { TrendingUp, Recycle, Trash2, CheckCircle, XCircle } from "lucide-react";
import { LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { useAuth } from "../../app/providers/AuthProvider";
import { useSettings } from "../../app/providers/SettingsProvider";
import { formatPipelineTime, type DisposalEvent, usePipelineTotals, useRealtimePipeline } from "../../shared/realtimePipeline";

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

function sideLabel(value: unknown) {
  if (value === "recyclable") return "Recyclable/right";
  if (value === "non_recyclable") return "Non-recyclable/left";
  if (typeof value === "string" && value.trim()) return value.replace(/[_-]+/g, " ");
  return "Not confirmed";
}

function resultLabel(correct: unknown) {
  if (correct === true) return "Correct";
  if (correct === false) return "Incorrect";
  return "Not confirmed";
}

function eventTime(event: DisposalEvent | null | undefined) {
  if (!event?.timestamp) return 0;
  if (typeof event.timestamp === "number") return event.timestamp;
  const parsed = Date.parse(event.timestamp);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export const DashboardOverview: React.FC = () => {
  const { user } = useAuth();
  const { settings } = useSettings();
  const { bins, loading, error } = useRealtimePipeline(user, settings.refreshRate);
  const totals = usePipelineTotals(bins);

  const correctRate = totals.correctDisposals + totals.incorrectDisposals > 0
    ? (totals.correctDisposals / (totals.correctDisposals + totals.incorrectDisposals)) * 100
    : 0;

  const recyclabilityData = [
    { name: "Recyclable", value: totals.recyclableItems, color: "#10b981" },
    { name: "Non-Recyclable", value: totals.nonRecyclableItems, color: "#ef4444" },
  ];

  const dailyData = useMemo(() => {
    return bins.map((bin) => ({
      bin: bin.binCode,
      items: Number(bin.statistics.totalItems || 0),
    }));
  }, [bins]);

  const latestDisposal = useMemo(() => {
    return bins
      .map((bin) => ({
        binCode: bin.binCode,
        orgId: bin.orgId,
        location: bin.location,
        statusMessage: bin.status.message,
        event: bin.events[0] || bin.latestEvent || null,
      }))
      .filter((row): row is {
        binCode: string;
        orgId: string;
        location: string | null | undefined;
        statusMessage: string | undefined;
        event: DisposalEvent;
      } => Boolean(row.event))
      .sort((left, right) => eventTime(right.event) - eventTime(left.event))[0] || null;
  }, [bins]);

  const stats = [
    {
      title: "Total Waste Items",
      value: String(totals.totalItems),
      icon: Trash2,
      bgColor: "bg-blue-50",
      iconColor: "text-blue-600",
    },
    {
      title: "Recyclable Items",
      value: String(totals.recyclableItems),
      icon: Recycle,
      bgColor: "bg-emerald-50",
      iconColor: "text-emerald-600",
    },
    {
      title: "Correct Disposal Rate",
      value: `${correctRate.toFixed(1)}%`,
      icon: CheckCircle,
      bgColor: "bg-green-50",
      iconColor: "text-green-600",
    },
    {
      title: "Normal Bins",
      value: `${totals.normalBins}/${bins.length}`,
      icon: XCircle,
      bgColor: "bg-gray-50",
      iconColor: "text-gray-600",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl text-gray-900 mb-2">Dashboard Overview</h1>
        <p className="text-gray-600">Live Supabase summary from Raspberry Pi updates</p>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat) => (
          <div key={stat.title} className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
            <div className="flex items-start justify-between mb-4">
              <div className={`w-12 h-12 rounded-lg ${stat.bgColor} flex items-center justify-center`}>
                <stat.icon className={`w-6 h-6 ${stat.iconColor}`} />
              </div>
              <div className="flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-emerald-50 text-emerald-700">
                <TrendingUp className="w-3 h-3" />
                Live
              </div>
            </div>
            <h3 className="text-2xl text-gray-900 mb-1">{loading ? "-" : stat.value}</h3>
            <p className="text-sm text-gray-600">{stat.title}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div>
            <h2 className="text-lg text-gray-900">Latest Disposal</h2>
            <p className="text-sm text-gray-600 mt-1">Most recent Pi event, including placement-unconfirmed uploads.</p>
          </div>
          <div className="text-sm text-gray-500">{latestDisposal ? formatPipelineTime(latestDisposal.event.timestamp) : "No event yet"}</div>
        </div>

        {loading ? (
          <div className="mt-5 text-sm text-gray-600">Loading latest event...</div>
        ) : latestDisposal ? (
          <div className="mt-5 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
            <div>
              <p className="text-xs uppercase text-gray-500 mb-1">Bin</p>
              <p className="text-sm text-gray-900 font-medium">{latestDisposal.binCode}</p>
              <p className="text-xs text-gray-500">{latestDisposal.location || latestDisposal.orgId}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-gray-500 mb-1">Category</p>
              <p className="text-sm text-gray-900">{categoryLabel(latestDisposal.event.category, latestDisposal.event.recyclable)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-gray-500 mb-1">Expected Side</p>
              <p className="text-sm text-gray-900">{sideLabel(latestDisposal.event.expectedSide)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-gray-500 mb-1">Disposed Side</p>
              <p className="text-sm text-gray-900">{sideLabel(latestDisposal.event.disposedSide)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-gray-500 mb-1">Result</p>
              <p className={`text-sm font-medium ${latestDisposal.event.correct === true ? "text-emerald-700" : latestDisposal.event.correct === false ? "text-rose-700" : "text-amber-700"}`}>{resultLabel(latestDisposal.event.correct)}</p>
            </div>
          </div>
        ) : (
          <div className="mt-5 text-sm text-gray-600">No disposal event has been received yet.</div>
        )}

        {latestDisposal?.statusMessage && <div className="mt-4 rounded-lg bg-amber-50 border border-amber-100 px-4 py-3 text-sm text-amber-800">{latestDisposal.statusMessage}</div>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <h2 className="text-lg text-gray-900 mb-4">Items By Bin</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={dailyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="bin" stroke="#9ca3af" />
              <YAxis stroke="#9ca3af" />
              <Tooltip contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "8px" }} />
              <Legend />
              <Line type="monotone" dataKey="items" stroke="#10b981" strokeWidth={3} dot={{ fill: "#10b981", r: 4 }} name="Waste Items" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <h2 className="text-lg text-gray-900 mb-4">Recyclability Distribution</h2>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={recyclabilityData} cx="50%" cy="50%" labelLine={false} label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`} outerRadius={100} fill="#8884d8" dataKey="value">
                {recyclabilityData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-6 mt-4">
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-emerald-600 rounded-full" /><span className="text-sm text-gray-600">Recyclable: {totals.recyclableItems}</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-red-500 rounded-full" /><span className="text-sm text-gray-600">Non-Recyclable: {totals.nonRecyclableItems}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
};
