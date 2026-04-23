import os
import cv2
import dlib
import math
import json
import statistics
import argparse
from PIL import Image
import imageio.v2 as imageio
import numpy as np
import csv
from collections import deque
import tensorflow as tf
import sys

# Robust import of constants
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
data_collection_dir = os.path.join(project_root, 'data_collection')
sys.path.insert(0, data_collection_dir)
from constants import TOTAL_FRAMES, VALID_WORD_THRESHOLD, NOT_TALKING_THRESHOLD, PAST_BUFFER_SIZE, LIP_WIDTH, LIP_HEIGHT

label_dict = {6: 'hello', 5: 'dog', 10: 'my', 12: 'you', 9: 'lips', 3: 'cat', 11: 'read', 0: 'a', 4: 'demo', 7: 'here', 8: 'is', 1: 'bye', 2: 'can'}

# Define the input shape
input_shape = (TOTAL_FRAMES, 80, 112, 3)

# Define the model architecture (same as predict_live.py)
model = tf.keras.Sequential([
    tf.keras.layers.Conv3D(16, (3, 3, 3), activation='relu', input_shape=input_shape),
    tf.keras.layers.MaxPooling3D((2, 2, 2)),
    tf.keras.layers.Conv3D(64, (3, 3, 3), activation='relu'),
    tf.keras.layers.MaxPooling3D((2, 2, 2)),
    tf.keras.layers.Flatten(),
    tf.keras.layers.Dense(128, activation='relu'),
    tf.keras.layers.Dropout(0.5),
    tf.keras.layers.Dense(64, activation='relu'),
    tf.keras.layers.Dropout(0.5),
    tf.keras.layers.Dense(len(label_dict), activation='softmax')
])

# Robust paths for weights
model_dir = os.path.join(project_root, 'model')
model_weights_path = os.path.join(model_dir, 'model_weights.h5')
face_weights_path = os.path.join(model_dir, 'face_weights.dat')

model.load_weights(model_weights_path, by_name=True)

# Load the detector and predictor
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(face_weights_path)

def main():
    parser = argparse.ArgumentParser(description='Lip reading inference from video file.')
    default_video = os.path.join(project_root, 'demo_examples', 'read_my_lips.mov')
    parser.add_argument('--video', type=str, default=r"C:\Users\DELL\OneDrive\Pictures\Camera Roll 1\WIN_20260210_18_44_54_Pro.mp4", help='Path to video file')
    args = parser.parse_args()

    video_path = args.video
    if not os.path.exists(video_path):
        print(f"Error: Video file {video_path} not found.")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    curr_word_frames = []
    not_talking_counter = 0
    past_word_frames = deque(maxlen=PAST_BUFFER_SIZE)
    predicted_word_label = None
    draw_prediction = False
    spoken_already = []
    count = 0

    # Prepare video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_path = os.path.join(project_root, 'demo', 'output_inference.mp4')
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
    if not out.isOpened():
        print("Warning: VideoWriter could not be opened. Video output will not be saved.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_count = 0

    print(f"Starting inference on {video_path}...")
    print(f"Output will be saved to: {out_path}")
    print("Press 'q' in the window to quit (if GUI is available).")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convert image into grayscale
        gray = cv2.cvtColor(src=frame, code=cv2.COLOR_BGR2GRAY)
        faces = detector(gray)
        
        for face in faces:
            # Landmarks and lip distance logic (copied from predict_live.py)
            landmarks = predictor(image=gray, box=face)
            mouth_top = (landmarks.part(51).x, landmarks.part(51).y)
            mouth_bottom = (landmarks.part(57).x, landmarks.part(57).y)
            lip_distance = math.hypot(mouth_bottom[0] - mouth_top[0], mouth_bottom[1] - mouth_top[1])

            lip_left = landmarks.part(48).x
            lip_right = landmarks.part(54).x
            lip_top = landmarks.part(50).y
            lip_bottom = landmarks.part(58).y

            width_diff = LIP_WIDTH - (lip_right - lip_left)
            height_diff = LIP_HEIGHT - (lip_bottom - lip_top)
            pad_left = max(0, min(width_diff // 2, lip_left))
            pad_right = max(0, min(width_diff - pad_left, frame.shape[1] - lip_right))
            pad_top = max(0, min(height_diff // 2, lip_top))
            pad_bottom = max(0, min(height_diff - pad_top, frame.shape[0] - lip_bottom))

            lip_frame = frame[lip_top - pad_top:lip_bottom + pad_bottom, lip_left - pad_left:lip_right + pad_right]
            lip_frame = cv2.resize(lip_frame, (LIP_WIDTH, LIP_HEIGHT))

            # Preprocessing (LAB CLAHE, GaussianBlur, bilateralFilter, etc. from predict_live.py)
            lip_frame_lab = cv2.cvtColor(lip_frame, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lip_frame_lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(3,3))
            l_channel_eq = clahe.apply(l_channel)
            lip_frame_eq = cv2.merge((l_channel_eq, a_channel, b_channel))
            lip_frame_eq = cv2.cvtColor(lip_frame_eq, cv2.COLOR_LAB2BGR)
            lip_frame_eq = cv2.GaussianBlur(lip_frame_eq, (7, 7), 0)
            lip_frame_eq = cv2.bilateralFilter(lip_frame_eq, 5, 75, 75)
            kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
            lip_frame_eq = cv2.filter2D(lip_frame_eq, -1, kernel)
            lip_frame_eq = cv2.GaussianBlur(lip_frame_eq, (5, 5), 0)
            lip_frame = lip_frame_eq

            # Visualization
            for n in range(48, 61):
                x = landmarks.part(n).x
                y = landmarks.part(n).y
                cv2.circle(img=frame, center=(x, y), radius=3, color=(0, 255, 0), thickness=-1)

            if lip_distance > 45: # person is talking
                curr_word_frames += [lip_frame.tolist()]
                not_talking_counter = 0
                draw_prediction = False
            else:
                not_talking_counter += 1
                if not_talking_counter >= NOT_TALKING_THRESHOLD and len(curr_word_frames) + PAST_BUFFER_SIZE == TOTAL_FRAMES: 
                    curr_word_frames = list(past_word_frames) + curr_word_frames
                    curr_data = np.array([curr_word_frames[:input_shape[0]]])
                    
                    prediction = model.predict(curr_data, verbose=0)
                    predicted_class_index = np.argmax(prediction)
                    
                    while label_dict[predicted_class_index] in spoken_already:
                        prediction[0][predicted_class_index] = 0
                        predicted_class_index = np.argmax(prediction)
                    
                    predicted_word_label = label_dict[predicted_class_index]
                    spoken_already.append(predicted_word_label)
                    print("Predicted:", predicted_word_label)
                    draw_prediction = True
                    count = 0
                    curr_word_frames = []
                    not_talking_counter = 0
                elif not_talking_counter < NOT_TALKING_THRESHOLD and len(curr_word_frames) + PAST_BUFFER_SIZE < TOTAL_FRAMES and len(curr_word_frames) > VALID_WORD_THRESHOLD:
                    curr_word_frames += [lip_frame.tolist()]
                    not_talking_counter = 0
                elif len(curr_word_frames) < VALID_WORD_THRESHOLD or (not_talking_counter >= NOT_TALKING_THRESHOLD and len(curr_word_frames) + PAST_BUFFER_SIZE > TOTAL_FRAMES):
                    curr_word_frames = []

                past_word_frames.append(lip_frame.tolist())

        if draw_prediction and count < 30: # Show for 30 frames
            count += 1
            cv2.putText(frame, predicted_word_label, (50 ,100), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 0), 2)

        # Save frame to output video
        if out.isOpened():
            out.write(frame)

        frame_count += 1
        if frame_count % 10 == 0:
            print(f"Processing frame {frame_count}/{total_frames}...")

    cap.release()
    out.release()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    print(f"Inference finished. Result saved to: {out_path}")

if __name__ == "__main__":
    main()
