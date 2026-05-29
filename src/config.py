# ============================================================
#  config.py — Paramètres centralisés du projet
#  Modifiez ici pour adapter le comportement sans toucher au code.
# ============================================================

# --- Webcam ---
CAMERA_INDEX: int = 0          # 0 = webcam par défaut, 1 = externe
FRAME_WIDTH: int = 640         # Résolution de capture (largeur)
FRAME_HEIGHT: int = 480        # Résolution de capture (hauteur)
FRAME_TARGET_FPS: int = 30     # FPS cible de la capture

# --- MediaPipe Hands ---
MP_MAX_HANDS: int = 1                   # Nombre de mains détectées simultanément
MP_DETECTION_CONFIDENCE: float = 0.7   # Seuil de détection initiale [0.0 – 1.0]
MP_TRACKING_CONFIDENCE: float = 0.6    # Seuil de suivi continu [0.0 – 1.0]

# --- Lissage des coordonnées (filtre EMA) ---
# alpha proche de 1.0 → réactif mais tremblant
# alpha proche de 0.1 → très lisse mais avec inertie
SMOOTH_ALPHA: float = 0.20

# --- Mapping main → scène 3D ---
# L'espace 3D Ursina est centré sur (0,0,0).
# Ces valeurs définissent les limites de la zone de jeu.
SCENE_X_RANGE: tuple = (-6.0, 6.0)    # Déplacement horizontal
SCENE_Y_RANGE: tuple = (-4.0, 4.0)    # Déplacement vertical
SCENE_Z_GRAB_THRESHOLD: float = 0.08  # Distance de "pince" pour attraper

# --- Rendu Ursina ---
WINDOW_TITLE: str = "CV3D — Interaction gestuelle 3D"
WINDOW_FULLSCREEN: bool = False
BACKGROUND_COLOR: tuple = (0.05, 0.05, 0.10, 1)  # Bleu nuit très sombre

# --- Overlay OpenCV ---
OVERLAY_FPS_COLOR: tuple = (50, 255, 120)       # Vert
OVERLAY_LANDMARK_COLOR: tuple = (255, 255, 255)  # Blanc
OVERLAY_NO_HAND_COLOR: tuple = (50, 50, 255)    # Rouge doux
OVERLAY_FONT_SCALE: float = 0.65
