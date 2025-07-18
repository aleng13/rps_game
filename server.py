# Your existing imports
import cv2
import mediapipe as mp
import random
import time
import threading
import json

# --- Imports for the web server ---
from flask import Flask, render_template, Response
from flask_cors import CORS

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Global variables to share data with the web UI ---
lock = threading.Lock()
output_frame = None
# --- EDIT: Added score back to game_data ---
game_data = {
    "player_score": 0,
    "computer_score": 0,
    "player_choice": "NONE",
    "computer_choice": "NONE",
    "result": "",
    "game_state": "waiting" # 'waiting', 'countdown', 'result'
}

# --- YOUR EXISTING GAME LOGIC, WRAPPED IN A FUNCTION ---
def run_game():
    global output_frame, game_data, lock

    # Your existing setup code
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7
    )

    def get_gesture(hand_landmarks):
        tip_ids = [8, 12, 16, 20]
        pip_ids = [6, 10, 14, 18]
        fingers = []
        for tip, pip in zip(tip_ids, pip_ids):
            fingers.append(1 if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[pip].y else 0)
        
        if sum(fingers) == 0: return "ROCK"
        if sum(fingers) == 4: return "PAPER"
        if fingers[0] == 1 and fingers[1] == 1 and sum(fingers) == 2: return "SCISSORS"
        return None

    cap = cv2.VideoCapture(0)
    start_time = 0
    
    # Your main game loop
    while cap.isOpened():
        with lock:
            current_game_state = game_data["game_state"]

        success, frame = cap.read()
        if not success:
            continue
        
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)
        
        if current_game_state == "waiting":
            cv2.putText(frame, "Click PLAY in browser", (100, 200), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        elif current_game_state == "countdown":
            if start_time == 0:
                start_time = time.time()

            elapsed = time.time() - start_time
            count = 3 - int(elapsed)
            
            if count > 0:
                cv2.putText(frame, str(count), (300, 200), 
                            cv2.FONT_HERSHEY_SIMPLEX, 5, (0, 0, 255), 5)
            else:
                player_choice = None
                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]
                    player_choice = get_gesture(hand_landmarks)
                
                if player_choice is None:
                    player_choice = "NONE"

                computer_choice = random.choice(["ROCK", "PAPER", "SCISSORS"])
                
                # --- EDIT: Re-added score logic ---
                result = ""
                if player_choice == "NONE":
                    result = "NO GESTURE!"
                elif player_choice == computer_choice:
                    result = "TIE!"
                elif (player_choice == "ROCK" and computer_choice == "SCISSORS") or \
                     (player_choice == "PAPER" and computer_choice == "ROCK") or \
                     (player_choice == "SCISSORS" and computer_choice == "PAPER"):
                    result = "YOU WIN!"
                    with lock:
                        game_data["player_score"] += 1
                else:
                    result = "COMPUTER WINS!"
                    with lock:
                        game_data["computer_score"] += 1
                
                with lock:
                    game_data["game_state"] = "result"
                    game_data["player_choice"] = player_choice
                    game_data["computer_choice"] = computer_choice
                    game_data["result"] = result
                start_time = 0

        elif current_game_state == "result":
            with lock:
                cv2.putText(frame, f"You: {game_data['player_choice']}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Computer: {game_data['computer_choice']}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.putText(frame, game_data['result'], (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                cv2.putText(frame, "Click PLAY to go again", (100, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        with lock:
            _, buffer = cv2.imencode('.jpg', frame)
            output_frame = buffer.tobytes()

# --- Functions to stream data to the web UI ---
def generate_video():
    global output_frame, lock
    while True:
        with lock:
            if output_frame is None:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + output_frame + b'\r\n')

def generate_data():
    global game_data, lock
    while True:
        time.sleep(0.1)
        with lock:
            yield f"data: {json.dumps(game_data)}\n\n"

# --- Web Server Endpoints (URLs) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_video(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/game_data')
def game_data_feed():
    return Response(generate_data(), mimetype='text/event-stream')

@app.route('/start_game', methods=['POST'])
def start_game():
    global game_data, lock
    with lock:
        if game_data["game_state"] in ["waiting", "result"]:
            game_data["game_state"] = "countdown"
            game_data["player_choice"] = "..."
            game_data["computer_choice"] = "..."
            game_data["result"] = ""
    return {"status": "ok"}

# --- Main execution block ---
if __name__ == '__main__':
    game_thread = threading.Thread(target=run_game)
    game_thread.daemon = True
    game_thread.start()
    
    app.run(host='0.0.0.0', port=5000)
