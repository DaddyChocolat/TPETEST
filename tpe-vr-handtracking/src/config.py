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
SMOOTH_ALPHA: float = 0.20

# --- Mapping main → scène 3D ---
SCENE_X_RANGE: tuple = (-6.0, 6.0)
SCENE_Y_RANGE: tuple = (-4.0, 4.0)
SCENE_Z_GRAB_THRESHOLD: float = 0.08

# --- Rendu Ursina ---
WINDOW_TITLE: str = "CV3D — Manipulation d'objets 3D par gestes"
WINDOW_FULLSCREEN: bool = False
BACKGROUND_COLOR: tuple = (0.05, 0.05, 0.10, 1)

# --- Overlay OpenCV ---
OVERLAY_FPS_COLOR: tuple = (50, 255, 120)
OVERLAY_LANDMARK_COLOR: tuple = (255, 255, 255)
OVERLAY_NO_HAND_COLOR: tuple = (50, 50, 255)
OVERLAY_FONT_SCALE: float = 0.65

# --- Interaction 3D ---
ROTATION_SPEED: float = 120.0      # degrés par unité de déplacement main
ZOOM_SPEED: float = 3.0            # unités de scale par unité de mouvement
ZOOM_MIN: float = 0.3              # scale minimum de l'objet
ZOOM_MAX: float = 5.0              # scale maximum de l'objet
GRAB_RADIUS: float = 3.0           # rayon de détection pour attraper
SECTION_COOLDOWN: float = 1.0      # secondes entre deux coupes
FRAGMENT_COUNT: int = 12           # nombre de fragments lors de l'explosion
FRAGMENT_LIFETIME: float = 3.0     # secondes avant disparition des fragments
REASSEMBLE_DELAY: float = 1.5      # secondes pour que les fragments reviennent
DOUBLE_FIST_WINDOW: float = 0.6    # secondes max entre deux poings pour déclencher explosion

# --- Persistance ---
SAVE_FILE: str = "data/last_model.json"   # chemin du fichier de sauvegarde
