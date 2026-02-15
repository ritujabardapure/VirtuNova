# main.py
from multiprocessing import Process
import time
from gesture import virtual_mouse           # gesture.py function
from voice_os import main as start_voice    # voice module main function
from gui import run_gui                      # GUI run function

def launch_gesture():
    """
    Starts the gesture control module (Virtual Mouse).
    """
    try:
        print("[INFO] Gesture module started.")
        virtual_mouse()
    except Exception as e:
        print(f"[ERROR] Gesture module crashed: {e}")

def launch_voice():
    """
    Starts the voice control module.
    """
    try:
        print("[INFO] Voice module started.")
        start_voice()
    except Exception as e:
        print(f"[ERROR] Voice module crashed: {e}")

def launch_all_modules():
    """
    Launch both gesture and voice modules in separate processes.
    """
    print("[INFO] Launching Gesture and Voice modules...")

    # Create separate processes for gesture and voice
    gesture_process = Process(target=launch_gesture)
    voice_process = Process(target=launch_voice)

    # Start both processes
    gesture_process.start()
    voice_process.start()

    # Keep the main program running, handle graceful exit
    try:
        while True:
            time.sleep(1)
            # Optionally, restart if a process crashes
            if not gesture_process.is_alive():
                print("[WARNING] Gesture process stopped unexpectedly. Restarting...")
                gesture_process = Process(target=launch_gesture)
                gesture_process.start()
            if not voice_process.is_alive():
                print("[WARNING] Voice process stopped unexpectedly. Restarting...")
                voice_process = Process(target=launch_voice)
                voice_process.start()

    except KeyboardInterrupt:
        print("\n[INFO] Exiting program...")
        gesture_process.terminate()
        voice_process.terminate()
        gesture_process.join()
        voice_process.join()
        print("[INFO] All processes terminated successfully.")

if __name__ == "__main__":
    # Run GUI first
    choice = run_gui()
    if choice == "LAUNCH":
        launch_all_modules()
    else:
        print("[INFO] GUI closed without launching modules.")