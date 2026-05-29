# ============================================================
#  vr_scene.py — Scène 3D interactive (Ursina Engine)
#
#  Gestes → Actions :
#    OPEN   (main ouverte)  → Rotation de l'objet
#    FIST   (poing)         → Déplacer l'objet / Double poing → Exploser
#    PINCH  (pince)         → Zoom (mouvement vertical)
#    POINT  (index)         → Armer le plan de coupe → trancher
#
#  Séquence briser/réassembler :
#    Double FIST rapide → explosion en fragments
#    OPEN après explosion → réassemblage
# ============================================================

from __future__ import annotations

import random
import time
from typing import Optional

from ursina import (
    Entity, camera, color,
    DirectionalLight, AmbientLight, PointLight,
    Vec3, lerp, destroy, Text, invoke,
)

from src.config import (
    SCENE_X_RANGE,
    SCENE_Y_RANGE,
    ROTATION_SPEED,
    ZOOM_SPEED,
    ZOOM_MIN,
    ZOOM_MAX,
    GRAB_RADIUS,
    SECTION_COOLDOWN,
    FRAGMENT_COUNT,
    FRAGMENT_LIFETIME,
    REASSEMBLE_DELAY,
    DOUBLE_FIST_WINDOW,
    SAVE_FILE,
)
from src.hand_tracking import HandState, Gesture
from src.object_manager import ObjectManager


# ── Couleurs ──────────────────────────────────────────────────────────────────

COL_GRID       = color.rgb(30, 34, 50)
COL_CURSOR     = color.rgba(255, 255, 255, 100)
COL_SECTION    = color.rgba(255, 60, 60, 80)
COL_FRAGMENT   = color.rgb(210, 140, 60)
COL_HUD_MAIN   = color.white
COL_HUD_SUB    = color.rgb(160, 160, 180)
COL_HUD_WARN   = color.rgb(255, 200, 60)


# ── États de l'application ────────────────────────────────────────────────────

class AppState:
    IDLE        = "idle"         # Aucune main / attente
    ROTATING    = "rotating"     # Main ouverte : rotation
    GRABBING    = "grabbing"     # Poing : déplacement
    ZOOMING     = "zooming"      # Pince : zoom
    ARMING      = "arming"       # Index : plan de coupe visible
    SECTIONED   = "sectioned"    # Objet coupé en 2 moitiés
    EXPLODED    = "exploded"     # Objet éclaté en fragments
    REASSEMBLING = "reassembling" # Fragments qui reviennent


# ── Fragment physique simple ───────────────────────────────────────────────────

class Fragment:
    """
    Un morceau de l'objet brisé.
    Simule une physique basique (vélocité + gravité) via update().
    """

    def __init__(self, origin: Vec3, color_val):
        self.vel = Vec3(
            random.uniform(-4, 4),
            random.uniform(2, 7),
            random.uniform(-3, 3),
        )
        self.rot_vel = Vec3(
            random.uniform(-200, 200),
            random.uniform(-200, 200),
            random.uniform(-200, 200),
        )
        self.entity = Entity(
            model=random.choice(["cube", "sphere"]),
            position=origin + Vec3(
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
            ),
            scale=random.uniform(0.15, 0.45),
            color=color_val,
        )
        self.alive = True
        self._born = time.perf_counter()

    def update(self, dt: float) -> None:
        if not self.alive:
            return
        # Gravité
        self.vel.y -= 9.8 * dt
        self.entity.position += self.vel * dt
        self.entity.rotation += self.rot_vel * dt
        # Sol
        if self.entity.y < -5:
            self.vel.y *= -0.4
            self.vel.x *= 0.7
            self.vel.z *= 0.7
            self.entity.y = -5

    def destroy(self) -> None:
        if self.alive:
            destroy(self.entity)
            self.alive = False


# ── Moitié d'objet sectionné ──────────────────────────────────────────────────

class Half:
    """Représente une des deux moitiés après coupe."""

    def __init__(self, model_path: Optional[str], offset: Vec3,
                 base_pos: Vec3, base_scale: float):
        self.target_offset = offset
        self.entity = Entity(
            model=model_path or "cube",
            position=base_pos,
            scale=base_scale,
            color=color.rgb(200, 100, 50),
        )
        self._base_pos = base_pos

    def animate_split(self) -> None:
        """Déplace la moitié vers son offset cible."""
        invoke(
            setattr, self.entity, "position",
            self._base_pos + self.target_offset,
            delay=0.05,
        )

    def destroy(self) -> None:
        destroy(self.entity)


# ── Scène principale ──────────────────────────────────────────────────────────

class Scene3D:
    """
    Orchestre toute la scène Ursina.
    Instancier APRÈS Ursina().
    """

    def __init__(self):
        self._state = AppState.IDLE
        self._obj_manager = ObjectManager(save_file=SAVE_FILE)
        self._obj_manager.set_on_loaded(self._on_model_loaded)

        self._setup_environment()
        self._setup_hud()
        self._cursor = self._make_cursor()
        self._section_plane: Optional[Entity] = None

        # État rotation
        self._prev_hand_x: float = 0.0
        self._prev_hand_y: float = 0.0
        self._prev_gesture = Gesture.NONE

        # État zoom
        self._zoom_anchor_y: float = 0.0
        self._zoom_anchor_scale: float = 1.5

        # Détection double poing
        self._last_fist_time: float = 0.0
        self._fist_count: int = 0

        # Fragments et moitiés
        self._fragments: list[Fragment] = []
        self._halves: list[Half] = []
        self._section_cooldown_until: float = 0.0

        # Dernier dt pour la physique fragments
        self._last_frame_time: float = time.perf_counter()

        # Charger le dernier modèle sauvegardé
        loaded = self._obj_manager.load_saved()
        if not loaded:
            self._make_default_object()

        self._update_hud_mode()

    # ── Construction ──────────────────────────────────────────────────────────

    def _setup_environment(self) -> None:
        Entity(
            model="plane",
            scale=(30, 1, 30),
            position=(0, -5, 0),
            color=COL_GRID,
        )
        sun = DirectionalLight()
        sun.look_at(Vec3(1, -2, -1))
        AmbientLight(color=color.rgb(70, 75, 100))
        fill = PointLight(color=color.rgb(80, 120, 255))
        fill.position = Vec3(-8, 6, -4)
        camera.position = (0, 1, -14)
        camera.rotation_x = 5

    def _setup_hud(self) -> None:
        self._hud_mode = Text(
            text="",
            position=(-0.85, 0.47),
            scale=1.1,
            color=COL_HUD_MAIN,
        )
        self._hud_gesture = Text(
            text="Aucune main détectée",
            position=(-0.85, 0.41),
            scale=0.9,
            color=COL_HUD_SUB,
        )
        self._hud_hint = Text(
            text="[O] Ouvrir un modèle 3D",
            position=(-0.85, -0.46),
            scale=0.8,
            color=COL_HUD_WARN,
        )

    @staticmethod
    def _make_cursor() -> Entity:
        return Entity(
            model="sphere",
            scale=0.18,
            color=COL_CURSOR,
            unlit=True,
            visible=False,
        )

    def _make_default_object(self) -> None:
        """Sphère par défaut si aucun modèle n'est sauvegardé."""
        e = Entity(
            model="sphere",
            position=Vec3(0, 0, 0),
            scale=1.5,
            color=color.orange,
        )
        e._base_scale = 1.5
        e._original_position = Vec3(0, 0, 0)
        e._original_rotation = Vec3(0, 0, 0)
        e._original_scale = 1.5
        self._obj_manager._entity = e

    def _on_model_loaded(self, entity: Entity) -> None:
        """Appelé par ObjectManager quand un nouveau modèle est chargé."""
        # Nettoyer l'état courant
        self._clear_fragments()
        self._clear_halves()
        self._state = AppState.IDLE
        self._update_hud_mode()

    # ── Point d'entrée par frame ──────────────────────────────────────────────

    def update(self, state: HandState) -> None:
        """Appelé à chaque frame depuis main.py."""
        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now

        # Mise à jour physique des fragments
        self._update_fragments(dt)

        # Mise à jour HUD geste
        if state.detected:
            self._hud_gesture.text = f"Geste : {state.gesture.name}"
            self._cursor.visible = True
            target = Vec3(state.scene_x, state.scene_y, 0)
            self._cursor.position = lerp(self._cursor.position, target, 0.3)
        else:
            self._hud_gesture.text = "Aucune main détectée"
            self._cursor.visible = False

        # Dispatch geste
        if state.detected:
            self._dispatch(state, dt)

        self._prev_gesture = state.gesture
        self._prev_hand_x = state.scene_x
        self._prev_hand_y = state.scene_y

    def open_model_dialog(self) -> None:
        """Appelé depuis main.py quand l'utilisateur presse 'O'."""
        self._obj_manager.open_dialog()

    # ── Dispatch des gestes ───────────────────────────────────────────────────

    def _dispatch(self, state: HandState, dt: float) -> None:
        obj = self._obj_manager.entity

        # En état EXPLODED : OPEN reassemble
        if self._state == AppState.EXPLODED:
            if state.gesture == Gesture.OPEN:
                self._reassemble()
            return

        # En état REASSEMBLING : attendre
        if self._state == AppState.REASSEMBLING:
            return

        # En état SECTIONED : OPEN réunit, FIST rapide explose
        if self._state == AppState.SECTIONED:
            if state.gesture == Gesture.OPEN:
                self._reunite_halves()
            elif state.gesture == Gesture.FIST:
                self._trigger_explosion()
            return

        if obj is None:
            return

        match state.gesture:
            case Gesture.OPEN:
                self._handle_rotation(obj, state, dt)
            case Gesture.FIST:
                self._handle_fist(obj, state)
            case Gesture.PINCH:
                self._handle_zoom(obj, state)
            case Gesture.POINT:
                self._handle_section_arm(obj, state)
            case _:
                self._state = AppState.IDLE
                if self._section_plane:
                    destroy(self._section_plane)
                    self._section_plane = None

    # ── Rotation ──────────────────────────────────────────────────────────────

    def _handle_rotation(self, obj: Entity, state: HandState, dt: float) -> None:
        self._state = AppState.ROTATING
        # Masquer le plan de coupe
        if self._section_plane:
            destroy(self._section_plane)
            self._section_plane = None

        if self._prev_gesture == Gesture.OPEN:
            dx = state.scene_x - self._prev_hand_x
            dy = state.scene_y - self._prev_hand_y
            obj.rotation_y -= dx * ROTATION_SPEED
            obj.rotation_x += dy * ROTATION_SPEED

    # ── Déplacement / Double poing ────────────────────────────────────────────

    def _handle_fist(self, obj: Entity, state: HandState) -> None:
        now = time.perf_counter()

        # Détection double poing
        if self._prev_gesture != Gesture.FIST:
            # Nouveau poing
            if now - self._last_fist_time < DOUBLE_FIST_WINDOW:
                self._fist_count += 1
            else:
                self._fist_count = 1
            self._last_fist_time = now

            if self._fist_count >= 2:
                self._fist_count = 0
                self._trigger_explosion()
                return

        self._state = AppState.GRABBING
        target = Vec3(state.scene_x, state.scene_y, 0)
        obj.position = lerp(obj.position, target, 0.25)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def _handle_zoom(self, obj: Entity, state: HandState) -> None:
        if self._prev_gesture != Gesture.PINCH:
            # Mémoriser l'ancre au début du geste
            self._zoom_anchor_y = state.scene_y
            self._zoom_anchor_scale = obj.scale_y
            self._state = AppState.ZOOMING
            return

        self._state = AppState.ZOOMING
        delta = state.scene_y - self._zoom_anchor_y
        new_scale = self._zoom_anchor_scale + delta * ZOOM_SPEED
        new_scale = max(ZOOM_MIN, min(ZOOM_MAX, new_scale))
        obj.scale = new_scale

    # ── Section (plan de coupe) ───────────────────────────────────────────────

    def _handle_section_arm(self, obj: Entity, state: HandState) -> None:
        """Index pointé : affiche un plan de coupe horizontal. Maintenu 1s → coupe."""
        self._state = AppState.ARMING

        if time.perf_counter() < self._section_cooldown_until:
            return

        # Créer ou déplacer le plan de coupe
        cut_y = state.scene_y
        if self._section_plane is None:
            self._section_plane = Entity(
                model="quad",
                scale=(6, 0.05, 6),
                position=Vec3(obj.x, cut_y, obj.z),
                rotation_x=90,
                color=COL_SECTION,
                unlit=True,
            )
        else:
            self._section_plane.y = cut_y

        # Si l'index est maintenu stable (geste POINT depuis >0.8s) → couper
        if self._prev_gesture == Gesture.POINT:
            if not hasattr(self, "_point_start"):
                self._point_start = time.perf_counter()
            elif time.perf_counter() - self._point_start > 0.8:
                self._do_section(obj, cut_y)
                del self._point_start
        else:
            if hasattr(self, "_point_start"):
                del self._point_start

    def _do_section(self, obj: Entity, cut_y: float) -> None:
        """Coupe l'objet en deux moitiés."""
        if self._section_plane:
            destroy(self._section_plane)
            self._section_plane = None

        path = self._obj_manager.model_path
        base_pos = obj.position
        base_scale = obj.scale_y

        # Cacher l'objet principal
        obj.visible = False

        # Créer les deux moitiés
        top = Half(path, Vec3(0, 1.2, 0.3), base_pos, base_scale)
        bot = Half(path, Vec3(0, -1.2, -0.3), base_pos, base_scale)
        top.animate_split()
        bot.animate_split()
        self._halves = [top, bot]

        self._state = AppState.SECTIONED
        self._section_cooldown_until = time.perf_counter() + SECTION_COOLDOWN
        self._update_hud_mode()

    def _reunite_halves(self) -> None:
        """Réunit les deux moitiés."""
        for h in self._halves:
            h.destroy()
        self._halves.clear()

        obj = self._obj_manager.entity
        if obj:
            obj.visible = True

        self._state = AppState.IDLE
        self._update_hud_mode()

    # ── Explosion ────────────────────────────────────────────────────────────

    def _trigger_explosion(self) -> None:
        """Explose l'objet en fragments."""
        obj = self._obj_manager.entity
        if obj is None:
            return

        # Nettoyer les moitiés si elles existent
        self._clear_halves()

        origin = obj.position
        obj.visible = False

        col = color.rgb(
            random.randint(180, 255),
            random.randint(80, 160),
            random.randint(20, 80),
        )

        self._fragments = [
            Fragment(origin, col) for _ in range(FRAGMENT_COUNT)
        ]
        self._state = AppState.EXPLODED
        self._update_hud_mode()

        # Auto-destruction des fragments après FRAGMENT_LIFETIME secondes
        invoke(self._auto_destroy_fragments, delay=FRAGMENT_LIFETIME)

    def _auto_destroy_fragments(self) -> None:
        if self._state == AppState.EXPLODED:
            self._reassemble()

    def _update_fragments(self, dt: float) -> None:
        for frag in self._fragments:
            frag.update(dt)

    def _clear_fragments(self) -> None:
        for frag in self._fragments:
            frag.destroy()
        self._fragments.clear()

    def _reassemble(self) -> None:
        """Réassemble les fragments vers l'objet original."""
        self._state = AppState.REASSEMBLING
        self._update_hud_mode()

        obj = self._obj_manager.entity
        if obj is None:
            self._clear_fragments()
            self._state = AppState.IDLE
            return

        target = obj._original_position if hasattr(obj, "_original_position") else Vec3(0, 0, 0)

        # Déplacer les fragments vers le centre
        for frag in self._fragments:
            if frag.alive:
                frag.vel = Vec3(0, 0, 0)
                frag.rot_vel = Vec3(0, 0, 0)
                # Animer via invoke
                invoke(
                    setattr, frag.entity, "position",
                    target,
                    delay=REASSEMBLE_DELAY * random.uniform(0.5, 1.0),
                )

        # Après le délai, remettre l'objet
        invoke(self._finish_reassemble, delay=REASSEMBLE_DELAY + 0.3)

    def _finish_reassemble(self) -> None:
        self._clear_fragments()
        obj = self._obj_manager.entity
        if obj:
            obj.visible = True
            if hasattr(obj, "_original_position"):
                obj.position = obj._original_position
            if hasattr(obj, "_original_scale"):
                obj.scale = obj._original_scale
        self._state = AppState.IDLE
        self._update_hud_mode()

    # ── Nettoyage ─────────────────────────────────────────────────────────────

    def _clear_halves(self) -> None:
        for h in self._halves:
            h.destroy()
        self._halves.clear()

    # ── HUD ───────────────────────────────────────────────────────────────────

    def _update_hud_mode(self) -> None:
        labels = {
            AppState.IDLE:          "✋ En attente",
            AppState.ROTATING:      "↻  Rotation",
            AppState.GRABBING:      "✊ Déplacement",
            AppState.ZOOMING:       "🔍 Zoom",
            AppState.ARMING:        "✂  Coupe (maintenir)",
            AppState.SECTIONED:     "✂  Objet sectionné",
            AppState.EXPLODED:      "💥 Objet éclaté — ouvrir la main pour réassembler",
            AppState.REASSEMBLING:  "⟳  Réassemblage...",
        }
        self._hud_mode.text = labels.get(self._state, "")
