#!/usr/bin/env python3
"""
face_recognition.py - Face recognition backend for JARVIS.
Stores face embeddings and identifies known faces (RED vs Unknown).
"""

import logging
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    from paths import VAULT_PATH, LOGS_PATH
except ImportError:
    from backend.paths import VAULT_PATH, LOGS_PATH

logger = logging.getLogger(__name__)

# Storage paths
FACE_PROFILES_PATH = VAULT_PATH / "raw_sources" / "face_profiles.json"
FACE_EMBEDDINGS_DIR = VAULT_PATH / "raw_sources" / "face_embeddings"

# Recognition thresholds
SIMILARITY_THRESHOLD = 0.85  # Cosine similarity threshold for match
CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.85
CONFIDENCE_LOW = 0.70


@dataclass
class FaceProfile:
    """Profile for a known person."""
    person_id: str  # e.g., "RED", "Tyler", "Unknown_001"
    name: str  # Display name
    registered_at: str
    sample_count: int  # Number of face samples stored
    last_seen: Optional[str] = None
    confidence_history: List[float] = None
    
    def __post_init__(self):
        if self.confidence_history is None:
            self.confidence_history = []


@dataclass
class FaceEmbedding:
    """Single face embedding capture."""
    embedding: List[float]  # 468-dimensional vector from Face Mesh
    timestamp: str
    source: str  # "registration" or "detection"
    confidence: float
    
    def to_dict(self):
        return {
            "embedding": self.embedding,
            "timestamp": self.timestamp,
            "source": self.source,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


class FaceRecognitionSystem:
    """Manages face profiles and performs identification."""
    
    def __init__(self):
        self.profiles: Dict[str, FaceProfile] = {}
        self.embeddings: Dict[str, List[FaceEmbedding]] = {}  # person_id -> list of embeddings
        self._ensure_storage()
        self._load_profiles()
    
    def _ensure_storage(self):
        """Ensure storage directories exist."""
        FACE_EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
        VAULT_PATH.mkdir(parents=True, exist_ok=True)
    
    def _load_profiles(self):
        """Load existing face profiles from storage."""
        if not FACE_PROFILES_PATH.exists():
            logger.info("[FaceRecognition] No existing profiles found")
            return
        
        try:
            with open(FACE_PROFILES_PATH, "r") as f:
                data = json.load(f)
            
            for person_id, profile_data in data.get("profiles", {}).items():
                self.profiles[person_id] = FaceProfile(**profile_data)
                
                # Load embeddings for this person
                embedding_file = FACE_EMBEDDINGS_DIR / f"{person_id}.json"
                if embedding_file.exists():
                    with open(embedding_file, "r") as f:
                        emb_data = json.load(f)
                    self.embeddings[person_id] = [
                        FaceEmbedding.from_dict(e) for e in emb_data.get("embeddings", [])
                    ]
            
            logger.info(f"[FaceRecognition] Loaded {len(self.profiles)} profiles")
            
        except Exception as e:
            logger.error(f"[FaceRecognition] Error loading profiles: {e}")
    
    def _save_profiles(self):
        """Save profiles to storage."""
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "profiles": {
                    pid: asdict(profile) for pid, profile in self.profiles.items()
                }
            }
            
            FACE_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(FACE_PROFILES_PATH, "w") as f:
                json.dump(data, f, indent=2)
            
            # Save embeddings separately
            for person_id, embeddings in self.embeddings.items():
                embedding_file = FACE_EMBEDDINGS_DIR / f"{person_id}.json"
                emb_data = {
                    "person_id": person_id,
                    "embedding_count": len(embeddings),
                    "embeddings": [e.to_dict() for e in embeddings]
                }
                with open(embedding_file, "w") as f:
                    json.dump(emb_data, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"[FaceRecognition] Error saving profiles: {e}")
            return False
    
    def _compute_embedding_hash(self, embedding: List[float]) -> str:
        """Compute hash of embedding for deduplication."""
        emb_str = ",".join([f"{x:.4f}" for x in embedding])
        return hashlib.md5(emb_str.encode()).hexdigest()[:12]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    def _average_embedding(self, embeddings: List[List[float]]) -> List[float]:
        """Compute average of multiple embeddings."""
        if not embeddings:
            return []
        
        dim = len(embeddings[0])
        avg = [0.0] * dim
        
        for emb in embeddings:
            for i in range(dim):
                avg[i] += emb[i]
        
        return [x / len(embeddings) for x in avg]
    
    def register_face(self, person_id: str, name: str, 
                      landmarks: List[dict], source: str = "manual") -> dict:
        """
        Register a new face profile.
        
        Args:
            person_id: Unique ID (e.g., "RED", "Tyler")
            name: Display name
            landmarks: List of MediaPipe Face Mesh landmarks (468 points)
            source: Registration source ("manual" or "auto")
        
        Returns:
            dict with success status and message
        """
        try:
            # Convert landmarks to embedding (468 x 3 = 1404 dimensions)
            embedding = []
            for lm in landmarks:
                embedding.extend([lm.get("x", 0), lm.get("y", 0), lm.get("z", 0)])
            
            # Check if embedding is valid
            if len(embedding) != 468 * 3:
                return {
                    "success": False,
                    "message": f"Invalid landmark data: expected 468 points, got {len(landmarks)}"
                }
            
            # Create or update profile
            now = datetime.now().isoformat()
            
            if person_id in self.profiles:
                profile = self.profiles[person_id]
                profile.sample_count += 1
                profile.name = name  # Update name if changed
            else:
                profile = FaceProfile(
                    person_id=person_id,
                    name=name,
                    registered_at=now,
                    sample_count=1
                )
                self.profiles[person_id] = profile
                self.embeddings[person_id] = []
            
            # Store embedding
            face_emb = FaceEmbedding(
                embedding=embedding,
                timestamp=now,
                source=source,
                confidence=1.0  # Registration is high confidence
            )
            
            if person_id not in self.embeddings:
                self.embeddings[person_id] = []
            self.embeddings[person_id].append(face_emb)
            
            # Keep only last 50 embeddings per person (prevent bloat)
            if len(self.embeddings[person_id]) > 50:
                self.embeddings[person_id] = self.embeddings[person_id][-50:]
            
            # Save to disk
            self._save_profiles()
            
            logger.info(f"[FaceRecognition] Registered face for {name} ({person_id})")
            
            return {
                "success": True,
                "person_id": person_id,
                "name": name,
                "sample_count": profile.sample_count,
                "message": f"Successfully registered {name}. {profile.sample_count} samples stored."
            }
            
        except Exception as e:
            logger.error(f"[FaceRecognition] Registration error: {e}")
            return {
                "success": False,
                "message": f"Registration failed: {e}"
            }
    
    def identify_face(self, landmarks: List[dict]) -> dict:
        """
        Identify a face from landmarks.
        
        Args:
            landmarks: MediaPipe Face Mesh landmarks (468 points)
        
        Returns:
            dict with identified person, confidence, and match info
        """
        try:
            # Convert landmarks to embedding
            embedding = []
            for lm in landmarks:
                embedding.extend([lm.get("x", 0), lm.get("y", 0), lm.get("z", 0)])
            
            if len(embedding) != 468 * 3:
                return {
                    "identified": False,
                    "person_id": None,
                    "name": "Unknown",
                    "confidence": 0.0,
                    "message": "Invalid face data"
                }
            
            # Compare against all known profiles
            best_match = None
            best_confidence = 0.0
            
            for person_id, embeddings in self.embeddings.items():
                if not embeddings:
                    continue
                
                # Compare against average of stored embeddings
                stored_embs = [e.embedding for e in embeddings]
                avg_emb = self._average_embedding(stored_embs)
                
                similarity = self._cosine_similarity(embedding, avg_emb)
                
                if similarity > best_confidence:
                    best_confidence = similarity
                    best_match = person_id
            
            # Determine result based on confidence
            if best_confidence >= SIMILARITY_THRESHOLD:
                profile = self.profiles.get(best_match)
                if profile and isinstance(profile, FaceProfile):
                    profile.last_seen = datetime.now().isoformat()
                    profile.confidence_history.append(best_confidence)
                    # Keep only last 100 confidence scores
                    profile.confidence_history = profile.confidence_history[-100:]
                    
                    # Save updated last_seen
                    self._save_profiles()
                    
                    confidence_level = "high" if best_confidence >= CONFIDENCE_HIGH else "medium"
                    
                    return {
                        "identified": True,
                        "person_id": best_match,
                        "name": profile.name,
                        "confidence": best_confidence,
                        "confidence_level": confidence_level,
                        "message": f"Recognized {profile.name} with {best_confidence:.1%} confidence"
                    }
            
            # No match - return unknown
            return {
                "identified": False,
                "person_id": None,
                "name": "Unknown",
                "confidence": best_confidence,
                "message": f"Face not recognized (best match: {best_confidence:.1%})"
            }
            
        except Exception as e:
            logger.error(f"[FaceRecognition] Identification error: {e}")
            return {
                "identified": False,
                "person_id": None,
                "name": "Error",
                "confidence": 0.0,
                "message": f"Identification failed: {e}"
            }
    
    def list_profiles(self) -> List[dict]:
        """List all registered face profiles."""
        return [
            {
                "person_id": pid,
                "name": profile.name,
                "sample_count": profile.sample_count,
                "registered_at": profile.registered_at,
                "last_seen": profile.last_seen,
                "avg_confidence": sum(profile.confidence_history) / len(profile.confidence_history) if profile.confidence_history else None,
            }
            for pid, profile in self.profiles.items()
        ]
    
    def delete_profile(self, person_id: str) -> bool:
        """Delete a face profile."""
        if person_id not in self.profiles:
            return False
        
        del self.profiles[person_id]
        if person_id in self.embeddings:
            del self.embeddings[person_id]
        
        # Delete embedding file
        embedding_file = FACE_EMBEDDINGS_DIR / f"{person_id}.json"
        if embedding_file.exists():
            embedding_file.unlink()
        
        self._save_profiles()
        logger.info(f"[FaceRecognition] Deleted profile {person_id}")
        return True


# Global instance
_face_recognition_system: Optional[FaceRecognitionSystem] = None


def get_face_recognition() -> FaceRecognitionSystem:
    """Get or create the global face recognition system."""
    global _face_recognition_system
    if _face_recognition_system is None:
        _face_recognition_system = FaceRecognitionSystem()
    return _face_recognition_system


# Convenience functions
def register_face(person_id: str, name: str, landmarks: List[dict]) -> dict:
    """Register a face (convenience function)."""
    system = get_face_recognition()
    return system.register_face(person_id, name, landmarks)


def identify_face(landmarks: List[dict]) -> dict:
    """Identify a face (convenience function)."""
    system = get_face_recognition()
    return system.identify_face(landmarks)


def list_face_profiles() -> List[dict]:
    """List all face profiles (convenience function)."""
    system = get_face_recognition()
    return system.list_profiles()


def delete_face_profile(person_id: str) -> bool:
    """Delete a face profile (convenience function)."""
    system = get_face_recognition()
    return system.delete_profile(person_id)


if __name__ == "__main__":
    print("Face Recognition module loaded.")
    print(f"Profiles stored at: {FACE_PROFILES_PATH}")
    print(f"Embeddings stored at: {FACE_EMBEDDINGS_DIR}")
    
    # List existing profiles
    profiles = list_face_profiles()
    print(f"\nRegistered profiles: {len(profiles)}")
    for p in profiles:
        print(f"  - {p['name']} ({p['person_id']}): {p['sample_count']} samples")
