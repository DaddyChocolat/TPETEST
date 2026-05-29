# ============================================================
#  main.py — Point d'entrée de l'application
#
#  Orchestration :
#    ┌──────────────┐       queue        ┌──────────────┐
#    │  HandTracker │ ─── HandState ──► │   Scene3D    │
#    │  (Thread CV) │                   │  (Ursina 3D) │
#    └──────────────┘                   └──────────────┘
#         ↑                                    ↑
#      Thread daemon                    Thread principal
#      (caméra + MediaPipe)            (game loop Ursina)
#
#  Touches clavier :
#    O        → Ouvrir un modèle 3D (sélecteur de fichier)
#    Échap    → Quitter (depuis la fenêtre OpenCV)
# ============================================================

import sys
import __main__
from ursina import Ursina, color, window, application, held_keys

from src.config import WINDOW_TITLE, WINDOW_FULLSCREEN, BACKGROUND_COLOR
from src.hand_tracking import HandTracker
from src.vr_scene import Scene3D


def main() -> None:
    # ── 1. Initialiser Ursina ─────────────────────────────────────────────────
    app = Ursina(
        title=WINDOW_TITLE,
        fullscreen=WINDOW_FULLSCREEN,
        borderless=False,
        development_mode=False,
    )
    window.color = color.rgba(*BACKGROUND_COLOR)
    window.exit_button.visible = False

    # ── 2. Créer la scène ─────────────────────────────────────────────────────
    scene = Scene3D()

    # ── 3. Lancer le tracker CV ───────────────────────────────────────────────
    tracker = HandTracker()
    tracker.start()

    # ── 4. Game loop ──────────────────────────────────────────────────────────
    def update():
        # Quitter si Esc pressé dans OpenCV
        if tracker._stop_event.is_set():
            application.quit()
            return
        state = tracker.get_state()
        scene.update(state)

    def input(key):
        # Touche O → ouvrir le sélecteur de fichier
        if key == "o":
            scene.open_model_dialog()

    # Injection dans __main__ (mécanisme natif Ursina)
    __main__.update = update
    __main__.input = input

    # ── 5. Lancer ────────────────────────────────────────────────────────────
    try:
        app.run()
    finally:
        tracker.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
