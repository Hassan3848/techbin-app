import React, { useMemo, useState } from "react";
import { CircleAlert, CheckCircle, Clock, Camera, Radio, Wifi } from "lucide-react";
import { useAuth } from "../../app/providers/AuthProvider";
import { useSettings } from "../../app/providers/SettingsProvider";
import { formatPipelineTime, PipelineBinState, useRealtimePipeline } from "../../shared/realtimePipeline";

type Filter = "all" | "Critical" | "Warning" | "Resolved";

type Fault = {
  id: string;
  binId: string;
  component: string;
  severity: "Critical" | "Warning" | "Normal";
  timestamp: string;
  description: string;
  status: "Resolved" | "Unresolved";
};

function componentLabel(key: string) {
  return key.replace(/([A-Z])/g, " $1").replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function faultsFromBin(bin: PipelineBinState): Fault[] {
  const timestamp = formatPipelineTime(bin.status.lastSeen || bin.latestEvent?.timestamp);
  const activeFaults = Object.entries(bin.faults).filter(([, active]) => active);

  if (activeFaults.length === 0 && (bin.status.state || "").toLowerCase() === "normal") {
    return [{
      id: `${bin.orgId}_${bin.binCode}_normal`,
      binId: bin.binCode,
      component: "System",
      severity: "Normal",
      timestamp,
      description: "System recovered and reports normal state",
      status: "Resolved",
    }];
  }

  return activeFaults.map(([key]) => ({
    id: `${bin.orgId}_${bin.binCode}_${key}`,
    binId: bin.binCode,
    component: componentLabel(key),
    severity: "Critical",
    timestamp,
    description: `${componentLabel(key)} failure reported by Raspberry Pi`,
    status: "Unresolved",
  }));
}

export const FaultDetectionPage: React.FC = () => {
  const { user } = useAuth();
  const { settings } = useSettings();
  const { bins, loading, error } = useRealtimePipeline(user, settings.refreshRate);
  const [filter, setFilter] = useState<Filter>("all");

  const faults = useMemo(() => bins.flatMap(faultsFromBin), [bins]);
  const filteredFaults = faults.filter((fault) => {
    if (filter === "all") return true;
    if (filter === "Resolved") return fault.status === "Resolved";
    return fault.severity === filter;
  });

  const criticalCount = faults.filter((f) => f.severity === "Critical" && f.status === "Unresolved").length;
  const warningCount = faults.filter((f) => f.severity === "Warning" && f.status === "Unresolved").length;
  const resolvedCount = faults.filter((f) => f.status === "Resolved").length;

  const getSeverityColor = (severity: string) => severity === "Critical" ? "bg-red-100 text-red-800 border-red-200" : severity === "Warning" ? "bg-yellow-100 text-yellow-800 border-yellow-200" : "bg-green-100 text-green-800 border-green-200";
  const getSeverityIcon = (severity: string) => severity === "Normal" ? <CheckCircle className="w-5 h-5 text-green-600" /> : <CircleAlert className={`w-5 h-5 ${severity === "Critical" ? "text-red-600" : "text-yellow-600"}`} />;
  const getComponentIcon = (component: string) => component.toLowerCase().includes("camera") ? <Camera className="w-5 h-5" /> : component.toLowerCase().includes("network") || component.toLowerCase().includes("wifi") ? <Wifi className="w-5 h-5" /> : <Radio className="w-5 h-5" />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl text-gray-900 mb-2">Fault Detection</h1>
        <p className="text-gray-600">Live fault state from Supabase</p>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gradient-to-br from-red-50 to-white rounded-xl shadow-sm p-6 border border-red-100"><div className="flex items-center gap-3"><div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center"><CircleAlert className="w-6 h-6 text-red-600" /></div><div><p className="text-3xl text-red-600">{loading ? "-" : criticalCount}</p><p className="text-sm text-gray-600">Critical Faults</p></div></div></div>
        <div className="bg-gradient-to-br from-yellow-50 to-white rounded-xl shadow-sm p-6 border border-yellow-100"><div className="flex items-center gap-3"><div className="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center"><CircleAlert className="w-6 h-6 text-yellow-600" /></div><div><p className="text-3xl text-yellow-600">{loading ? "-" : warningCount}</p><p className="text-sm text-gray-600">Warnings</p></div></div></div>
        <div className="bg-gradient-to-br from-green-50 to-white rounded-xl shadow-sm p-6 border border-green-100"><div className="flex items-center gap-3"><div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"><CheckCircle className="w-6 h-6 text-green-600" /></div><div><p className="text-3xl text-green-600">{loading ? "-" : resolvedCount}</p><p className="text-sm text-gray-600">Resolved</p></div></div></div>
      </div>

      <div className="flex flex-wrap gap-2">
        {(["all", "Critical", "Warning", "Resolved"] as Filter[]).map((item) => <button key={item} onClick={() => setFilter(item)} className={`px-4 py-2 rounded-lg transition-colors ${filter === item ? "bg-emerald-600 text-white" : "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50"}`}>{item === "all" ? "All Faults" : item}</button>)}
      </div>

      <div className="space-y-4">
        {loading ? <div className="text-gray-600">Loading faults...</div> : filteredFaults.length === 0 ? <div className="text-gray-600">No faults reported by Supabase.</div> : filteredFaults.map((fault) => (
          <div key={fault.id} className={`bg-white rounded-xl shadow-sm p-6 border ${getSeverityColor(fault.severity)}`}>
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div className="flex items-start gap-4 flex-1">
                <div className="flex-shrink-0">{getSeverityIcon(fault.severity)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2 flex-wrap">
                    <span className="px-3 py-1 bg-emerald-50 text-emerald-800 rounded-full text-xs">{fault.binId}</span>
                    <div className="flex items-center gap-1 px-3 py-1 bg-blue-50 text-blue-800 rounded-full text-xs">{getComponentIcon(fault.component)}<span>{fault.component}</span></div>
                  </div>
                  <p className="text-gray-900 mb-2">{fault.description}</p>
                  <div className="flex items-center gap-2 text-sm text-gray-500"><Clock className="w-4 h-4" /><span>{fault.timestamp}</span></div>
                </div>
              </div>
              <span className={`px-4 py-2 rounded-lg text-sm ${fault.status === "Resolved" ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"}`}>{fault.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
