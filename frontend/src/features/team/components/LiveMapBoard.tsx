import Map, { NavigationControl } from 'react-map-gl/maplibre';
import maplibregl, { type StyleSpecification } from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { layers, namedFlavor } from '@protomaps/basemaps';
import 'maplibre-gl/dist/maplibre-gl.css';
import { TechMarker } from './TechMarker';
import { RoutePolyline } from './RoutePolyline';
import type { TeamMember, ActiveRoute } from '../types';

interface LiveMapBoardProps {
  technicians: TeamMember[];
  routes: ActiveRoute[];
  onTechClick: (techId: string) => void;
}

const INITIAL_VIEW = {
  longitude: -0.1276,
  latitude: 51.5074,
  zoom: 11
};

const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

// Labels need remote glyph assets. The demo intentionally keeps only the local
// geometry layers so loading the dispatch map never depends on another origin.
const DEMO_MAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    protomaps: {
      type: 'vector',
      url: `pmtiles://${window.location.origin}/maps/london.pmtiles`,
      attribution:
        '<a href="https://github.com/protomaps/basemaps">Protomaps</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    },
  },
  layers: layers('protomaps', namedFlavor('dark')),
};

export function LiveMapBoard({ technicians, routes, onTechClick }: LiveMapBoardProps) {
  const mapStyle = import.meta.env.VITE_MAP_STYLE || DEMO_MAP_STYLE;

  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-secondary shadow-2xl relative">
      <Map
        initialViewState={INITIAL_VIEW}
        style={{ width: '100%', height: '100%' }}
        mapStyle={mapStyle}
        attributionControl={{ compact: true }}
      >
        <NavigationControl position="top-right" showCompass={false} />

        {/* 1. Render Active Routes (The Lines) */}
        {routes.map((route) => (
          <RoutePolyline 
            key={route.id || route.techId} 
            id={route.id || route.techId}
            geometry={route.geometry} 
            status={route.status} 
          />
        ))}

        {/* 2. Render Technicians (The Cars/Avatars) */}
        {technicians.map((tech) => (
          <TechMarker 
            key={tech.id} 
            tech={tech} 
            onClick={() => onTechClick(tech.id)} 
          />
        ))}
      </Map>
      
      {/* Legend Overlay */}
      <div className="absolute top-4 left-4 bg-secondary/90 border border-slate-700 p-3 rounded-lg backdrop-blur-sm shadow-xl">
        <h4 className="text-xs font-bold text-slate-300 mb-2 font-heading uppercase tracking-wider">Fleet Status</h4>
        <div className="space-y-2 text-xs">
           <div className="flex items-center gap-2 text-slate-400">
             <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
             Available
           </div>
           <div className="flex items-center gap-2 text-slate-400">
             <div className="w-2 h-2 rounded-full bg-violet-500 shadow-[0_0_8px_rgba(124,58,237,0.5)]"></div>
             Busy (On Route)
           </div>
           <div className="flex items-center gap-2 text-slate-400">
             <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.5)]"></div>
             Delayed
           </div>
        </div>
      </div>
    </div>
  );
}
