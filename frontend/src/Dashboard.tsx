import { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, GeoJSON, Tooltip } from 'react-leaflet'
import { AlertTriangle, CheckCircle, Info, Map as MapIcon, Loader2, ArrowRight } from 'lucide-react'
import axios from 'axios'
import 'leaflet/dist/leaflet.css'

interface DashboardProps {
  fileId: string;
}

export default function Dashboard({ fileId }: DashboardProps) {
  const [status, setStatus] = useState<string>('PROCESSING')
  const [summary, setSummary] = useState<any>(null)
  const [features, setFeatures] = useState<any[]>([])
  const [measurements, setMeasurements] = useState<any[]>([])
  
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    
    const checkStatus = async () => {
      try {
        const res = await axios.get(`http://localhost:8000/api/v1/files/${fileId}`)
        setStatus(res.data.status)
        if (res.data.status === 'COMPLETED' || res.data.status === 'FAILED') {
          clearInterval(interval)
          if (res.data.status === 'COMPLETED') {
            loadData()
          } else {
            setLoading(false)
          }
        }
      } catch (err) {
        console.error(err)
      }
    }
    
    if (status === 'PROCESSING' || status === 'PENDING') {
      interval = setInterval(checkStatus, 1500)
    }
    
    return () => clearInterval(interval)
  }, [fileId, status])

  const loadData = async () => {
    try {
      const [sumRes, featRes, measRes] = await Promise.all([
        axios.get(`http://localhost:8000/api/v1/files/${fileId}/summary`),
        axios.get(`http://localhost:8000/api/v1/files/${fileId}/features`),
        axios.get(`http://localhost:8000/api/v1/files/${fileId}/measurements`)
      ])
      
      setSummary(sumRes.data)
      setFeatures(featRes.data.features)
      setMeasurements(measRes.data.measurements)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const mapBounds = useMemo(() => {
    if (!features.length) return null
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    let hasBounds = false
    
    features.forEach(f => {
      if (f.bbox) {
        hasBounds = true
        minX = Math.min(minX, f.bbox[0])
        minY = Math.min(minY, f.bbox[1])
        maxX = Math.max(maxX, f.bbox[2])
        maxY = Math.max(maxY, f.bbox[3])
      }
    })
    
    if (hasBounds) {
      return [
        [minY, minX],
        [maxY, maxX]
      ] as [number, number][]
    }
    return null
  }, [features])

  if (loading || status === 'PROCESSING') {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-textDim gap-4">
        <Loader2 className="w-12 h-12 animate-spin text-primary" />
        <h3 className="text-xl font-medium text-text">Analyzing Geospatial Data...</h3>
        <p>Detecting CRS, validating geometry, and calculating accurate measurements.</p>
      </div>
    )
  }

  if (status === 'FAILED') {
    return (
      <div className="glass-panel p-8 text-center text-error border-error/20 flex flex-col items-center gap-4">
        <AlertTriangle className="w-12 h-12" />
        <h3 className="text-xl font-bold">Processing Failed</h3>
        <p className="text-textDim">The file could not be parsed or contained critical errors.</p>
      </div>
    )
  }

  if (!summary) return null

  const tableData = features.map(f => {
    const m = measurements.find(meas => meas.feature_id === f.id)
    return { ...f, measurement: m }
  })

  const downloadCSV = () => {
    const headers = ['ID', 'Type', 'Area (ha)', 'Length (m)', 'Status'];
    const rows = tableData.map(row => [
      row.feature_index,
      row.geometry_type,
      row.measurement?.polygon_measurement?.area_hectares?.toFixed(4) || '',
      row.measurement?.line_measurement?.length_m?.toFixed(2) || '',
      row.measurement?.quality?.valid === false ? 'Invalid' : (row.measurement?.quality?.repaired ? 'Repaired' : 'Valid')
    ]);
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows.map(e => e.join(','))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `report_${fileId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const downloadJSON = () => {
    const exportData = { summary, features: tableData };
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
    const link = document.createElement("a");
    link.setAttribute("href", dataStr);
    link.setAttribute("download", `report_${fileId}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="flex flex-col gap-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="glass-panel p-6 lg:col-span-3 bg-gradient-to-br from-surface to-surfaceHighlight/50 border-primary/20">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-primary/10 text-primary rounded-xl">
              <MapIcon className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-1">Coordinate System Intelligence</h3>
              <p className="text-sm text-textDim mb-4">
                To guarantee physically accurate measurements, geographic coordinates were automatically projected into a metric system.
              </p>
              
              <div className="flex flex-wrap items-center gap-4 text-sm font-medium">
                <div className="px-4 py-2 bg-surface rounded-lg border border-border">
                  <span className="text-textDim text-xs block uppercase tracking-wide mb-1">Source CRS</span>
                  <span className="text-text">{summary.crs.source_crs}</span>
                </div>
                
                <ArrowRight className="w-5 h-5 text-textDim" />
                
                <div className="px-4 py-2 bg-primary/10 border border-primary/30 rounded-lg">
                  <span className="text-textDim text-xs block uppercase tracking-wide mb-1 text-primary/80">Measurement CRS</span>
                  <span className="text-primary">{summary.crs.measurement_crs}</span>
                </div>
                
                <div className="px-4 py-2 bg-surface rounded-lg border border-border ml-auto">
                  <span className="text-textDim text-xs block uppercase tracking-wide mb-1">Strategy</span>
                  <span className="text-text">{summary.crs.crs_strategy}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Features</span>
          <span className="stat-value text-text">{summary.feature_count}</span>
          <div className="text-xs text-textDim mt-auto pt-2 border-t border-border flex justify-between">
            <span>Polygons: {summary.geometry_distribution.Polygon}</span>
            <span>Lines: {summary.geometry_distribution.LineString}</span>
          </div>
        </div>
        
        <div className="stat-card">
          <span className="stat-label">Total Area</span>
          <span className="stat-value text-secondary">
            {summary.area_summary.total_area_hectares.toFixed(2)} ha
          </span>
          <div className="text-xs text-textDim mt-auto pt-2 border-t border-border flex justify-between">
            <span>{summary.area_summary.total_area_m2.toLocaleString(undefined, {maximumFractionDigits: 0})} m²</span>
            <span>{summary.area_summary.total_area_km2.toFixed(4)} km²</span>
          </div>
        </div>
        
        <div className="stat-card">
          <span className="stat-label">Total Length</span>
          <span className="stat-value text-accent">
            {summary.length_summary.total_length_km.toFixed(2)} km
          </span>
          <div className="text-xs text-textDim mt-auto pt-2 border-t border-border flex justify-between">
            <span>{summary.length_summary.total_length_m.toLocaleString(undefined, {maximumFractionDigits: 0})} m</span>
          </div>
        </div>
      </div>
      {summary.quality.warning_count > 0 && (
        <div className="glass-panel p-6 border-warning/30 bg-warning/5">
          <div className="flex items-center gap-2 text-warning mb-4">
            <AlertTriangle className="w-5 h-5" />
            <h3 className="font-semibold text-lg">Quality Warnings ({summary.quality.warning_count})</h3>
          </div>
          <div className="space-y-2">
            {summary.quality.warnings.slice(0, 5).map((w: any, idx: number) => (
              <div key={idx} className="text-sm bg-surface/50 p-3 rounded-lg border border-border flex items-start gap-3">
                {w.severity === 'WARNING' ? <AlertTriangle className="w-4 h-4 text-warning mt-0.5 shrink-0" /> : <Info className="w-4 h-4 text-primary mt-0.5 shrink-0" />}
                <div>
                  <span className="font-medium mr-2">[{w.code}]</span>
                  <span className="text-textDim">{w.message}</span>
                  {w.feature_index !== undefined && <span className="text-textDim block mt-0.5 text-xs">Feature Index: {w.feature_index}</span>}
                </div>
              </div>
            ))}
            {summary.quality.warnings.length > 5 && (
              <p className="text-sm text-textDim pl-7 pt-2">...and {summary.quality.warnings.length - 5} more warnings.</p>
            )}
          </div>
        </div>
      )}
      <div className="glass-panel p-1 border-border/50 h-[500px] rounded-2xl overflow-hidden relative shadow-2xl">
        <div className="absolute top-4 left-4 z-[1000] bg-surface/90 backdrop-blur px-4 py-2 rounded-lg border border-border shadow-lg text-sm font-medium">
          Uploaded Geometry Map
        </div>
        <MapContainer 
          bounds={mapBounds as any || undefined} 
          center={!mapBounds ? [0, 0] : undefined}
          zoom={!mapBounds ? 2 : undefined}
          scrollWheelZoom={true} 
          className="h-full w-full bg-[#0a0a0a]"
        >
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
            attribution='Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
          />
          {features.map((f) => f.geometry_geojson && (
            <GeoJSON 
              key={f.id} 
              data={f.geometry_geojson as any} 
              style={() => ({
                color: f.geometry_type?.includes('Line') ? '#8B5CF6' : '#10B981',
                weight: 2,
                opacity: 0.8,
                fillColor: '#10B981',
                fillOpacity: 0.2
              })}
            >
              <Tooltip className="!bg-surface !text-text !border-border !rounded-lg !shadow-xl">
                <div className="flex flex-col gap-1 text-sm">
                  <span className="font-bold text-primary">Feature {f.feature_index}</span>
                  <span>Type: {f.geometry_type}</span>
                  {f.properties?.name && <span>Name: {f.properties.name}</span>}
                </div>
              </Tooltip>
            </GeoJSON>
          ))}
        </MapContainer>
      </div>
      <div className="glass-panel overflow-hidden border-border/50">
        <div className="p-4 border-b border-border bg-surfaceHighlight/30 flex items-center justify-between">
          <h3 className="font-semibold text-lg">Feature Details & Measurements</h3>
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium px-2 py-1 bg-surface rounded text-textDim border border-border">
              Showing all {features.length} features
            </span>
            <button onClick={downloadCSV} className="btn-secondary text-xs px-3 py-1.5 h-auto">
              Export CSV
            </button>
            <button onClick={downloadJSON} className="btn-secondary text-xs px-3 py-1.5 h-auto">
              Export JSON
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-textDim uppercase bg-surface/50 border-b border-border">
              <tr>
                <th className="px-6 py-4 font-medium">ID</th>
                <th className="px-6 py-4 font-medium">Type</th>
                <th className="px-6 py-4 font-medium">Area (hectares)</th>
                <th className="px-6 py-4 font-medium">Length (meters)</th>
                <th className="px-6 py-4 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tableData.map((row) => (
                <tr key={row.id} className="hover:bg-surfaceHighlight/20 transition-colors">
                  <td className="px-6 py-4 font-medium text-text">{row.feature_index}</td>
                  <td className="px-6 py-4 text-textDim">{row.geometry_type}</td>
                  <td className="px-6 py-4">
                    {row.measurement?.polygon_measurement 
                      ? <span className="text-secondary font-medium">{row.measurement.polygon_measurement.area_hectares.toFixed(4)}</span> 
                      : <span className="text-border">-</span>}
                  </td>
                  <td className="px-6 py-4">
                    {row.measurement?.line_measurement 
                      ? <span className="text-accent font-medium">{row.measurement.line_measurement.length_m.toFixed(2)}</span> 
                      : <span className="text-border">-</span>}
                  </td>
                  <td className="px-6 py-4">
                    {row.measurement?.quality?.valid === false ? (
                      <span className="text-error flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Invalid</span>
                    ) : row.measurement?.quality?.repaired ? (
                      <span className="text-warning flex items-center gap-1"><Info className="w-3 h-3" /> Repaired</span>
                    ) : (
                      <span className="text-secondary flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Valid</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
    </div>
  )
}
