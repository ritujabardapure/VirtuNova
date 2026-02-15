# gesture.py (Dual-Hand Virtual Mouse)
import cv2
import mediapipe as mp
import pyautogui
import time
import math

# -----------------------------
# Mediapipe setup
# -----------------------------
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands = mp_hands.Hands(max_num_hands=2,
                       min_detection_confidence=0.7,
                       min_tracking_confidence=0.7)

# -----------------------------
# Screen info
# -----------------------------
screen_w, screen_h = pyautogui.size()
pyautogui.FAILSAFE = False

# -----------------------------
# Helper functions
# -----------------------------
def distance(p1, p2):
    return math.hypot(p2[0]-p1[0], p2[1]-p1[1])

def fingers_up(lm_list):
    """Returns list of fingers up: [thumb, index, middle, ring, pinky]"""
    fingers = []
    # Thumb: basic heuristic (works for many cases)
    try:
        fingers.append(lm_list[4][0] < lm_list[3][0])
    except Exception:
        fingers.append(False)
    # Other fingers
    for tip_id, pip_id in [(8,6), (12,10), (16,14), (20,18)]:
        try:
            fingers.append(lm_list[tip_id][1] < lm_list[pip_id][1])
        except Exception:
            fingers.append(False)
    return fingers

# -----------------------------
# Main Virtual Mouse
# -----------------------------
def virtual_mouse():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FPS, 30)  # increase camera FPS for faster detection
    cv2.namedWindow("Virtual Mouse", cv2.WINDOW_NORMAL)

    last_left_click_time = 0
    last_right_click_time = 0
    click_cooldown = 0.3   # faster click cooldown
    pinch_state = False
    pinch_start_time = 0

    prev_x, prev_y = 0, 0
    smooth_factor = 0.5    # faster cursor movement
    cam_margin = 40

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        frame = cv2.flip(frame, 1)
        h, w, c = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb_frame)

        right_hand_lm = None
        left_hand_lm = None

        # Detect hands
        if result.multi_hand_landmarks and result.multi_handedness:
            for hand_landmarks, hand_info in zip(result.multi_hand_landmarks, result.multi_handedness):
                lm_list = [(int(lm.x * w), int(lm.y * h)) for lm in hand_landmarks.landmark]
                label = hand_info.classification[0].label

                if label == "Right":
                    right_hand_lm = lm_list
                else:
                    left_hand_lm = lm_list

                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        # -----------------------------
        # Cursor movement (prefer right hand, else left)
        # -----------------------------
        if right_hand_lm:
            x, y = right_hand_lm[8]
        elif left_hand_lm:
            x, y = left_hand_lm[8]
        else:
            x = y = None

        if x is not None and y is not None:
            # avoid division by zero and clamp margins
            usable_w = max(1, (w - 2 * cam_margin))
            usable_h = max(1, (h - 2 * cam_margin))
            rel_x = (x - cam_margin) / usable_w
            rel_y = (y - cam_margin) / usable_h
            rel_x = max(0.0, min(1.0, rel_x))
            rel_y = max(0.0, min(1.0, rel_y))

            screen_x = int(screen_w * rel_x)
            screen_y = int(screen_h * rel_y)
            screen_x = max(0, min(screen_w-1, screen_x))
            screen_y = max(0, min(screen_h-1, screen_y))
            screen_x = int(prev_x + (screen_x - prev_x) * smooth_factor)
            screen_y = int(prev_y + (screen_y - prev_y) * smooth_factor)
            prev_x, prev_y = screen_x, screen_y
            try:
                pyautogui.moveTo(screen_x, screen_y, duration=0.01)
            except Exception:
                pass



        # -----------------------------
        # Right hand -> left click
        # -----------------------------
        if right_hand_lm:
            thumb_index_dist = distance(right_hand_lm[4], right_hand_lm[8])
            if thumb_index_dist < 40:  # slightly higher threshold for faster detection
                if not pinch_state:
                    pinch_state = True
                    pinch_start_time = time.time()
            else:
                if pinch_state:
                    pinch_duration = time.time() - pinch_start_time
                    try:
                        if pinch_duration < 0.5:
                            pyautogui.click()
                            cv2.putText(frame, "Left Click!", (x+10, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                        else:
                            pyautogui.doubleClick()
                            cv2.putText(frame, "Double Click!", (x+10, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,200,0), 2)
                    except Exception:
                        pass
                    pinch_state = False

            # Scroll up/down with 3 fingers (index+middle+ring)
            fingers = fingers_up(right_hand_lm)
            if fingers[1] and fingers[2] and fingers[3]:
                try:
                    pyautogui.scroll(60)  # faster scrolling
                except Exception:
                    pass
                cv2.putText(frame, "Scroll Up", (x+10, y-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)
            elif not fingers[1] and not fingers[2] and not fingers[3]:
                try:
                    pyautogui.scroll(-60)  # faster scrolling
                except Exception:
                    pass
                cv2.putText(frame, "Scroll Down", (x+10, y-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)

        # -----------------------------
        # Left hand -> right click
        # -----------------------------
        if left_hand_lm and time.time() - last_right_click_time > click_cooldown:
            thumb_index_dist = distance(left_hand_lm[4], left_hand_lm[8])
            if thumb_index_dist < 40:  # faster detection
                try:
                    pyautogui.rightClick()
                    last_right_click_time = time.time()
                    lx, ly = left_hand_lm[8]
                    cv2.putText(frame, "Right Click!", (lx+10, ly-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                except Exception:
                    pass

        # Show feed
        cv2.imshow("Virtual Mouse", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


# -----------------------------
# Run standalone
# -----------------------------
if __name__ == "__main__":
    virtual_mouse()
