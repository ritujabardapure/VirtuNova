# gui.py
"""
Phase-2 Upgraded GUI for Virtual World (all Phase-2 features applied)
Single central button: "LAUNCH"
Click detection: Thumb + Index finger
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import math
from collections import deque

# Optional sound: winsound works on Windows. Fallback to no sound.
try:
    import winsound

    def play_click_sound():
        winsound.Beep(700, 70)  # frequency, duration ms
except Exception:
    def play_click_sound():
        pass

mpHands = mp.solutions.hands
hands = mpHands.Hands(max_num_hands=1,
                      min_detection_confidence=0.6,
                      min_tracking_confidence=0.6)
mpDraw = mp.solutions.drawing_utils

# --------- Utility functions ----------
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def lerp(a, b, t):
    return a + (b - a) * t

def color_lerp(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))

# --------- Visual effect helpers ----------
def draw_frosted_panel(img, x1, y1, x2, y2, radius=8, alpha=0.55):
    h, w = img.shape[:2]
    x1c, y1c = max(0, x1), max(0, y1)
    x2c, y2c = min(w, x2), min(h, y2)
    if x2c <= x1c or y2c <= y1c:
        return img
    region = img[y1c:y2c, x1c:x2c]
    if region.size == 0:
        return img
    blurred = cv2.GaussianBlur(region, (21, 21), 0)
    overlay = img.copy()
    overlay[y1c:y2c, x1c:x2c] = blurred
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 255, 255), -1)
    res = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
    return res

def draw_gradient_round_button(img, x1, y1, x2, y2, text, glow=0.0, scale=1.0):
    h, w = img.shape[:2]
    overlay = img.copy()
    x1c, y1c = int(max(0, x1)), int(max(0, y1))
    x2c, y2c = int(min(w - 1, x2)), int(min(h - 1, y2))
    if x2c <= x1c or y2c <= y1c:
        return img

    top, mid, bot = (15, 80, 150), (60, 140, 220), (120, 80, 180)
    height = y2c - y1c
    for i in range(y1c, y2c):
        t = (i - y1c) / max(1, height)
        if t < 0.5:
            c = color_lerp(top, mid, t * 2)
        else:
            c = color_lerp(mid, bot, (t - 0.5) * 2)
        cv2.line(overlay, (x1c, i), (x2c, i), c, 1)

    cv2.rectangle(overlay, (x1c, y1c), (x2c, y2c), (255, 255, 255), 1, cv2.LINE_AA)

    glow_amount = int(12 * glow)
    for i in range(glow_amount):
        cv2.rectangle(overlay, (x1c - i, y1c - i), (x2c + i, y2c + i), (120, 200, 255), 1, cv2.LINE_AA)
        overlay = cv2.addWeighted(overlay, 1.0, img, 0.0, 0)

    img = cv2.addWeighted(overlay, 0.85, img, 0.15, 0)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.9 * scale
    thickness = 2
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    cx, cy = (x1c + x2c) // 2, (y1c + y2c) // 2
    text_x = cx - text_size[0] // 2
    text_y = cy + text_size[1] // 2
    cv2.putText(img, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness + 1, cv2.LINE_AA)

    shine_h = int((y2c - y1c) * 0.25)
    shine = img.copy()
    cv2.rectangle(shine, (x1c + 5, y1c + 5), (x2c - 5, y1c + 5 + shine_h), (255, 255, 255), -1)
    img[y1c + 5:y1c + 5 + shine_h, x1c + 5:x2c - 5] = cv2.addWeighted(
        shine[y1c + 5:y1c + 5 + shine_h, x1c + 5:x2c - 5], 0.08,
        img[y1c + 5:y1c + 5 + shine_h, x1c + 5:x2c - 5], 0.92, 0
    )
    return img

def draw_neon_border(img, intensity=0.5):
    h, w = img.shape[:2]
    t = (math.sin(time.time() * 2) + 1) / 2
    outer_color = color_lerp((20, 80, 160), (120, 80, 200), t)
    thickness = int(6 * (0.5 + intensity))
    cv2.rectangle(img, (3, 3), (w - 4, h - 4), outer_color, thickness, cv2.LINE_AA)
    return img

def show_loading(frame_func, mode_text, duration=1.4):
    start = time.time()
    while time.time() - start < duration:
        frame = frame_func()
        h, w = frame.shape[:2]
        center = (w // 2, h // 2)
        radius = min(w, h) // 10
        angle = int((time.time() - start) * 360 * 2)
        thickness = 6
        cv2.ellipse(frame, center, (radius, radius), 0, angle, angle + 220, (120, 200, 255), thickness, cv2.LINE_AA)
        cv2.putText(frame, mode_text, (center[0] - 170, center[1] + radius + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (220, 220, 255), 2, cv2.LINE_AA)
        cv2.imshow("Main Menu - Gesture Controlled", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# --------- Main run function ----------
def run_gui():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not accessible")
        return None

    cv2.namedWindow("Main Menu - Gesture Controlled", cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty("Main Menu - Gesture Controlled", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    except Exception:
        pass

    trail = deque()
    trail_max_len = 18
    last_click_time = 0

    while True:
        success, frame = cap.read()
        if not success:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        # Background blur + grid
        bg = cv2.GaussianBlur(frame, (9, 9), 8)
        grid = bg.copy()
        step = 60
        for gx in range(0, w, step):
            cv2.line(grid, (gx, 0), (gx, h), (80, 60, 120), 1)
        for gy in range(0, h, step):
            cv2.line(grid, (0, gy), (w, gy), (80, 60, 120), 1)
        frame = cv2.addWeighted(bg, 0.84, grid, 0.16, 0)

        # Title
        title_y = int(h * 0.18)
        title = "Virtual World"
        glow = abs(math.sin(time.time() * 1.6))
        t_size = cv2.getTextSize(title, cv2.FONT_HERSHEY_SCRIPT_COMPLEX, 2.2, 6)[0]
        tx = (w - t_size[0]) // 2
        ty = title_y
        shadow_col = (30, 40, 80)
        cv2.putText(frame, title, (tx + 6, ty + 6), cv2.FONT_HERSHEY_SCRIPT_COMPLEX, 2.2, shadow_col, 6, cv2.LINE_AA)
        cv2.putText(frame, title, (tx, ty), cv2.FONT_HERSHEY_SCRIPT_COMPLEX, 2.2, (255, 255, 255), int(2 + 3 * glow), cv2.LINE_AA)

        # Single central LAUNCH button
        center_btn = (w // 2, int(h * 0.57))
        b_w = int(w * 0.32)
        b_h = int(h * 0.12)
        bx1 = center_btn[0] - b_w // 2
        by1 = center_btn[1] - b_h // 2
        bx2 = center_btn[0] + b_w // 2
        by2 = center_btn[1] + b_h // 2

        frame = draw_frosted_panel(frame, bx1 - 8, by1 - 8, bx2 + 8, by2 + 8, alpha=0.36)

        # Hand detection
        try:
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(img_rgb)
        except Exception:
            results = None

        hover_btn = 0.0
        finger_dist = None
        cursor_pos = None
        hand_confidence = 0.0

        if results and getattr(results, "multi_hand_landmarks", None):
            hand = results.multi_hand_landmarks[0]
            landmarks = [(int(lm.x * w), int(lm.y * h)) for lm in hand.landmark]

            # Thumb + Index for click
            p_index, p_thumb = landmarks[8], landmarks[4]
            cursor_pos = p_index
            finger_dist = dist(p_index, p_thumb)
            hand_confidence = 1.0
            trail.appendleft((p_index[0], p_index[1], time.time()))
            if len(trail) > trail_max_len:
                trail.pop()

            db = dist(p_index, center_btn)
            hover_btn = max(0.0, min(1.0, (260 - db) / 200))

            joined = finger_dist is not None and finger_dist < 40
            now = time.time()
            if joined and now - last_click_time > 0.45:
                last_click_time = now
                x, y = p_index
                if bx1 < x < bx2 and by1 < y < by2:
                    play_click_sound()

                    def frame_func():
                        ret, f = cap.read()
                        if not ret:
                            return frame
                        f = cv2.flip(f, 1)
                        f = cv2.GaussianBlur(f, (9, 9), 8)
                        f = cv2.addWeighted(f, 0.9, frame, 0.1, 0)
                        return f

                    show_loading(frame_func, "Launching...", duration=1.2)
                    cap.release()
                    cv2.destroyAllWindows()
                    return "LAUNCH"

            mpDraw.draw_landmarks(frame, hand, mpHands.HAND_CONNECTIONS,
                                  mpDraw.DrawingSpec(color=(80, 220, 180), thickness=1, circle_radius=2),
                                  mpDraw.DrawingSpec(color=(80, 140, 220), thickness=1))

        # hand trail
        if len(trail) > 1:
            for i in range(len(trail) - 1):
                x1t, y1t, t1 = trail[i]
                x2t, y2t, t2 = trail[i + 1]
                age = time.time() - t1
                alpha = max(0.0, 1.0 - age * 1.2)
                col = (int(120 * alpha + 10), int(200 * alpha + 10), int(255 * alpha + 10))
                thickness = int(6 * alpha) + 1
                cv2.line(frame, (x1t, y1t), (x2t, y2t), col, thickness, cv2.LINE_AA)

        scale = 1.0 + hover_btn * 0.08
        frame = draw_gradient_round_button(frame, bx1, by1, bx2, by2, "LAUNCH", glow=hover_btn, scale=scale)

        if finger_dist is not None and cursor_pos is not None:
            px, py = cursor_pos
            r = int(max(8, min(45, 80 - finger_dist)))
            color = (0, 255, 0) if finger_dist < 40 else (0, 180, 255)
            cv2.circle(frame, (px, py), r, color, 3, cv2.LINE_AA)
            if finger_dist < 40:
                cv2.putText(frame, "Click Detected", (px - 50, py + r + 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 180, 120), 2, cv2.LINE_AA)

        # hand confidence meter
        meter_x, meter_y = int(w * 0.86), int(h * 0.90)
        meter_w, meter_h = int(w * 0.10), int(h * 0.03)
        cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (30, 30, 40), -1, cv2.LINE_AA)
        fill_w = int(meter_w * hand_confidence)
        biz_color = (50, 200, 120) if hand_confidence > 0.6 else (50, 180, 230) if hand_confidence > 0.3 else (200, 80, 80)
        cv2.rectangle(frame, (meter_x, meter_y), (meter_x + fill_w, meter_y + meter_h), biz_color, -1, cv2.LINE_AA)
        cv2.putText(frame, "Hand", (meter_x - 60, meter_y + meter_h), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (220, 220, 220), 1, cv2.LINE_AA)

        frame = draw_neon_border(frame, intensity=0.6)
        cv2.imshow("Main Menu - Gesture Controlled", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return None

if __name__ == "__main__":
    choice = run_gui()
    print("User selected:", choice)