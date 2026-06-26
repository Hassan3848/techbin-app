import React, { useMemo } from "react";
import { TrendingUp, Recycle, Trash2, CheckCircle, XCircle } from "lucide-react";
import { LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { useAuth } from "../../app/providers/AuthProvider";
import { useSettings } from "../../app/providers/SettingsProvider";
import { usePipelineTotals, useRealtimePipeline } from "../../shared/realtimePipeline";

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
