# CV3D — Interaction gestuelle 3D par Computer Vision

> **Contrôler un environnement 3D en temps réel, sans aucun contrôleur physique,  
> grâce à la seule webcam et à l'intelligence artificielle.**

[![CI Tests](https://github.com/DaddyChocolat/tpe-vr-handtracking/actions/workflows/python-app.yml/badge.svg)](https://github.com/DaddyChocolat/tpe-vr-handtracking/actions)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 1. Problématique scientifique (TPE)

> *Comment l'Intelligence Artificielle et la Vision par Ordinateur permettent-elles  
> de créer une interface naturelle de contrôle 3D en s'affranchissant des  
> contrôleurs physiques ?*

**Note terminologique :** Ce projet ne relève pas de la Réalité Virtuelle au sens strict  
(qui exige une immersion sensorielle, typiquement via un casque stéréoscopique).  
Il implémente une **interface gestuelle 3D** — catégorie plus précise et rigoureusement  
défendable devant un jury technique.

---

## 2. Description du système

Le système fonctionne comme une boucle interactive en temps réel à deux threads :

```
┌──────────────────────────────┐         queue          ┌────────────────────────┐
│   Thread CV (HandTracker)    │ ──── HandState ──────► │  Thread 3D (Ursina)    │
│                              │                        │                        │
│  Webcam → MediaPipe Hands   │                        │  Scène + Objets        │
│  → Landmarks (21 points)    │                        │  → Réaction au geste   │
│  → Filtre EMA               │                        │  → Feedback visuel     │
│  → Geste reconnu            │                        │                        │
└──────────────────────────────┘                        └────────────────────────┘
```

### Les 3 étapes clés

| Étape | Ce qui se passe | Technologie |
|-------|-----------------|-------------|
| **Perception** | Capture vidéo + détection des 21 landmarks de la main | OpenCV + MediaPipe |
| **Traduction** | Normalisation, lissage EMA, classification du geste | Python pur |
| **Rendu** | Mise à jour de la scène 3D selon l'état de la main | Ursina Engine |

---

## 3. Gestes reconnus

| Geste | Condition | Action dans la scène |
|-------|-----------|----------------------|
| ✋ **Main ouverte** | 4 doigts levés | Déplacement + surbrillance de l'objet |
| ✊ **Poing** | Tous doigts repliés | Attraper et déplacer l'objet |
| 🤏 **Pince** | Pouce + index proches | Sélectionner / désélectionner |
| ☝️ **Index pointé** | Seul l'index levé | Animation pulse sur l'objet |

---

## 4. Architecture modulaire

```
cv3d/
├── src/
│   ├── __init__.py
│   ├── config.py          ← Tous les paramètres (une seule source de vérité)
│   ├── hand_tracking.py   ← Thread CV : capture + MediaPipe + EMA + gestes
│   ├── vr_scene.py        ← Scène 3D Ursina + logique d'interaction
│   └── main.py            ← Orchestration des deux threads
├── tests/
│   └── test_tracking.py   ← Tests unitaires sur la logique pure
├── .github/workflows/
│   └── python-app.yml     ← CI automatique sur chaque push
├── .python-version        ← Version Python fixée (3.10.14)
└── requirements.txt       ← Dépendances épinglées
```

---

## 5. Dépendances (`requirements.txt`)

| Bibliothèque | Rôle | Pourquoi ce choix |
|---|---|---|
| `opencv-python 4.9` | Capture webcam + overlay d'info | Standard industriel de Computer Vision |
| `mediapipe 0.10.9` | Détection des 21 landmarks de la main | Modèle Google, CPU only, fonctionne hors-ligne |
| `ursina 5.3.0` | Moteur de rendu 3D | Python pur, basé sur Panda3D, idéal pour prototypage |
| `pytest 8.2` | Tests unitaires | Standard de facto Python |

> **⚠ Limite connue de MediaPipe :** L'axe Z fourni par `landmark.z` est une estimation  
> *relative* basée sur la taille du poignet — pas une profondeur métrique. Ce projet  
> utilise uniquement X et Y pour le déplacement, ce qui est scientifiquement honnête.

---

## 6. Installation et lancement

### Prérequis
- Python **3.10.x** (voir `.python-version`)
- Webcam intégrée ou externe
- Windows 10+, macOS 12+, ou Linux (Ubuntu 22.04+)

### Étapes

```bash
# 1. Cloner le dépôt
git clone https://github.com/DaddyChocolat/tpe-vr-handtracking.git
cd tpe-vr-handtracking

# 2. Créer un environnement virtuel
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer l'application
python -m src.main
```

> Deux fenêtres s'ouvrent simultanément :  
> - **Fenêtre OpenCV** — flux webcam avec overlay (FPS, geste, coordonnées)  
> - **Fenêtre Ursina** — scène 3D interactive  
> Appuyez sur **Échap** dans la fenêtre OpenCV pour quitter proprement.

---

## 7. Tests unitaires

```bash
# Lancer tous les tests
pytest -v

# Avec rapport de couverture
pytest --cov=src --cov-report=term-missing
```

Les tests couvrent la logique pure (normalisation, filtre EMA, classification des gestes)  
sans nécessiter de webcam ni d'affichage graphique.

---

## 8. Points forts scientifiques

- **Rigueur sur l'axe Z** : le projet reconnaît et documente la limite du Z MediaPipe  
  plutôt que de la masquer — ce qui démontre une vraie compréhension du système.
- **Architecture multithread** : séparation propre entre l'I/O caméra et le rendu 3D,  
  évitant les deadlocks et les frames sautées.
- **Filtre EMA** : algorithme de lissage défendable mathématiquement (`s_t = α·x_t + (1−α)·s_{t-1}`).
- **Reconnaissance de gestes** : 4 gestes distincts basés sur la géométrie relative  
  des landmarks — pas de machine learning supplémentaire.

---

## Licence

MIT — voir `LICENSE`
