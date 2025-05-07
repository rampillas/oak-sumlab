import depthai as dai
from typing import List, Dict, Deque
from collections import deque
import numpy as np
from config_loader import load_config #Import the function
# Load Config
config = load_config()


THRESH_DIST_DELTA = config["vehicle_tracker"]["threshold_dist_delta"]  # Umbral mínimo para considerar movimiento
MAX_HISTORY = config["vehicle_tracker"]["max_history"] # Número de posiciones almacenadas por vehículo
MAX_HISTORY_POSITIONS = config["vehicle_tracker"]["max_history_positions"] # Número de posiciones almacenadas por vehículo


class VehicleTracker:
    def __init__(self) -> None:
        self.data: Dict[str, Dict] = {}  # Almacena los vehículos detectados
        self.counter = {'ascending': 0, 'descending': 0}  # Contador de movimientos
        

    def _print(self, vehicle_id, direction):
        print(f"Vehicle {vehicle_id} is moving {direction.upper()}")

    def _get_centroid(self, roi) -> tuple:
        """Calcula el centro del bounding box del objeto detectado."""
        x1, y1 = roi.topLeft().x, roi.topLeft().y
        x2, y2 = roi.bottomRight().x, roi.bottomRight().y
        return ((x1 + x2) / 2, (y1 + y2) / 2)  # Centro del objeto

    def _calculate_direction(self, positions: Deque) -> str:
        """Determina si el vehículo se mueve hacia arriba (ascending) o abajo (descending)."""
        if len(positions) < 2:
            return "unknown"  # No hay suficiente información

        # Calcular la pendiente usando los primeros y últimos puntos almacenados
        y_start = positions[0][1]
        y_end = positions[-1][1]
        deltaY = y_end - y_start

        if abs(deltaY) > THRESH_DIST_DELTA:
            return "ascending" if deltaY < 0 else "descending"
        return "unknown"

    def calculate_tracklet_movement(self, tracklets: dai.Tracklets) -> Dict[str, str]:
        movement_directions = {}

        for t in tracklets:
            tracklet_id = str(t.id)

            # Si es un nuevo tracklet, inicializar su historial de posiciones
            if t.status == dai.Tracklet.TrackingStatus.NEW:
                self.data[tracklet_id] = {
                    "positions": deque(maxlen=MAX_HISTORY),  # Últimas X posiciones
                    "lostCnt": 0,
                    "historial": deque(maxlen=MAX_HISTORY_POSITIONS)
                }
            
            # Obtener la nueva posición
            new_position = self._get_centroid(t.roi)

            if t.status in [dai.Tracklet.TrackingStatus.NEW, dai.Tracklet.TrackingStatus.TRACKED]:
                try:
                    self.data[tracklet_id]["positions"].append(new_position)
                    self.data[tracklet_id]["lostCnt"] = 0  # Reiniciar el contador de pérdida

                    # Calcular la dirección si hay suficientes datos
                    direction = self._calculate_direction(self.data[tracklet_id]["positions"])
                    if direction in ["ascending", "descending"]:
                        #self._print(tracklet_id, direction)
                        self.data[tracklet_id]["historial"].append(direction)
                        movement_directions[int(tracklet_id)] = self.data[tracklet_id]["historial"]
                    else: 
                        self.data[tracklet_id]["historial"].append('undefined')
                        movement_directions[int(tracklet_id)] = self.data[tracklet_id]["historial"]
                except KeyError:
                    print('KeyError')
                    pass

            elif t.status == dai.Tracklet.TrackingStatus.LOST:
                try:
                    self.data[tracklet_id]["lostCnt"] += 1
                    # Si el objeto se ha perdido por más de 10 frames, eliminarlo
                    if self.data[tracklet_id]["lostCnt"] > 10:
                        if tracklet_id in self.data:
                            del self.data[tracklet_id]
                except KeyError:
                    pass

                

            elif t.status == dai.Tracklet.TrackingStatus.REMOVED:
                if tracklet_id in self.data:
                    del self.data[tracklet_id]

        return movement_directions  # Devuelve un diccionario con el ID y la dirección detectada
