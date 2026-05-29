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
#  Les deux boucles sont INDÉPENDANTES.
#  HandTracker pousse les états dans une queue thread-safe.
#  La game loop Ursina (update()) consomme cette queue.
# ============================================================

import sys
from ursina import Ursina, color, window

from src.config import WINDOW_TITLE, WINDOW_FULLSCREEN, BACKGROUND_COLOR
from src.hand_tracking import HandTracker
from src.vr_scene import Scene3D


def main() -> None:
    # ── 1. Initialiser Ursina (DOIT être fait avant tout Entity) ─────────────
    app = Ursina(
        title=WINDOW_TITLE,
        fullscreen=WINDOW_FULLSCREEN,
        borderless=False,
        development_mode=False,
    )
    window.color = color.rgba(*BACKGROUND_COLOR)
    window.exit_button.visible = False  # Pas de bouton de sortie Ursina par défaut

    # ── 2. Créer la scène 3D ──────────────────────────────────────────────────
    scene = Scene3D()

    # ── 3. Lancer le tracker dans son thread dédié ────────────────────────────
    tracker = HandTracker()
    tracker.start()

    # ── 4. Définir la game loop Ursina ────────────────────────────────────────
    #  update() est appelée automatiquement à chaque frame par Ursina.
    #  Elle tire le dernier état disponible depuis la queue.
    def update():
        state = tracker.get_state()
        scene.update(state)

    # Injecter update() dans le module global (requis par Ursina)
    import builtins
    builtins.update = update

    # ── 5. Lancer la boucle principale ────────────────────────────────────────
    try:
        app.run()
    finally:
        # Arrêt propre : libère la caméra et détruit le thread
        tracker.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
