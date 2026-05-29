# ============================================================
#  tests/test_tracking.py — Tests unitaires réels
#
#  Couvre les fonctions pures du module hand_tracking.py :
#    - normalize_coords()     (mapping de coordonnées)
#    - EMAFilter              (filtre de lissage)
#    - _classify_gesture()    (reconnaissance de gestes)
#
#  NE teste PAS la webcam, MediaPipe ou Ursina
#  (ces libs nécessitent du matériel physique).
#  Les tests de la logique pure sont suffisants pour la CI.
# ============================================================

import pytest
from unittest.mock import MagicMock

from src.hand_tracking import (
    normalize_coords,
    EMAFilter,
    _classify_gesture,
    Gesture,
    SCENE_X_RANGE,
    SCENE_Y_RANGE,
)


# ── normalize_coords ──────────────────────────────────────────────────────────

class TestNormalizeCoords:

    def test_centre_maps_to_centre(self):
        """Le centre de la frame (0.5, 0.5) doit mapper au centre de la scène."""
        x, y = normalize_coords(0.5, 0.5)
        assert abs(x) < 0.01
        assert abs(y) < 0.01

    def test_left_edge_maps_to_right_scene(self):
        """nx=0 (gauche frame) → droite scène (effet miroir naturel)."""
        x, _ = normalize_coords(0.0, 0.5)
        assert x == pytest.approx(SCENE_X_RANGE[1])

    def test_right_edge_maps_to_left_scene(self):
        """nx=1 (droite frame) → gauche scène."""
        x, _ = normalize_coords(1.0, 0.5)
        assert x == pytest.approx(SCENE_X_RANGE[0])

    def test_top_frame_maps_to_top_scene(self):
        """ny=0 (haut frame) → haut scène."""
        _, y = normalize_coords(0.5, 0.0)
        assert y == pytest.approx(SCENE_Y_RANGE[1])

    def test_bottom_frame_maps_to_bottom_scene(self):
        """ny=1 (bas frame) → bas scène."""
        _, y = normalize_coords(0.5, 1.0)
        assert y == pytest.approx(SCENE_Y_RANGE[0])

    def test_output_in_bounds(self):
        """Les sorties doivent toujours rester dans les plages config."""
        for nx, ny in [(0, 0), (1, 1), (0.3, 0.7), (0.99, 0.01)]:
            x, y = normalize_coords(nx, ny)
            assert SCENE_X_RANGE[0] <= x <= SCENE_X_RANGE[1], f"x={x} hors plage pour nx={nx}"
            assert SCENE_Y_RANGE[0] <= y <= SCENE_Y_RANGE[1], f"y={y} hors plage pour ny={ny}"


# ── EMAFilter ─────────────────────────────────────────────────────────────────

class TestEMAFilter:

    def test_first_update_is_exact(self):
        """La première valeur est retournée telle quelle (initialisation)."""
        f = EMAFilter(alpha=0.5, dims=2)
        result = f.update(3.0, 7.0)
        assert result == pytest.approx([3.0, 7.0])

    def test_converges_toward_new_value(self):
        """Après plusieurs frames stables, la sortie doit converger vers l'entrée."""
        f = EMAFilter(alpha=0.5, dims=1)
        for _ in range(20):
            r = f.update(10.0)
        assert r[0] == pytest.approx(10.0, abs=0.01)

    def test_smoothing_reduces_jump(self):
        """Un saut brutal est atténué (pas de téléportation)."""
        f = EMAFilter(alpha=0.2, dims=1)
        f.update(0.0)
        result = f.update(10.0)
        # alpha=0.2 → sortie = 0.2*10 + 0.8*0 = 2.0
        assert result[0] == pytest.approx(2.0)

    def test_reset_reinitialises(self):
        """Après reset, la prochaine valeur est acceptée comme initiale."""
        f = EMAFilter(alpha=0.2, dims=1)
        f.update(5.0)
        f.reset()
        result = f.update(8.0)
        assert result[0] == pytest.approx(8.0)


# ── _classify_gesture ─────────────────────────────────────────────────────────

def _make_landmarks(positions: dict) -> list:
    """
    Crée une liste de landmarks factices.
    positions : dict {index: (x, y, z)}
    Les indices non fournis ont (0.5, 0.5, 0.0) par défaut.
    """
    class FakeLM:
        def __init__(self, x, y, z=0.0):
            self.x, self.y, self.z = x, y, z

    # 21 landmarks
    lms = [FakeLM(0.5, 0.5) for _ in range(21)]
    for idx, (x, y, *z) in positions.items():
        lms[idx] = FakeLM(x, y, z[0] if z else 0.0)
    return lms


class TestClassifyGesture:

    def test_fist_when_all_fingers_down(self):
        """Tous les TIP en dessous de leur PIP → poing."""
        lms = _make_landmarks({
            # TIPs (8,12,16,20) ont y > PIPs (6,10,14,18)
            8: (0.5, 0.8), 6: (0.5, 0.5),   # index replié
            12: (0.5, 0.8), 10: (0.5, 0.5),
            16: (0.5, 0.8), 14: (0.5, 0.5),
            20: (0.5, 0.8), 18: (0.5, 0.5),
            4: (0.4, 0.5),  5: (0.5, 0.5),  # pouce replié
        })
        assert _classify_gesture(lms) == Gesture.FIST

    def test_point_when_only_index_up(self):
        """Seul l'index pointé vers le haut → Gesture.POINT."""
        lms = _make_landmarks({
            8: (0.5, 0.2), 6: (0.5, 0.5),   # index levé
            12: (0.5, 0.8), 10: (0.5, 0.5), # autres repliés
            16: (0.5, 0.8), 14: (0.5, 0.5),
            20: (0.5, 0.8), 18: (0.5, 0.5),
        })
        assert _classify_gesture(lms) == Gesture.POINT

    def test_pinch_when_thumb_and_index_close(self):
        """Pouce et index très proches + autres doigts repliés → Pince."""
        lms = _make_landmarks({
            4:  (0.50, 0.50),  # THUMB_TIP
            8:  (0.54, 0.54),  # INDEX_TIP — proche du pouce
            5:  (0.45, 0.45),  # INDEX_MCP — pour la condition pouce
            6:  (0.50, 0.40),  # INDEX_PIP — index replié (tip.y > pip.y)
            12: (0.5, 0.8), 10: (0.5, 0.5),
            16: (0.5, 0.8), 14: (0.5, 0.5),
            20: (0.5, 0.8), 18: (0.5, 0.5),
        })
        assert _classify_gesture(lms) == Gesture.PINCH
