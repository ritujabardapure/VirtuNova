import os
import time
import threading
import math
import sys
import traceback

import speech_recognition as sr
import pyttsx3
import pyautogui
import keyboard
from pywinauto import Desktop, Application
import win32gui
import win32con
import win32api
from ctypes import windll
from PIL import Image, ImageDraw, ImageFont
import tkinter as tk

# -----------------------
# Config
# -----------------------
LISTENING_INDICATOR = True
OVERLAY_TTL = 12.0  # seconds overlay stays
SPEECH_TIMEOUT = 3  # seconds to wait for one phrase
SPEECH_PHRASE_TIME_LIMIT = 4

# Use 'google' by default (requires internet). To use offline engines swap out recognizer.recognize_google().
USE_GOOGLE = True

# -----------------------
# Utilities
# -----------------------
engine = pyttsx3.init()
engine.setProperty('rate', 160)

def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print("TTS error:", e)

def press_win_and_type(text, wait=0.15):
    """Press Windows key, type, press enter"""
    pyautogui.press('win')
    time.sleep(0.12)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(wait)
    pyautogui.press('enter')

def get_active_window_handle():
    return win32gui.GetForegroundWindow()

def find_window_by_title_contains(name):
    name = name.lower()
    def enum_cb(hwnd, results):
        txt = win32gui.GetWindowText(hwnd).lower()
        cls = win32gui.GetClassName(hwnd).lower()
        if name in txt or name in cls:
            results.append(hwnd)
    results = []
    win32gui.EnumWindows(lambda h, r=results: enum_cb(h, r), None)
    return results

def minimize_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception as e:
        print("minimize error", e)

def maximize_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    except Exception as e:
        print("maximize error", e)

def restore_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception as e:
        print("restore error", e)

def close_window(hwnd):
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception as e:
        print("close window error", e)

# -----------------------
# Overlay helper (Tkinter transparent window with numbered labels)
# -----------------------
class OverlayManager:
    def __init__(self):
        self.root = None
        self.labels = []
        self.visible = False

    def _start_root(self):
        if self.root:
            return
        self.root = tk.Tk()
        self.root.attributes('-topmost', True)
        # make window fullscreen and transparent
        self.root.overrideredirect(True)
        self.root.geometry(f"{pyautogui.size().width}x{pyautogui.size().height}+0+0")
        self.root.config(bg='systemTransparent')
        # required on Windows to allow click-through? We'll make labels clickable not root.
        # Make window transparent using layered attributes:
        try:
            self.root.wm_attributes('-transparentcolor', 'systemTransparent')
        except Exception:
            pass

    def show_numbered_overlays(self, coords_list):
        """
        coords_list: list of (x_center, y_center) tuples to overlay numbers near
        returns a map number->(x,y) to be used for clicking
        """
        self._start_root()
        # clear old
        for lbl in self.labels:
            try:
                lbl.destroy()
            except: pass
        self.labels = []
        self.visible = True

        # Draw small circular numbers using Tk labels with an image
        for idx, (x, y) in enumerate(coords_list, start=1):
            lbl = tk.Label(self.root, bd=0)
            # create an image circle with number
            img = self._make_number_image(idx)
            lbl.img = img
            lbl.config(image=img)
            # place slightly above/left of the center so it doesn't cover icon entirely
            w = img.width()
            h = img.height()
            px = int(x - w/2)
            py = int(y - h - 10)
            lbl.place(x=px, y=py)
            self.labels.append(lbl)

        # small listening indicator
        if LISTENING_INDICATOR:
            self.ind_lbl = tk.Label(self.root, text="Listening...", font=("Segoe UI", 10), bg="#222", fg="white")
            self.ind_lbl.place(x=10, y=10)
        # Run root update in new thread so main program isn't blocked
        def run():
            start = time.time()
            while time.time() - start < OVERLAY_TTL and self.visible:
                try:
                    self.root.update()
                except Exception:
                    break
            self.clear()
        t = threading.Thread(target=run, daemon=True)
        t.start()

        # return mapping of numbers to positions (center coords)
        mapping = {i+1: coords_list[i] for i in range(len(coords_list))}
        return mapping

    def clear(self):
        self.visible = False
        if self.root:
            try:
                for lbl in self.labels:
                    lbl.destroy()
                self.labels = []
                if hasattr(self, 'ind_lbl'):
                    self.ind_lbl.destroy()
                self.root.destroy()
            except Exception as e:
                pass
            self.root = None

    def _make_number_image(self, number, diameter=36):
        # Create a PIL image of a circle with a number then convert to Tk PhotoImage
        img = Image.new('RGBA', (diameter, diameter), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        # circle background
        draw.ellipse((0,0,diameter-1, diameter-1), fill=(36,36,36,220))
        # text
        try:
            font = ImageFont.truetype("Arial.ttf", int(diameter*0.5))
        except:
            font = ImageFont.load_default()
        w,h = draw.textsize(str(number), font=font)
        draw.text(((diameter-w)/2, (diameter-h)/2-1), str(number), fill=(255,255,255,255), font=font)
        return tk.PhotoImage(data=pil_image_to_base64(img))

def pil_image_to_base64(pil_image):
    # convert PIL image to Tk base64 string
    from io import BytesIO
    buf = BytesIO()
    pil_image.save(buf, format='PNG')
    b = buf.getvalue()
    import base64
    return base64.b64encode(b)

# -----------------------
# Explorer enumerator using pywinauto UIA backend
# -----------------------
def enumerate_explorer_visible_items():
    """
    Find the currently active File Explorer window and return a list of items with screen coordinates
    Returns list of tuples: (name, (center_x, center_y))
    """
    try:
        desktop = Desktop(backend="uia")
        # find active explorer window
        win = None
        foreground = get_active_window_handle()
        fg_title = win32gui.GetWindowText(foreground).lower()
        # Attempt to find an 'Explorer' window among top windows
        for w in desktop.windows():
            try:
                if 'file explorer' in w.window_text().lower() or 'explorer' in w.window_text().lower() or w.process_id() and 'explorer.exe' in str(w.process_id()):
                    # choose the one that matches foreground if possible
                    if w.handle == foreground:
                        win = w
                        break
                    # fallback: use the first explorer-like window
                    if win is None:
                        win = w
            except Exception:
                continue
        if win is None:
            # try connecting to any explorer window
            for w in desktop.windows():
                txt = w.window_text().lower()
                if 'file explorer' in txt or 'explorer' in txt:
                    win = w
                    break
        if win is None:
            return []

        # try to find the items control (List or DataGrid)
        items = []
        # search for List control
        try:
            list_ctrls = win.descendants(control_type="List")
            if not list_ctrls:
                list_ctrls = win.descendants(control_type="DataGrid")
            if not list_ctrls:
                list_ctrls = win.descendants(control_type="ListItem")
            # pick the first list-like control
            if list_ctrls:
                # flatten to items
                elems = []
                for c in list_ctrls:
                    try:
                        elems += c.descendants(control_type="ListItem")
                    except Exception:
                        pass
                if not elems:
                    # maybe the list_ctrls themselves are items
                    elems = list_ctrls
                # gather names and rectangles
                for e in elems[:60]:  # limit for performance
                    try:
                        rect = e.rectangle()
                        cx = (rect.left + rect.right) // 2
                        cy = (rect.top + rect.bottom) // 2
                        name = e.window_text() or e.legacy_properties().get('Name', '') if hasattr(e, 'legacy_properties') else e.window_text()
                        if name:
                            items.append((name, (cx, cy)))
                    except Exception:
                        continue
        except Exception as ex:
            print("explorer enumerate inner error:", ex)
            # fallback: use icon positions from the desktop or grid, but that's out of scope

        return items
    except Exception as e:
        print("enumerate_explorer_visible_items EX:", e)
        return []

# -----------------------
# Main Voice Controller
# -----------------------
class VoiceDesktopController:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = False
        self.overlay = OverlayManager()
        # Pre-warm microphone
        with self.microphone as mic:
            self.recognizer.adjust_for_ambient_noise(mic, duration=1.0)

    def listen_once(self, timeout=SPEECH_TIMEOUT, phrase_time_limit=SPEECH_PHRASE_TIME_LIMIT):
        with self.microphone as source:
            audio = None
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return ""
        try:
            if USE_GOOGLE:
                text = self.recognizer.recognize_google(audio)
            else:
                text = self.recognizer.recognize_sphinx(audio)
            return text.lower()
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            print("recognition error:", e)
            return ""

    def start(self):
        self.running = True
        speak("Voice desktop assistant started.")
        print("Listening for commands. Say 'help' to hear commands.")
        # Main loop
        while self.running:
            try:
                print("Waiting for command...")
                text = self.listen_once()
                if not text:
                    continue
                print("Heard:", text)
                handled = self.handle_command(text)
                if not handled:
                    speak("Sorry, I didn't understand. Say help to list commands.")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("Main loop error:", e)
                traceback.print_exc()
        speak("Assistant stopped.")

    def stop(self):
        self.running = False

    def handle_command(self, text):
        # basic commands patterns
        if 'help' in text:
            cmds = [
                "Open app <name>",
                "Open folder <full path> or say open documents / open downloads",
                "Open this pc",
                "Enumerate files",
                "Click number <n>",
                "Minimize window",
                "Maximize window",
                "Restore window",
                "Close window",
                "Close app <name>",
                "Refresh",
                "Back",
                "Forward",
                "Stop assistant",
            ]
            speak("Available commands. " + ", ".join(cmds))
            return True

        if 'stop assistant' in text or 'exit assistant' in text or 'quit assistant' in text:
            speak("Shutting down assistant.")
            self.stop()
            return True

        # ---------------------- TYPE COMMAND ----------------------
        if text.startswith("type "):
            to_type = text.replace("type ", "", 1).strip()

            if not to_type:
                speak("Please say what to type.")
                return True

            speak("Typing your text.")
            pyautogui.typewrite(to_type, interval=0.03)
            return True

        # PRESS KEYBOARD BUTTONS
        if text.startswith("press "):
            command = text.replace("press ", "", 1).strip()

            # Mapping for common keys users speak differently
            key_alias = {
                "enter": "enter",
                "return": "enter",
                "escape": "esc",
                "esc": "esc",
                "space": "space",
                "spacebar": "space",
                "tab": "tab",
                "backspace": "backspace",
                "delete": "delete",
                "up": "up",
                "down": "down",
                "left": "left",
                "right": "right",
                "windows": "win",
                "window": "win",
                "win": "win",
                "control": "ctrl",
                "ctrl": "ctrl",
                "alt": "alt",
                "shift": "shift",
                "f one": "f1",
                "f two": "f2",
                "f three": "f3",
                "f four": "f4",
                "f five": "f5",
                "f six": "f6",
                "f seven": "f7",
                "f eight": "f8",
                "f nine": "f9",
                "f ten": "f10",
                "f eleven": "f11",
                "f twelve": "f12",
            }

            # Convert spoken words to pyautogui key names
            words = command.split()
            keys = []

            for word in words:
                keys.append(key_alias.get(word, word))

            try:
                if len(keys) == 1:
                    # Single key press
                    pyautogui.press(keys[0])
                else:
                    # Combination like ctrl + c, alt + f4, windows + d
                    pyautogui.hotkey(*keys)

                speak(f"Pressed {' '.join(keys)}")
            except Exception as e:
                speak("Sorry, I could not press that key.")
                print("Key press error:", e)

            return True

        # Open app via start/search
        if text.startswith('open app') or text.startswith('open ') and ('app' in text and 'open app' in text):
            # two variants: "open app chrome" or "open chrome"
            target = text.replace('open app', '').replace('open', '').strip()
            if not target:
                speak("Say the app name after open.")
                return True
            speak(f"Opening {target}")
            press_win_and_type(target)
            return True

        # direct "open chrome" or "open notepad"
        if text.startswith('open '):
            target = text.replace('open', '', 1).strip()
            # if "open this pc" or "open file explorer" or "open documents"
            if target in ('this pc', 'file explorer', 'explorer'):
                # open explorer
                speak("Opening File Explorer.")
                os.startfile("explorer.exe")
                return True
            # common known folders
            if target in ('documents', 'my documents'):
                speak("Opening Documents.")
                os.startfile(os.path.join(os.path.expanduser('~'), 'Documents'))
                return True
            if target in ('downloads', 'download'):
                speak("Opening Downloads.")
                os.startfile(os.path.join(os.path.expanduser('~'), 'Downloads'))
                return True
            if os.path.exists(target):  # path given
                speak(f"Opening {target}")
                try:
                    os.startfile(target)
                except Exception as e:
                    speak("Couldn't open that path.")
                return True
            # else treat as app name search in start
            speak(f"Opening {target}")
            press_win_and_type(target)
            return True

        # enumerate files in active explorer
        if 'enumerate files' in text or 'list files' in text or 'enumerate' in text or 'show files' in text:
            items = enumerate_explorer_visible_items()
            if not items:
                speak("I couldn't find a File Explorer window. Please open the folder you want and say enumerate files again.")
                return True
            # prepare coordinates list
            coords = [coord for (_, coord) in items]
            mapping = self.overlay.show_numbered_overlays(coords)
            # speak names optionally (keep short)
            speak(f"I found {len(items)} items. Say the number to open the item.")
            # wait for a number from user
            number_spoken = self._listen_for_number()
            if number_spoken is None:
                speak("No number heard. Cancelling.")
                self.overlay.clear()
                return True
            # click the coordinate
            if number_spoken in mapping:
                x,y = mapping[number_spoken]
                pyautogui.click(x, y)
                speak("Clicked item number " + str(number_spoken))
            else:
                speak("That number is not valid.")
            self.overlay.clear()
            return True

        # click number explicit
        if text.startswith('click') and 'number' in text:
            # "click number 4"
            words = text.split()
            for w in words:
                if w.isdigit():
                    n = int(w)
                    # we need mapping from last overlay - for simplicity, re-enumerate and map 1.N to current items
                    items = enumerate_explorer_visible_items()
                    if not items:
                        speak("No Explorer items found.")
                        return True
                    # map indices to coords
                    if 1 <= n <= len(items):
                        x,y = items[n-1][1]
                        pyautogui.click(x,y)
                        speak("Clicked number " + str(n))
                        return True
                    else:
                        speak("Number out of range.")
                        return True
            speak("I didn't catch a number to click.")
            return True

        # minimize, maximize, restore, close active window
        if 'minimize' in text or ('minimise' in text):
            hwnd = get_active_window_handle()
            minimize_window(hwnd)
            speak("Window minimized.")
            return True
        if 'maximize' in text:
            hwnd = get_active_window_handle()
            maximize_window(hwnd)
            speak("Window maximized.")
            return True
        if 'restore' in text or 'unmaximize' in text or 'restore window' in text:
            hwnd = get_active_window_handle()
            restore_window(hwnd)
            speak("Window restored.")
            return True
        if 'close window' in text or text.startswith('close '):
            # close the active window or close by name
            if text == 'close window':
                hwnd = get_active_window_handle()
                close_window(hwnd)
                speak("Window closed.")
                return True
            else:
                # "close app chrome"
                target = text.replace('close app','').replace('close','').strip()
                if not target:
                    speak("Say the app name to close.")
                    return True
                wins = find_window_by_title_contains(target)
                if not wins:
                    speak("I couldn't find a window with that name.")
                    return True
                for w in wins:
                    close_window(w)
                speak(f"Closed {len(wins)} window(s) with name {target}.")
                return True

        # navigation commands
        if 'refresh' in text:
            keyboard.send('f5')
            speak("Refreshed.")
            return True
        if text == 'back':
            keyboard.send('alt+left')
            speak("Back.")
            return True
        if text == 'forward':
            keyboard.send('alt+right')
            speak("Forward.")
            return True

        # fallback
        return False

    def _listen_for_number(self, timeout=8):
        # listens for a number word or digit and returns int or None
        start = time.time()
        end_time = start + timeout
        while time.time() < end_time:
            txt = self.listen_once(timeout=3, phrase_time_limit=3)
            if not txt:
                continue
            print("Number-heard:", txt)
            # try to extract integer
            for token in txt.split():
                if token.isdigit():
                    return int(token)
            # attempt to convert number words (one,two,three...)
            word_to_num = {
                'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
                'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20
            }
            for w,n in word_to_num.items():
                if w in txt:
                    return n
        return None

# -----------------------
# Run assistant
# -----------------------
def main():
    # Ensure pyautogui FAILSAFE off (corner mouse won't break)
    pyautogui.FAILSAFE = False
    controller = VoiceDesktopController()
    try:
        controller.start()
    except Exception as e:
        print("Fatal error:", e)
        traceback.print_exc()
    finally:
        controller.overlay.clear()

if __name__ == '__main__':
    main()
