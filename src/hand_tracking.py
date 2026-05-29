# ============================================================
#  hand_tracking.py — Module de Computer Vision
#
#  Responsabilités :
#    1. Capture vidéo (thread dédié, non-bloquant)
#    2. Détection des 21 landmarks via MediaPipe Hands
#    3. Lissage des coordonnées (filtre EMA)
#    4. Normalisation vers l'espace scène 3D
#    5. Reconnaissance de gestes (pince, poing, index pointé)
#    6. Affichage overlay dans la fenêtre OpenCV
# ============================================================

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import cv2
import mediapipe as mp

from src.config import (
    CAMERA_INDEX,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    FRAME_TARGET_FPS,
    MP_MAX_HANDS,
    MP_DETECTION_CONFIDENCE,
    MP_TRACKING_CONFIDENCE,
    SMOOTH_ALPHA,
    SCENE_X_RANGE,
    SCENE_Y_RANGE,
    SCENE_Z_GRAB_THRESHOLD,
    OVERLAY_FPS_COLOR,
    OVERLAY_NO_HAND_COLOR,
    OVERLAY_FONT_SCALE,
)


# ── Types & constantes MediaPipe ──────────────────────────────────────────────

_mp_hands = mp.solutions.hands
_mp_draw  = mp.solutions.drawing_utils
_mp_style = mp.solutions.drawing_styles

# Indices des landmarks (cf. https://mediapipe.dev/solutions/hands)
WRIST       = 0
THUMB_TIP   = 4
INDEX_MCP   = 5
INDEX_TIP   = 8
MIDDLE_TIP  = 12
RING_TIP    = 16
PINKY_TIP   = 20

# Articulations intermédiaires (PIP = proximal interphalangeal)
INDEX_PIP  = 6
MIDDLE_PIP = 10
RING_PIP   = 14
PINKY_PIP  = 18


# ── Gestes reconnus ───────────────────────────────────────────────────────────

class Gesture(Enum):
    NONE    = auto()   # Aucune main ou geste indéterminé
    OPEN    = auto()   # Main ouverte — mode déplacement
    FIST    = auto()   # Poing fermé — mode "attraper"
    PINCH   = auto()   # Pince (pouce + index) — mode "sélectionner"
    POINT   = auto()   # Index pointé seul — mode "pointer"


# ── Structure de données retournée à chaque frame ─────────────────────────────

@dataclass
class HandState:
    """Données de la main pour une frame, prêtes à être consommées par la scène."""
    detected: bool = False

    # Coordonnées 3D normalisées vers l'espace scène
    scene_x: float = 0.0
    scene_y: float = 0.0
    # Z estimé : proxy de profondeur basé sur l'écartement wrist–middle_tip
    # ⚠ Ce n'est PAS une profondeur métrique. Valeur relative, utilisée
    #   uniquement pour le seuil de "pince". Cf. MediaPipe Hands docs.
    depth_proxy: float = 0.0

    gesture: Gesture = Gesture.NONE
    fps: float = 0.0

    # Frame annotée pour l'affichage OpenCV (peut être None)
    annotated_frame: Optional[object] = field(default=None, repr=False)


# ── Filtre de lissage EMA (Exponential Moving Average) ────────────────────────

class EMAFilter:
    """
    Filtre exponentiel sur N dimensions.
    Atténue le bruit de détection sans introduire trop d'inertie.
    alpha = 0.20 est un bon compromis pour 30 fps.
    """

    def __init__(self, alpha: float = SMOOTH_ALPHA, dims: int = 2):
        self._alpha = alpha
        self._state = [0.0] * dims
        self._initialised = False

    def update(self, *values: float) -> list[float]:
        if not self._initialised:
            self._state = list(values)
            self._initialised = True
            return self._state[:]
        self._state = [
            self._alpha * v + (1 - self._alpha) * s
            for v, s in zip(values, self._state)
        ]
        return self._state[:]

    def reset(self):
        self._initialised = False


# ── Fonctions de normalisation ─────────────────────────────────────────────────

def normalize_coords(
    nx: float,
    ny: float,
    x_range: tuple = SCENE_X_RANGE,
    y_range: tuple = SCENE_Y_RANGE,
) -> tuple[float, float]:
    """
    Convertit les coordonnées normalisées MediaPipe [0,1]
    vers les unités de la scène 3D Ursina.

    nx, ny : coordonnées brutes MediaPipe (0 = haut-gauche, 1 = bas-droite)
    Retourne (scene_x, scene_y) dans les plages définies dans config.py

    Note : l'axe Y est inversé (MediaPipe y=0 en haut, Ursina y positif en haut).
    """
    x_min, x_max = x_range
    y_min, y_max = y_range
    # flip horizontal pour effet miroir naturel
    scene_x = x_min + (1.0 - nx) * (x_max - x_min)
    # flip vertical
    scene_y = y_min + (1.0 - ny) * (y_max - y_min)
    return scene_x, scene_y


def _compute_depth_proxy(landmarks) -> float:
    """
    Estime un proxy de profondeur à partir de l'écart
    wrist ↔ middle_tip sur l'axe X normalisé.
    Valeur haute → main proche caméra / main grande dans le champ.
    Valeur basse → main loin / petite.
    """
    w  = landmarks[WRIST]
    mt = landmarks[MIDDLE_TIP]
    return abs(w.x - mt.x) + abs(w.y - mt.y)


# ── Reconnaissance de gestes ──────────────────────────────────────────────────

def _classify_gesture(landmarks) -> Gesture:
    """
    Classe le geste à partir des positions relatives des landmarks.
    Logique simple, entièrement défendable devant un jury :
    - un doigt est "replié" si son TIP est plus bas (y plus grand) que son PIP.
    """
    tips = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]
    pips = [INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP]

    fingers_up = [
        landmarks[tip].y < landmarks[pip].y
        for tip, pip in zip(tips, pips)
    ]
    # Pouce : compare TIP à MCP sur l'axe X (main droite en miroir)
    thumb_up = landmarks[THUMB_TIP].x < landmarks[INDEX_MCP].x

    n_up = sum(fingers_up)

    if n_up == 0:
        return Gesture.FIST

    if n_up == 4 and thumb_up:
        return Gesture.OPEN

    # Pince : pouce et index proches, autres doigts repliés
    dx = abs(landmarks[THUMB_TIP].x - landmarks[INDEX_TIP].x)
    dy = abs(landmarks[THUMB_TIP].y - landmarks[INDEX_TIP].y)
    if dx < SCENE_Z_GRAB_THRESHOLD and dy < SCENE_Z_GRAB_THRESHOLD and n_up <= 1:
        return Gesture.PINCH

    # Index pointé seul
    if fingers_up[0] and not any(fingers_up[1:]):
        return Gesture.POINT

    return Gesture.NONE


# ── Thread de capture caméra ──────────────────────────────────────────────────

class HandTracker:
    """
    Encapsule toute la logique de Computer Vision dans un thread dédié.

    Usage :
        tracker = HandTracker()
        tracker.start()
        ...
        state: HandState = tracker.get_state()
        ...
        tracker.stop()
    """

    def __init__(self):
        # File thread-safe : taille 1 → on ne traite que la frame la plus récente
        self._queue: queue.Queue[HandState] = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ema = EMAFilter(alpha=SMOOTH_ALPHA, dims=2)
        self._last_state = HandState()

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Lance le thread de capture en arrière-plan."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="HandTrackerThread",
            daemon=True,   # S'arrête automatiquement si le process principal quitte
        )
        self._thread.start()

    def stop(self) -> None:
        """Arrête proprement le thread et libère la caméra."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def get_state(self) -> HandState:
        """
        Retourne l'état le plus récent disponible.
        Non-bloquant : si aucune nouvelle frame, renvoie le dernier état connu.
        """
        try:
            self._last_state = self._queue.get_nowait()
        except queue.Empty:
            pass
        return self._last_state

    # ── Boucle interne (thread) ───────────────────────────────────────────────

    def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(CAMERA_INDEX)

        if not cap.isOpened():
            raise RuntimeError(
                f"❌ Impossible d'ouvrir la webcam (index {CAMERA_INDEX}). "
                "Vérifiez qu'elle est branchée et non utilisée par une autre application."
            )

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS,          FRAME_TARGET_FPS)

        hands_model = _mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MP_MAX_HANDS,
            min_detection_confidence=MP_DETECTION_CONFIDENCE,
            min_tracking_confidence=MP_TRACKING_CONFIDENCE,
        )

        prev_time = time.perf_counter()

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    # Frame corrompue → on continue sans planter
                    continue

                # Calcul FPS
                now = time.perf_counter()
                fps = 1.0 / max(now - prev_time, 1e-9)
                prev_time = now

                # MediaPipe attend du RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False          # Optimisation mémoire
                results = hands_model.process(rgb)
                rgb.flags.writeable = True

                state = HandState(fps=fps)

                if results.multi_hand_landmarks:
                    lm = results.multi_hand_landmarks[0]

                    # Lissage EMA sur (x, y)
                    raw_x = lm.landmark[INDEX_TIP].x
                    raw_y = lm.landmark[INDEX_TIP].y
                    sx, sy = self._ema.update(raw_x, raw_y)

                    state.detected = True
                    state.scene_x, state.scene_y = normalize_coords(sx, sy)
                    state.depth_proxy = _compute_depth_proxy(lm.landmark)
                    state.gesture    = _classify_gesture(lm.landmark)

                    # Dessin des landmarks sur le frame BGR original
                    _mp_draw.draw_landmarks(
                        frame,
                        lm,
                        _mp_hands.HAND_CONNECTIONS,
                        _mp_style.get_default_hand_landmarks_style(),
                        _mp_style.get_default_hand_connection_style(),
                    )
                else:
                    self._ema.reset()

                # Overlay texte
                self._draw_overlay(frame, state)
                state.annotated_frame = frame

                # Mise à jour non-bloquante de la queue
                if self._queue.full():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass
                self._queue.put_nowait(state)

                # Affichage OpenCV
                cv2.imshow("CV3D — Webcam (Esc pour quitter)", frame)
                if cv2.waitKey(1) & 0xFF == 27:   # Touche Échap
                    self._stop_event.set()

        finally:
            hands_model.close()
            cap.release()
            cv2.destroyAllWindows()

    @staticmethod
    def _draw_overlay(frame, state: HandState) -> None:
        """Affiche les informations de debug sur le frame OpenCV."""
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = OVERLAY_FONT_SCALE
        thick = 2

        # FPS (coin haut gauche)
        cv2.putText(
            frame, f"FPS: {state.fps:.0f}",
            (10, 30), font, scale, OVERLAY_FPS_COLOR, thick,
        )

        if state.detected:
            # Geste actuel
            gesture_label = state.gesture.name
            cv2.putText(
                frame, f"Geste : {gesture_label}",
                (10, 60), font, scale, (255, 255, 255), thick,
            )
            # Coordonnées scène
            cv2.putText(
                frame, f"X:{state.scene_x:+.2f}  Y:{state.scene_y:+.2f}",
                (10, 90), font, scale * 0.85, (200, 200, 200), 1,
            )
        else:
            cv2.putText(
                frame, "Aucune main détectée",
                (10, 60), font, scale, OVERLAY_NO_HAND_COLOR, thick,
            )

        # Barre de statut (bas du frame)
        cv2.rectangle(frame, (0, h - 30), (w, h), (20, 20, 20), -1)
        cv2.putText(
            frame, "Esc = quitter  |  Poing = attraper  |  Pince = sélectionner",
            (10, h - 10), font, 0.42, (160, 160, 160), 1,
        )
