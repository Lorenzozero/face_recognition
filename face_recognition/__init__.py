"""
face_recognition-ng
Fork of ageitgey/face_recognition — InsightFace backend, same API.

Original project: https://github.com/ageitgey/face_recognition
Fork by: https://github.com/Lorenzozero
"""

from .backends.insightface_backend import (
    load_image_file,
    face_locations,
    face_encodings,
    compare_faces,
    face_distance,
    face_landmarks,
)

__version__ = "2.0.0"
__author__ = "Lorenzozero (fork)"
__original_author__ = "Adam Geitgey"
