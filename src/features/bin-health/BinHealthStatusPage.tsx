import React, { useMemo } from "react";
import { CheckCircle, XCircle, AlertCircle, Camera, Radio, Wifi, Zap } from "lucide-react";
import { useAuth } from "../../app/providers/AuthProvider";
import { useSettings } from "../../app/providers/SettingsProvider";
import { formatPipelineTime, PipelineBinState, useRealtimePipeline } from "../../shared/realtimePipeline";

interface SensorStatus {
  name: string;
  status: "OK" | "Fault" | "Degraded";
  icon: React.ElementType;
  lastChecked: string;
  details: string;
}

function faultStatus(bin: PipelineBinState, key: string): SensorStatus["status"] {
  return bin.faults[key] ? "Fault" : "OK";
}

function hasFaultKey(bin: PipelineBinState, key: string) {
  return Object.prototype.hasOwnProperty.call(bin.faults, key);
}

function fillDetails(bin: PipelineBinState) {
  const left = typeof bin.sensors.leftFillLevel === "number" ? `${bin.sensors.leftFillLevel}%` : "-";
  const right = typeof bin.sensors.rightFillLevel === "number" ? `${bin.sensors.rightFillLevel}%` : "-";
  if (left !== "-" || right !== "-") return `Left: ${left} / Right: ${right}`;
  return typeof bin.sensors.fillLevel === "number" ? `Overall: ${bin.sensors.fillLevel}%` : "Fill level unavailable";
}

function makeSensors(bin: PipelineBinState): SensorStatus[] {
  const lastChecked = formatPipelineTime(bin.status.lastSeen || bin.latestEvent?.timestamp);
  const sensors: SensorStatus[] = [
    { name: "Ultrasonic Sensor", status: faultStatus(bin, "ultrasonic"), icon: Radio, lastChecked, details: fillDetails(bin) },
    { name: "Camera", status: faultStatus(bin, "camera"), icon: Camera, lastChecked, details: bin.latestEvent?.label ? `Last item: ${bin.latestEvent.label}` : "Waiting for image event" },
    { name: "Network", status: faultStatus(bin, "network"), icon: Wifi, lastChecked, details: (bin.status.state || "unknown").toString() },
  ];
  if (hasFaultKey(bin, "ir")) sensors.splice(0, 0, { name: "IR Sensor", status: faultStatus(bin, "ir"), icon: Radio, lastChecked, details: "Insertion detection channel" });
  if (hasFaultKey(bin, "metal")) sensors.splice(sensors.length - 2, 0, { name: "Metal Sensor", status: faultStatus(bin, "metal"), icon: Zap, lastChecked, details: "Material side detection" });
  return sensors;
}

function computeOverallStatus(bin: PipelineBinState, sensors: SensorStatus[]): "Healthy" | "Warning" | "Critical" {
  if ((bin.status.state || "").toLowerCase() === "faulty") return "Critical";
  if (sensors.some((sensor) => sensor.status === "Fault")) return "Critical";
  if ((bin.status.state || "").toLowerCase() === "maintenance") return "Warning";
  if (sensors.some((sensor) => sensor.status === "Degraded")) return "Warning";
  return "Healthy";
}

export const BinHealthStatusPage: React.FC = () => {
  const { user } = useAuth();
  const { settings } = useSettings();
  const { bins, loading, error } = useRealtimePipeline(user, settings.refreshRate);

  const binHealth = useMemo(() => bins.map((bin) => {
    const sensors = makeSensors(bin);
    return {
      binId: bin.binCode,
      location: bin.location || bin.orgId,
      overallStatus: computeOverallStatus(bin, sensors),
      sensors,
    };
  }), [bins]);

  const healthyCount = binHealth.filter((bin) => bin.overallStatus === "Healthy").length;
  const warningCount = binHealth.filter((bin) => bin.overallStatus === "Warning").length;
  const criticalCount = binHealth.filter((bin) => bin.overallStatus === "Critical").length;

  const getStatusIcon = (status: string) => status === "OK" ? <CheckCircle className="w-5 h-5 text-green-600" /> : status === "Fault" ? <XCircle className="w-5 h-5 text-red-600" /> : <AlertCircle className="w-5 h-5 text-yellow-600" />;
  const getOverallStatusColor = (status: string) => status === "Healthy" ? "border-green-200 bg-gradient-to-br from-green-50 to-white" : status === "Warning" ? "border-yellow-200 bg-gradient-to-br from-yellow-50 to-white" : "border-red-200 bg-gradient-to-br from-red-50 to-white";
  const getOverallStatusBadge = (status: string) => status === "Healthy" ? "bg-green-100 text-green-800" : status === "Warning" ? "bg-yellow-100 text-yellow-800" : "bg-red-100 text-red-800";

  if (!user) {
    return <div className="bg-white rounded-xl border border-gray-100 p-6"><h1 className="text-xl text-gray-900 mb-2">Bin Health Status</h1><p className="text-gray-600">Please login to view bin health.</p></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl text-gray-900 mb-2">Bin Health Status</h1>
        <p className="text-gray-600">{user.superAdmin ? "System-wide cloud sensor health" : `Sensor health monitoring (Org: ${user.orgId})`}</p>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gradient-to-br from-green-50 to-white rounded-xl shadow-sm p-6 border border-green-100"><div className="flex items-center gap-3"><div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center"><CheckCircle className="w-7 h-7 text-green-600" /></div><div><p className="text-3xl text-green-600">{loading ? "-" : healthyCount}</p><p className="text-sm text-gray-600">Healthy Bins</p></div></div></div>
        <div className="bg-gradient-to-br from-yellow-50 to-white rounded-xl shadow-sm p-6 border border-yellow-100"><div className="flex items-center gap-3"><div className="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center"><AlertCircle className="w-7 h-7 text-yellow-600" /></div><div><p className="text-3xl text-yellow-600">{loading ? "-" : warningCount}</p><p className="text-sm text-gray-600">Warning State</p></div></div></div>
        <div className="bg-gradient-to-br from-red-50 to-white rounded-xl shadow-sm p-6 border border-red-100"><div className="flex items-center gap-3"><div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center"><XCircle className="w-7 h-7 text-red-600" /></div><div><p className="text-3xl text-red-600">{loading ? "-" : criticalCount}</p><p className="text-sm text-gray-600">Critical State</p></div></div></div>
      </div>

      <div className="space-y-6">
        {loading ? <div className="text-gray-600">Loading bins...</div> : binHealth.length === 0 ? <div className="text-gray-600">No cloud bin state found.</div> : binHealth.map((bin) => (
          <div key={bin.binId} className={`rounded-xl shadow-sm p-6 border-2 ${getOverallStatusColor(bin.overallStatus)}`}>
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
              <div><div className="flex items-center gap-3 mb-2"><h2 className="text-xl text-gray-900">{bin.binId}</h2><span className={`px-3 py-1 rounded-full text-xs ${getOverallStatusBadge(bin.overallStatus)}`}>{bin.overallStatus}</span></div><p className="text-gray-600">{bin.location}</p></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              {bin.sensors.map((sensor) => {
                const IconComponent = sensor.icon;
                return <div key={sensor.name} className="bg-white rounded-lg p-4 border border-gray-200"><div className="flex items-center justify-between mb-3"><div className="flex items-center gap-2"><IconComponent className="w-5 h-5 text-gray-600" /><span className="text-sm text-gray-900">{sensor.name}</span></div>{getStatusIcon(sensor.status)}</div><div className="space-y-1"><p className="text-xs text-gray-500">{sensor.details}</p><p className="text-xs text-gray-400">{sensor.lastChecked}</p></div></div>;
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
