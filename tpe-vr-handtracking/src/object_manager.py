# ============================================================
#  object_manager.py — Gestion du chargement et de la persistance
#
#  Responsabilités :
#    1. Ouvrir un sélecteur de fichier natif Windows/macOS/Linux
#    2. Charger le modèle .obj (ou autre) dans Ursina
#    3. Sauvegarder le chemin du dernier modèle (JSON)
#    4. Recharger automatiquement ce modèle au démarrage
# ============================================================

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from ursina import Entity, Vec3, color, destroy


# ── Sélecteur de fichier (thread séparé pour ne pas bloquer Ursina) ───────────

def _open_file_dialog(callback: Callable[[Optional[str]], None]) -> None:
    """
    Ouvre le sélecteur de fichier natif dans un thread dédié.
    Appelle callback(path) avec le chemin sélectionné, ou callback(None) si annulé.
    Thread séparé obligatoire : tkinter bloque si appelé depuis le thread Panda3D.
    """
    def _run():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()          # Cacher la fenêtre principale tk
            root.attributes('-topmost', True)  # Dialog au premier plan

            path = filedialog.askopenfilename(
                title="Sélectionner un modèle 3D",
                filetypes=[
                    ("Modèles 3D", "*.obj *.glb *.gltf *.egg *.bam"),
                    ("OBJ", "*.obj"),
                    ("Tous les fichiers", "*.*"),
                ],
            )
            root.destroy()
            callback(path if path else None)
        except Exception as e:
            print(f"[ObjectManager] Erreur sélecteur de fichier : {e}")
            callback(None)

    t = threading.Thread(target=_run, daemon=True, name="FileDialogThread")
    t.start()


# ── Persistance JSON ──────────────────────────────────────────────────────────

def _load_saved_path(save_file: str) -> Optional[str]:
    """Lit le chemin du dernier modèle chargé depuis le fichier JSON."""
    try:
        p = Path(save_file)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            path = data.get("last_model_path", "")
            if path and Path(path).exists():
                return path
    except Exception:
        pass
    return None


def _save_path(save_file: str, model_path: str) -> None:
    """Sauvegarde le chemin du modèle dans le fichier JSON."""
    try:
        p = Path(save_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"last_model_path": model_path}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[ObjectManager] Impossible de sauvegarder : {e}")


# ── Classe principale ─────────────────────────────────────────────────────────

class ObjectManager:
    """
    Gère le modèle 3D central de la scène.

    - Charge un modèle depuis un fichier (OBJ, GLB, EGG…)
    - Crée l'entité Ursina correspondante
    - Sauvegarde le chemin pour la prochaine session
    - Fournit open_dialog() pour que l'utilisateur change de modèle
    """

    def __init__(self, save_file: str):
        self._save_file = save_file
        self._entity: Optional[Entity] = None
        self._model_path: Optional[str] = None
        self._on_loaded_cb: Optional[Callable] = None
        self._dialog_open = False

    # ── API publique ──────────────────────────────────────────────────────────

    def set_on_loaded(self, callback: Callable) -> None:
        """Callback appelé quand un nouveau modèle est chargé."""
        self._on_loaded_cb = callback

    def load_saved(self) -> bool:
        """
        Charge le dernier modèle utilisé s'il existe encore sur le disque.
        Retourne True si un modèle a été chargé.
        """
        path = _load_saved_path(self._save_file)
        if path:
            return self._load_model(path)
        return False

    def open_dialog(self) -> None:
        """Ouvre le sélecteur de fichier. Non-bloquant."""
        if self._dialog_open:
            return
        self._dialog_open = True
        _open_file_dialog(self._on_file_selected)

    @property
    def entity(self) -> Optional[Entity]:
        return self._entity

    @property
    def model_path(self) -> Optional[str]:
        return self._model_path

    def destroy_entity(self) -> None:
        """Détruit l'entité Ursina actuelle sans perdre le chemin."""
        if self._entity:
            destroy(self._entity)
            self._entity = None

    # ── Interne ───────────────────────────────────────────────────────────────

    def _on_file_selected(self, path: Optional[str]) -> None:
        self._dialog_open = False
        if path:
            self._load_model(path)

    def _load_model(self, path: str) -> bool:
        """
        Charge le modèle dans Ursina.
        Ursina accepte un chemin absolu comme modèle.
        """
        # Détruire l'ancien modèle s'il existe
        self.destroy_entity()

        try:
            self._entity = Entity(
                model=path,
                position=Vec3(0, 0, 0),
                scale=1.5,
                color=color.white,
                texture="white_cube",
            )
            self._entity._base_scale = 1.5
            self._entity._original_position = Vec3(0, 0, 0)
            self._entity._original_rotation = Vec3(0, 0, 0)
            self._entity._original_scale = 1.5
            self._model_path = path
            _save_path(self._save_file, path)
            print(f"[ObjectManager] Modèle chargé : {Path(path).name}")

            if self._on_loaded_cb:
                self._on_loaded_cb(self._entity)
            return True

        except Exception as e:
            print(f"[ObjectManager] Erreur de chargement ({path}) : {e}")
            # Fallback : sphère si le fichier ne peut pas être chargé
            self._entity = Entity(
                model="sphere",
                position=Vec3(0, 0, 0),
                scale=1.5,
                color=color.orange,
            )
            self._entity._base_scale = 1.5
            self._entity._original_position = Vec3(0, 0, 0)
            self._entity._original_rotation = Vec3(0, 0, 0)
            self._entity._original_scale = 1.5
            return False
