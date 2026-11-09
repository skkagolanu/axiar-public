from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Tuple

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


class RouteOptimizationService:
    def __init__(self):
        self.enabled = ORTOOLS_AVAILABLE

    async def optimize_route(self, stops: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Optimize route for multiple stops"""
        if not stops or len(stops) < 2:
            return {"optimized_order": stops, "total_distance_km": 0, "total_time_minutes": 0}

        if not self.enabled:
            return {
                "optimized_order": stops,
                "total_distance_km": len(stops) * 5,
                "total_time_minutes": len(stops) * 20,
                "method": "fallback",
            }

        distance_matrix = self._get_distance_matrix(stops)

        manager = pywrapcp.RoutingIndexManager(len(stops), 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            return {"optimized_order": stops, "total_distance_km": 0, "total_time_minutes": 0, "method": "failed"}

        index = routing.Start(0)
        optimized_order = []
        total_distance = 0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            optimized_order.append(stops[node])
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            total_distance += routing.GetArcCostForVehicle(previous_index, index, 0)

        return {
            "optimized_order": optimized_order,
            "total_distance_km": round(total_distance / 1000, 2),
            "total_time_minutes": int(total_distance / 1000 * 3),
            "method": "ortools",
        }

    def _get_distance_matrix(self, stops: List[Dict[str, Any]]) -> List[List[int]]:
        n = len(stops)
        matrix = [[0] * n for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i != j:
                    lat1, lon1 = stops[i]["latitude"], stops[i]["longitude"]
                    lat2, lon2 = stops[j]["latitude"], stops[j]["longitude"]
                    matrix[i][j] = int(self._haversine_distance(lat1, lon1, lat2, lon2) * 1000)

        return matrix

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    async def estimate_travel_time(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> Dict[str, Any]:
        distance_km = self._haversine_distance(from_coords[0], from_coords[1], to_coords[0], to_coords[1])
        time_minutes = int((distance_km / 30) * 60)

        return {
            "distance_km": round(distance_km, 2),
            "estimated_time_minutes": time_minutes,
            "estimated_arrival": (datetime.utcnow() + timedelta(minutes=time_minutes)).isoformat(),
        }


route_optimizer = RouteOptimizationService()
