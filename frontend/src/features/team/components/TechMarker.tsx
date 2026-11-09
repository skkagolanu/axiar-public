import { Marker } from 'react-map-gl/maplibre';
import { Navigation2 } from 'lucide-react';

interface TechMarkerProps {
    tech: {
      id: string;
      liveStatus: {
        lat: number;
        lng: number;
        heading: number;
        status: 'available' | 'busy' | 'delayed' | 'offline';
      };
      avatar: string;
      fullName: string;
    };
    onClick: () => void;
}

export function TechMarker({ tech, onClick }: TechMarkerProps) {
  const { lat, lng, heading, status } = tech.liveStatus;

  // Status Ring Colors
  const ringColor = {
    available: 'ring-emerald-500',
    busy: 'ring-violet-500',
    delayed: 'ring-amber-500',
    offline: 'ring-slate-500'
  }[status];

  // Arrow Color
  const arrowColor = {
    available: 'text-emerald-400',
    busy: 'text-violet-400',
    delayed: 'text-amber-400',
    offline: 'text-slate-400'
  }[status];

  // Only show arrow for moving techs
  const isMoving = status === 'busy' || status === 'delayed';

  return (
    <Marker longitude={lng} latitude={lat} anchor="center">
      <div 
        className="relative group cursor-pointer"
        onClick={(e) => {
            e.stopPropagation();
            onClick();
        }}
      >
        {/* The Direction Arrow (Only for moving techs) */}
        {isMoving && (
          <div 
            className="absolute -top-4 left-1/2 -translate-x-1/2 z-20"
            style={{ transform: `translateX(-50%) rotate(${heading}deg)` }}
          >
            <Navigation2 
              className={`w-5 h-5 ${arrowColor} fill-current drop-shadow-lg`} 
              strokeWidth={1.5}
            />
          </div>
        )}

        {/* The Avatar Circle */}
        <div 
          className={`
            relative z-10 w-11 h-11 rounded-full 
            ring-2 ${ringColor} ring-offset-2 ring-offset-slate-900
            bg-slate-800 shadow-xl overflow-hidden
            ${status === 'offline' ? 'grayscale opacity-60' : ''}
            ${status === 'delayed' ? 'animate-pulse' : ''}
          `}
        >
           {tech.avatar ? (
             <img
               src={tech.avatar}
               alt={tech.fullName}
               className="w-full h-full object-cover"
             />
           ) : (
             <span className="flex h-full w-full items-center justify-center text-xs font-bold text-white">
               {tech.fullName.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()}
             </span>
           )}
        </div>

        {/* Tooltip (Visible on hover) */}
        <div 
          className="absolute -bottom-7 left-1/2 -translate-x-1/2 bg-slate-900/95 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-30 shadow-lg"
        >
          {tech.fullName}
          {status === 'delayed' && <span className="text-amber-400 ml-1">(Delayed)</span>}
        </div>
      </div>
    </Marker>
  );
}
