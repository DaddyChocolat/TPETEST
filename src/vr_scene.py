# ============================================================
#  vr_scene.py — Module de rendu 3D interactif (Ursina Engine)
#
#  Responsabilités :
#    1. Initialiser la scène, l'éclairage et la caméra
#    2. Créer les objets interactifs
#    3. Consommer le HandState à chaque frame (update)
#    4. Réagir aux gestes (déplacement, attraper, sélectionner)
#    5. Feedback visuel clair sur chaque interaction
# ============================================================

from __future__ import annotations

from ursina import (
    Ursina, Entity, camera, color,
    DirectionalLight, AmbientLight, PointLight,
    Vec3, lerp, destroy, held_keys, window,
    Text, invoke,
)
from ursina.prefabs.first_person_controller import FirstPersonController

from src.config import (
    WINDOW_TITLE,
    WINDOW_FULLSCREEN,
    BACKGROUND_COLOR,
    SCENE_X_RANGE,
    SCENE_Y_RANGE,
)
from src.hand_tracking import HandState, Gesture


# ── Couleurs de la scène ──────────────────────────────────────────────────────

COL_IDLE      = color.rgb(80, 140, 220)    # Bleu — objet au repos
COL_HOVER     = color.rgb(120, 220, 180)   # Cyan — sous la main
COL_GRABBED   = color.rgb(255, 180, 60)    # Orange — attrapé
COL_SELECTED  = color.rgb(220, 80, 160)    # Magenta — sélectionné
COL_GRID      = color.rgb(40, 44, 60)      # Gris bleuté — sol


# ── Classe principale de la scène ─────────────────────────────────────────────

class Scene3D:
    """
    Encapsule toute la logique de la scène Ursina.
    Créé APRÈS l'app Ursina (Ursina() doit être appelé en premier).
    """

    def __init__(self):
        self._setup_environment()
        self._setup_objects()
        self._setup_hud()
        self._cursor_entity = self._create_cursor()

        # État interne
        self._grabbed_object: Entity | None = None
        self._grab_offset = Vec3(0, 0, 0)
        self._prev_gesture = Gesture.NONE

    # ── Construction de la scène ──────────────────────────────────────────────

    def _setup_environment(self) -> None:
        """Sol en grille + éclairages."""
        # Sol
        Entity(
            model="plane",
            scale=(20, 1, 20),
            position=(0, -4, 0),
            color=COL_GRID,
            texture="white_cube",
            texture_scale=(20, 20),
        )

        # Lumière directionnelle principale (lumière du "soleil")
        sun = DirectionalLight()
        sun.look_at(Vec3(1, -2, -1))

        # Lumière ambiante douce (évite les zones complètement noires)
        AmbientLight(color=color.rgb(60, 65, 90))

        # Lumière d'accentuation colorée (scène sci-fi)
        accent = PointLight(color=color.rgb(50, 100, 255))
        accent.position = Vec3(-8, 4, -2)

        # Caméra fixe orientée vers la scène
        camera.position = (0, 1, -14)
        camera.rotation_x = 5

    def _setup_objects(self) -> None:
        """Objets 3D interactifs disposés dans la scène."""
        self._objects: list[Entity] = []

        configs = [
            # (modèle,   position,         scale, couleur)
            ("cube",     Vec3(-4,  0,  0),  1.4,  COL_IDLE),
            ("sphere",   Vec3( 0,  0,  0),  1.2,  COL_IDLE),
            ("cube",     Vec3( 4,  0,  0),  1.0,  COL_IDLE),
            # Petits objets décoratifs en arrière-plan
            ("sphere",   Vec3(-2,  2,  3),  0.6,  color.rgb(80, 200, 100)),
            ("cube",     Vec3( 2,  2,  3),  0.7,  color.rgb(200, 80, 80)),
        ]

        for model, pos, sc, col in configs:
            e = Entity(
                model=model,
                position=pos,
                scale=sc,
                color=col,
                texture="white_cube",
            )
            e._base_color = col
            e._base_scale = sc
            self._objects.append(e)

        # Objet principal controlé par la main (le plus grand au centre)
        self._main_obj: Entity = self._objects[1]

    def _setup_hud(self) -> None:
        """HUD minimaliste : état du geste, coordonnées."""
        self._hud_gesture = Text(
            text="En attente de main...",
            position=(-0.85, 0.46),
            scale=1.1,
            color=color.white,
        )
        self._hud_coords = Text(
            text="",
            position=(-0.85, 0.40),
            scale=0.85,
            color=color.rgb(180, 180, 180),
        )

    @staticmethod
    def _create_cursor() -> Entity:
        """Petite sphère translucide qui suit la position de la main."""
        return Entity(
            model="sphere",
            scale=0.25,
            color=color.rgba(255, 255, 255, 120),
            unlit=True,    # Non affecté par l'éclairage → toujours visible
        )

    # ── Mise à jour par frame ─────────────────────────────────────────────────

    def update(self, state: HandState) -> None:
        """
        Appelé depuis la game loop Ursina (fonction update() globale).
        Consomme le HandState fourni par HandTracker.
        """
        self._update_hud(state)

        if not state.detected:
            self._cursor_entity.visible = False
            self._release_object()
            return

        # Positionner le curseur dans la scène
        self._cursor_entity.visible = True
        target_pos = Vec3(state.scene_x, state.scene_y, 0)
        # Interpolation douce vers la cible (complète le lissage EMA)
        self._cursor_entity.position = lerp(
            self._cursor_entity.position, target_pos, 0.35
        )

        # Réagir aux gestes
        self._handle_gesture(state.gesture, target_pos)
        self._prev_gesture = state.gesture

    # ── Logique de gestes ─────────────────────────────────────────────────────

    def _handle_gesture(self, gesture: Gesture, hand_pos: Vec3) -> None:
        match gesture:
            case Gesture.OPEN:
                self._on_open_hand(hand_pos)
            case Gesture.FIST:
                self._on_fist(hand_pos)
            case Gesture.PINCH:
                self._on_pinch(hand_pos)
            case Gesture.POINT:
                self._on_point(hand_pos)
            case _:
                self._highlight_closest(hand_pos)

    def _on_open_hand(self, hand_pos: Vec3) -> None:
        """Main ouverte : simple surbrillance de l'objet le plus proche."""
        self._release_object()
        self._highlight_closest(hand_pos)

    def _on_fist(self, hand_pos: Vec3) -> None:
        """Poing : attraper l'objet le plus proche et le déplacer."""
        if self._grabbed_object is None:
            # Cherche un objet à portée
            closest = self._find_closest(hand_pos, radius=2.5)
            if closest:
                self._grabbed_object = closest
                self._grab_offset = closest.position - hand_pos
                self._flash_color(closest, COL_GRABBED)
        else:
            # Déplace l'objet attrapé
            self._grabbed_object.position = lerp(
                self._grabbed_object.position,
                hand_pos + self._grab_offset,
                0.4,
            )

    def _on_pinch(self, hand_pos: Vec3) -> None:
        """Pince : sélectionner/désélectionner, changer la couleur."""
        if self._prev_gesture != Gesture.PINCH:
            closest = self._find_closest(hand_pos, radius=3.0)
            if closest:
                if closest.color == COL_SELECTED:
                    self._flash_color(closest, closest._base_color)
                else:
                    self._flash_color(closest, COL_SELECTED)

    def _on_point(self, hand_pos: Vec3) -> None:
        """Index pointé : animation de pulse sur l'objet visé."""
        self._release_object()
        closest = self._find_closest(hand_pos, radius=4.0)
        if closest:
            self._pulse_scale(closest)

    # ── Helpers visuels ───────────────────────────────────────────────────────

    def _highlight_closest(self, hand_pos: Vec3) -> None:
        """Mettre en surbrillance l'objet le plus proche, reset les autres."""
        closest = self._find_closest(hand_pos, radius=2.5)
        for obj in self._objects:
            if obj is not self._grabbed_object:
                obj.color = COL_HOVER if obj is closest else obj._base_color

    def _find_closest(self, hand_pos: Vec3, radius: float) -> Entity | None:
        best, best_dist = None, radius
        for obj in self._objects:
            d = (obj.position - hand_pos).length()
            if d < best_dist:
                best_dist = d
                best = obj
        return best

    def _release_object(self) -> None:
        if self._grabbed_object:
            self._grabbed_object.color = self._grabbed_object._base_color
            self._grabbed_object = None

    def _flash_color(self, obj: Entity, col) -> None:
        obj.color = col

    def _pulse_scale(self, obj: Entity) -> None:
        """Animation de 'pulse' sur l'échelle de l'objet."""
        original = obj._base_scale
        obj.scale = original * 1.25
        invoke(setattr, obj, "scale", original, delay=0.15)

    # ── HUD ───────────────────────────────────────────────────────────────────

    def _update_hud(self, state: HandState) -> None:
        if state.detected:
            self._hud_gesture.text = f"Geste : {state.gesture.name}"
            self._hud_coords.text = (
                f"X:{state.scene_x:+.2f}  Y:{state.scene_y:+.2f}"
            )
        else:
            self._hud_gesture.text = "En attente de main..."
            self._hud_coords.text = ""
