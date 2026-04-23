import os
import sys
import dlib
import tensorflow as tf
import cv2
import numpy as np

print("Python version:", sys.version)
print("TensorFlow version:", tf.__version__)
print("OpenCV version:", cv2.__version__)
print("Dlib version:", dlib.__version__)

try:
    detector = dlib.get_frontal_face_detector()
    print("Dlib detector loaded successfully.")
except Exception as e:
    print("Error loading Dlib detector:", e)

try:
    # Test model architecture creation
    input_shape = (22, 80, 112, 3)
    model = tf.keras.Sequential([
        tf.keras.layers.Conv3D(16, (3, 3, 3), activation='relu', input_shape=input_shape),
        tf.keras.layers.MaxPooling3D((2, 2, 2)),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(13, activation='softmax')
    ])
    print("TensorFlow model created successfully.")
except Exception as e:
    print("Error creating TensorFlow model:", e)

print("Environment check complete.")
