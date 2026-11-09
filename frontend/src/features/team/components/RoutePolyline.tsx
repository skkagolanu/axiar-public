import { useId } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';

interface RoutePolylineProps {
  id?: string; // Add ID prop to ensure uniqueness
  geometry: any; // GeoJSON LineString
  status: 'normal' | 'delayed';
}

export function RoutePolyline({ id, geometry, status }: RoutePolylineProps) {
  const generatedId = useId();
  // Color Logic: Violet for normal, Amber for delay
  const lineColor = status === 'delayed' ? '#F59E0B' : '#7C3AED';
  const layerId = id || `route-${generatedId.replace(/:/g, '')}`;
  
  return (
    <Source id={`source-${layerId}`} type="geojson" data={geometry}>
      {/* The Glow Effect (Underneath) */}
      <Layer
        id={`layer-glow-${layerId}`}
        type="line"
        paint={{
          'line-color': lineColor,
          'line-width': 8,
          'line-opacity': 0.3,
          'line-blur': 4
        }}
      />
      {/* The Sharp Line (Top) */}
      <Layer
        id={`layer-core-${layerId}`}
        type="line"
        layout={{
          'line-join': 'round',
          'line-cap': 'round'
        }}
        paint={{
          'line-color': lineColor,
          'line-width': 3
        }}
      />
    </Source>
  );
}
