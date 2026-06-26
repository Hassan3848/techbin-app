import React, { useMemo, useState } from "react";
import { BarChart, Bar, LineChart, Line, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { useAuth } from "../../app/providers/AuthProvider";
import { useSettings } from "../../app/providers/SettingsProvider";
import { usePipelineTotals, useRealtimePipeline } from "../../shared/realtimePipeline";

const CATEGORY_KEYS = ["cardboard", "paper", "plastic_glass", "metal", "trash"];

const NON_RECYCLABLE_CATEGORIES = new Set(["trash"]);

function categoryLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("/");
}

export const AnalyticsPage: React.FC = () => {
  const { user } = useAuth();
  const { settings } = useSettings();
  const { bins, loading, error } = useRealtimePipeline(user, settings.refreshRate);
  const totals = usePipelineTotals(bins);
  const [selectedBin, setSelectedBin] = useState("all");

  const visibleBins = selectedBin === "all" ? bins : bins.filter((bin) => bin.binCode === selectedBin);

  const wasteCategories = useMemo(() => {
    return CATEGORY_KEYS.map((key) => ({
      category: categoryLabel(key),
      recyclable: NON_RECYCLABLE_CATEGORIES.has(key) ? 0 : visibleBins.reduce((sum, bin) => sum + Number(bin.statistics[key] || 0), 0),
      nonRecyclable: NON_RECYCLABLE_CATEGORIES.has(key) ? visibleBins.reduce((sum, bin) => sum + Number(bin.statistics[key] || 0), 0) : 0,
    }));
  }, [visibleBins]);

  const disposalTrend = useMemo(() => visibleBins.map((bin) => ({
    bin: bin.binCode,
    correct: Number(bin.statistics.correctDisposals || 0),
    incorrect: Number(bin.statistics.incorrectDisposals || 0),
  })), [visibleBins]);

  const filteredTotals = usePipelineTotals(visibleBins);
  const totalRecyclability = filteredTotals.recyclableItems + filteredTotals.nonRecyclableItems;
  const recyclabilityRate = totalRecyclability > 0 ? (filteredTotals.recyclableItems / totalRecyclability) * 100 : 0;
  const totalCorrectness = filteredTotals.correctDisposals + filteredTotals.incorrectDisposals;
  const accuracyRate = totalCorrectness > 0 ? (filteredTotals.correctDisposals / totalCorrectness) * 100 : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl text-gray-900 mb-2">Analytics</h1>
          <p className="text-gray-600">Supabase analytics counters supplied by Raspberry Pi</p>
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-700 mb-2">Data Source</label>
            <div className="w-full px-4 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700">Supabase Realtime live counters</div>
          </div>
          <div>
            <label className="block text-sm text-gray-700 mb-2">Bin ID</label>
            <select value={selectedBin} onChange={(e) => setSelectedBin(e.target.value)} className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500">
              <option value="all">All Bins</option>
              {bins.map((bin) => <option key={`${bin.orgId}_${bin.binCode}`} value={bin.binCode}>{bin.binCode}</option>)}
            </select>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <h2 className="text-lg text-gray-900 mb-6">Waste Category Distribution</h2>
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={wasteCategories}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="category" stroke="#9ca3af" />
              <YAxis stroke="#9ca3af" />
              <Tooltip contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "8px" }} />
              <Legend />
              <Bar dataKey="recyclable" fill="#10b981" name="Recyclable" radius={[8, 8, 0, 0]} />
              <Bar dataKey="nonRecyclable" fill="#ef4444" name="Non-Recyclable" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <h2 className="text-lg text-gray-900 mb-6">Disposal Correctness By Bin</h2>
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={disposalTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="bin" stroke="#9ca3af" />
              <YAxis stroke="#9ca3af" />
              <Tooltip contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "8px" }} />
              <Legend />
              <Line type="monotone" dataKey="correct" stroke="#10b981" strokeWidth={3} dot={{ fill: "#10b981", r: 5 }} name="Correct Disposal" />
              <Line type="monotone" dataKey="incorrect" stroke="#ef4444" strokeWidth={3} dot={{ fill: "#ef4444", r: 5 }} name="Incorrect Disposal" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-gradient-to-br from-emerald-50 to-white rounded-xl shadow-sm p-6 border border-emerald-100"><h3 className="text-sm text-gray-600 mb-2">Recyclability Rate</h3><p className="text-3xl text-emerald-600 mb-1">{loading ? "-" : `${recyclabilityRate.toFixed(1)}%`}</p><p className="text-xs text-gray-500">{filteredTotals.recyclableItems} recyclable items</p></div>
          <div className="bg-gradient-to-br from-green-50 to-white rounded-xl shadow-sm p-6 border border-green-100"><h3 className="text-sm text-gray-600 mb-2">Accuracy Rate</h3><p className="text-3xl text-green-600 mb-1">{loading ? "-" : `${accuracyRate.toFixed(1)}%`}</p><p className="text-xs text-gray-500">{filteredTotals.correctDisposals} correct disposals</p></div>
          <div className="bg-gradient-to-br from-blue-50 to-white rounded-xl shadow-sm p-6 border border-blue-100"><h3 className="text-sm text-gray-600 mb-2">Total Items Processed</h3><p className="text-3xl text-blue-600 mb-1">{loading ? "-" : filteredTotals.totalItems}</p><p className="text-xs text-gray-500">All selected cloud counters</p></div>
        </div>

        {!loading && totals.totalItems === 0 && <div className="text-sm text-gray-600">No analytics counters have been written by the Pi yet.</div>}
      </div>
    </div>
  );
};
