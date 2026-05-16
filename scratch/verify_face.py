import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path("c:/Projects/Operator/backend")
sys.path.append(str(backend_path))

from face_recognition import get_face_recognition

def test_face_pipeline():
    print("=== Face Recognition Logic Verification ===")
    system = get_face_recognition()
    
    # 1. Create mock landmarks (468 points)
    mock_landmarks = []
    for i in range(468):
        mock_landmarks.append({"x": 0.5 + (i * 0.001), "y": 0.5 - (i * 0.001), "z": 0.1})
    
    print("\n[Step 1] Registering mock face 'TestUser'...")
    reg_result = system.register_face("TEST_USER", "Test User", mock_landmarks)
    print(f"Result: {reg_result['message']}")
    
    # 2. Check if files were created
    profiles_path = Path("e:/JarvisVault/raw_sources/face_profiles.json")
    emb_path = Path("e:/JarvisVault/raw_sources/face_embeddings/TEST_USER.json")
    
    print(f"\n[Step 2] Checking storage...")
    if profiles_path.exists():
        print(f"OK: face_profiles.json created.")
    else:
        print(f"FAIL: face_profiles.json missing at {profiles_path}")
        
    if emb_path.exists():
        print(f"OK: TEST_USER.json embedding created.")
    else:
        print(f"FAIL: Embedding file missing at {emb_path}")
        
    # 3. Identify face
    print("\n[Step 3] Identifying face with slightly jittered landmarks...")
    jittered_landmarks = []
    for i in range(468):
        jittered_landmarks.append({"x": 0.5001 + (i * 0.001), "y": 0.4999 - (i * 0.001), "z": 0.1})
        
    ident_result = system.identify_face(jittered_landmarks)
    print(f"Result: {ident_result['message']}")
    print(f"Identified: {ident_result['identified']}")
    print(f"Confidence: {ident_result['confidence']:.4f}")
    
    # 4. Clean up
    print("\n[Step 4] Cleaning up test data...")
    system.delete_profile("TEST_USER")
    print("Profile deleted.")

if __name__ == "__main__":
    test_face_pipeline()
