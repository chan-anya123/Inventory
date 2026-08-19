#!/usr/bin/env python3
"""
Fully Encapsulated QR Camera Manager & Video Vision Engine
Lazy / On-Demand Camera Lifecycle: Only opens hardware camera when requested/used.
"""

import os
import re
import cv2
import time
import json
import logging
import datetime
import threading
import subprocess
import numpy as np
from typing import Optional, List, Dict, Tuple, Any, Generator

try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

log = logging.getLogger("qr_camera")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)


def get_default_base_dir() -> str:
    """Resolve project base directory (parent of scripts directory)."""
    curr = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(curr) == "scripts":
        return os.path.dirname(curr)
    return curr


class QRCameraManager:
    """
    Fully Encapsulated Camera Manager & QR Code Scanning Engine Class.
    
    On-Demand / Standby Architecture:
    - Does NOT open the hardware camera (/dev/video0) on application startup.
    - Only opens camera when a stream is opened (/video_feed) or a scan is requested (/read, /slot/drop/scan).
    - Automatically releases camera hardware back to the OS when idle.
    """

    def __init__(self, camera_index: int = None, width: int = 640, height: int = 480, base_dir: str = None):
        if camera_index is None or camera_index < 0:
            avail = self.list_available_cameras()
            camera_index = avail[0]["index"] if avail else 0

        self.index: int = camera_index
        self.width: int = width
        self.height: int = height
        self.start_time: float = time.time()
        self.lock = threading.Lock()

        # Directories and configuration file paths
        self.base_dir: str = base_dir or get_default_base_dir()
        self.setups_dir: str = os.path.join(self.base_dir, "data/camera_setups")
        self.captures_dir: str = os.path.join(self.base_dir, "captures")
        self.config_path: str = os.path.join(self.base_dir, "data/camera_setup.json")
        os.makedirs(self.setups_dir, exist_ok=True)
        os.makedirs(self.captures_dir, exist_ok=True)

        # Image adjustment settings
        self.settings: Dict[str, Any] = {
            "brightness": 0,         # Range: -100 to 100
            "contrast": 1.0,         # Range: 0.1 to 3.0
            "exposure": 0,           # Range: -5 to 5 (EV Shift)
            "threshold": 0,          # Range: 0 (Off) to 255
        }

        # Captured QR Frame Storage
        self.last_qr_frame: Optional[np.ndarray] = None
        self.last_qr_data: Optional[str] = None
        # Standby state - Camera is NOT opened initially (On-Demand)
        self.cap: Optional[cv2.VideoCapture] = None
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.last_frame_time: float = 0.0
        self.last_access_time: float = 0.0
        self.active_stream_count: int = 0
        self.idle_timeout: float = 8.0  # Seconds of inactivity before releasing hardware

        # Track if user explicitly requested a saved profile/custom tuning
        self.has_custom_profile_loaded: bool = False

        # Always start with native clean hardware & software defaults
        self.reset_to_camera_defaults(camera_index)

        log.info("QR Camera Engine initialized in STANDBY mode with clean native defaults on index %s (opens on-demand)", camera_index)

    # -------------------------------------------------------------------------
    # Static Utility Methods (Scoped Inside Class)
    # -------------------------------------------------------------------------

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitize string for safe filesystem usage."""
        if not name:
            return f"setup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', str(name).strip())
        if not cleaned:
            return f"setup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return cleaned

    @staticmethod
    def is_video_capture_device(dev_path: str) -> bool:
        """Check if device path supports standard Video Capture (and is not purely metadata)."""
        try:
            res = subprocess.run(["v4l2-ctl", "-d", dev_path, "--info"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                in_dev_caps = False
                for line in res.stdout.splitlines():
                    if "Device Caps" in line:
                        in_dev_caps = True
                    elif in_dev_caps:
                        if line.startswith("\t\t") or line.startswith("        "):
                            if "Video Capture" in line and "Metadata" not in line:
                                return True
                        elif line and not line.startswith("\t") and not line.startswith(" "):
                            in_dev_caps = False
        except Exception:
            pass
        return False

    @staticmethod
    def list_available_cameras() -> List[Dict[str, Any]]:
        """Scan and return a list of available connected camera devices (only real Video Capture streams)."""
        cameras = []
        try:
            res = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                curr_name = "Camera"
                for line in res.stdout.splitlines():
                    if line and not line.startswith("\t"):
                        curr_name = line.strip().split("(")[0].strip()
                    elif line.startswith("\t/dev/video"):
                        dev_path = line.strip()
                        if QRCameraManager.is_video_capture_device(dev_path):
                            try:
                                idx = int(re.sub(r'\D', '', dev_path))
                                if not any(c["index"] == idx for c in cameras):
                                    cameras.append({"index": idx, "name": f"{curr_name} ({dev_path})"})
                            except ValueError:
                                pass
        except Exception as e:
            log.debug("v4l2-ctl camera list warning: %s", e)

        if not cameras:
            for i in range(8):
                dev_path = f"/dev/video{i}"
                if os.path.exists(dev_path) and QRCameraManager.is_video_capture_device(dev_path):
                    cameras.append({"index": i, "name": f"Camera {i} ({dev_path})"})

        return sorted(cameras, key=lambda x: x["index"]) if cameras else [{"index": 0, "name": "Camera 0 (/dev/video0)"}]

    def list_cameras(self) -> List[Dict[str, Any]]:
        """Instance method to list available cameras."""
        return self.list_available_cameras()

    # -------------------------------------------------------------------------
    # On-Demand Hardware Lifecycle Management
    # -------------------------------------------------------------------------

    def _ensure_camera_active(self) -> bool:
        """Open camera hardware and start grabber thread if not already running."""
        with self.lock:
            self.last_access_time = time.time()
            if self.cap is not None and self.cap.isOpened() and self.running:
                return True

            log.info("Activating camera index %s on-demand...", self.index)
            if self.cap and self.cap.isOpened():
                self.cap.release()

            self.cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
            if self.width:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            if not self.cap.isOpened():
                log.warning("Could not open camera index %s", self.index)
                return False

            log.info("Camera index %s opened successfully on-demand", self.index)
            self.running = True

            # Apply hardware settings directly on device
            if not self.has_custom_profile_loaded:
                self.reset_hardware_ctrls_unlocked(self.index)
            else:
                self._apply_v4l2_settings_unlocked(self.settings)
            self.disable_autofocus(self.index)

            # Start continuous background capture thread
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._capture_loop, daemon=True)
                self.thread.start()

            return True

    def stop_camera(self):
        """Release camera hardware back to the system immediately."""
        with self.lock:
            self.running = False
            if self.cap and self.cap.isOpened():
                self.cap.release()
                log.info("Camera index %s released back to OS", self.index)
            self.cap = None
            self.latest_frame = None

    def switch_camera(self, new_index: int) -> int:
        """Switch active camera to a new device index, resetting to its clean native defaults."""
        if self.index == new_index and self.cap is not None and self.cap.isOpened():
            return self.index

        log.info("Switching camera from %s to %s", self.index, new_index)
        was_running = self.running or (self.active_stream_count > 0)
        self.stop_camera()

        self.index = int(new_index)
        self.reset_to_camera_defaults(self.index)

        if was_running:
            self._ensure_camera_active()

        return self.index

    def reset_hardware_ctrls_unlocked(self, index: int = None):
        """Execute physical hardware register factory reset directly on device via V4L2."""
        idx = index if index is not None else self.index
        dev_path = f"/dev/video{idx}"
        try:
            res = subprocess.run(["v4l2-ctl", "-d", dev_path, "--list-ctrls"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                ctrl_sets = []
                for line in res.stdout.splitlines():
                    if "default=" in line and "flags=inactive" not in line and "flags=read-only" not in line:
                        parts = line.strip().split()
                        if parts:
                            ctrl_name = parts[0]
                            m = re.search(r'default=(-?\d+)', line)
                            if m:
                                ctrl_sets.append(f"{ctrl_name}={m.group(1)}")
                if ctrl_sets:
                    log.info("Resetting physical hardware registers on %s to defaults (%s)", dev_path, ', '.join(ctrl_sets))
                    subprocess.run(
                        ["v4l2-ctl", "-d", dev_path, f"--set-ctrl={','.join(ctrl_sets)}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=3,
                    )
        except Exception as e:
            log.debug("V4L2 hardware defaults reset on %s: %s", dev_path, e)

    def reset_to_camera_defaults(self, index: int = None) -> dict:
        """Reset hardware controls directly on the camera device to manufacturer factory defaults."""
        idx = index if index is not None else self.index
        with self.lock:
            self.settings = {
                "brightness": 0,
                "contrast": 1.0,
                "exposure": 0,
                "threshold": 0,
            }
            self.has_custom_profile_loaded = False
            self.reset_hardware_ctrls_unlocked(idx)

        self.disable_autofocus(idx)
        log.info("Reset camera %s directly at hardware level to factory defaults", idx)
        return self.get_settings()

    def disable_autofocus(self, index: int = None):
        """Disable autofocus on the camera if supported by hardware controls."""
        idx = index if index is not None else self.index
        dev_path = f"/dev/video{idx}"

        if self.cap and self.cap.isOpened():
            try:
                self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            except Exception as e:
                log.debug("OpenCV disable autofocus warning on index %s: %s", idx, e)

        try:
            res = subprocess.run(
                ["v4l2-ctl", "-d", dev_path, "--list-ctrls"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0:
                ctrls_to_disable = []
                for line in res.stdout.splitlines():
                    if "flags=inactive" in line or "flags=read-only" in line:
                        continue
                    if "focus_automatic_continuous" in line:
                        ctrls_to_disable.append("focus_automatic_continuous=0")
                    elif "focus_auto" in line:
                        ctrls_to_disable.append("focus_auto=0")

                if ctrls_to_disable:
                    subprocess.run(
                        ["v4l2-ctl", "-d", dev_path, f"--set-ctrl={','.join(ctrls_to_disable)}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=2,
                    )
        except Exception as e:
            log.debug("v4l2-ctl disable autofocus error on %s: %s", dev_path, e)

    def get_config_path(self, index: int = None) -> str:
        """Get path to camera setup file for a specific camera index."""
        idx = index if index is not None else self.index
        return os.path.join(self.setups_dir, f"camera_setup_cam{idx}.json")

    def _save_setup_unlocked(self, index: int = None):
        """Save settings for a specific camera index."""
        idx = index if index is not None else self.index
        path = self.get_config_path(idx)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            log.error("Failed to save camera %s setup: %s", idx, e)

    def save_current_setup(self, index: int = None):
        """Public method to save current camera settings."""
        with self.lock:
            self._save_setup_unlocked(index)

    def load_saved_setup(self, index: int = None):
        """Load persistent settings for a specific camera index."""
        idx = index if index is not None else self.index
        path = self.get_config_path(idx)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
                    log.info("Loaded camera %s setup from %s", idx, path)
                    return
            except Exception as e:
                log.error("Error loading setup file for camera %s: %s", idx, e)

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                log.error("Error loading main camera config: %s", e)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all saved camera setup preset profiles."""
        profiles = []
        if not os.path.exists(self.setups_dir):
            return profiles
        for fn in sorted(os.listdir(self.setups_dir)):
            if fn.endswith(".json"):
                full_p = os.path.join(self.setups_dir, fn)
                try:
                    with open(full_p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        name = data.get("profile_name", fn.replace(".json", ""))
                        profiles.append({
                            "name": name,
                            "filename": fn,
                            "settings": data.get("settings", data)
                        })
                except Exception:
                    pass
        return profiles

    def save_profile(self, name: str = None, new_settings: dict = None) -> dict:
        """Save settings to a named profile JSON file."""
        with self.lock:
            if new_settings:
                for k in ["brightness", "contrast", "exposure", "threshold"]:
                    if k in new_settings:
                        self.settings[k] = new_settings[k]

            clean_name = self.sanitize_filename(name or f"profile_{int(time.time())}")
            filename = f"{clean_name}.json"
            filepath = os.path.join(self.setups_dir, filename)

            payload = {
                "profile_name": name or clean_name,
                "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "camera_index": self.index,
                "settings": self.settings.copy()
            }
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                log.info("Saved camera setup profile to file: %s", filepath)
            except Exception as e:
                log.error("Failed to save camera profile %s: %s", filepath, e)
                raise

            self._save_setup_unlocked(self.index)
            return {"status": "ok", "filename": filename, "profile": payload}

    def load_profile(self, target: str) -> dict:
        """Load and apply a specific setup profile by filename or name."""
        filename = target if target.endswith(".json") else f"{self.sanitize_filename(target)}.json"
        filepath = os.path.join(self.setups_dir, filename)

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Profile {filename} not found")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        settings_to_apply = data.get("settings", data)
        self.has_custom_profile_loaded = True
        return self.update_settings(settings_to_apply)

    def get_settings(self) -> dict:
        """Return the current camera image settings dictionary."""
        with self.lock:
            return self.settings.copy()

    def update_settings(self, new_settings: dict) -> dict:
        """Update brightness, contrast, exposure, threshold settings and persist."""
        with self.lock:
            for k in ["brightness", "contrast", "exposure", "threshold"]:
                if k in new_settings:
                    try:
                        if k == "contrast":
                            self.settings[k] = float(new_settings[k])
                        else:
                            self.settings[k] = int(new_settings[k])
                    except (ValueError, TypeError):
                        pass

            self.has_custom_profile_loaded = True
            self._apply_v4l2_settings_unlocked(self.settings)
            self._save_setup_unlocked(self.index)
            return self.settings.copy()

    def _apply_v4l2_settings_unlocked(self, s: dict):
        """Apply camera hardware settings via v4l2-ctl and OpenCV."""
        dev_path = f"/dev/video{self.index}"
        b = s.get("brightness", 0)
        c = s.get("contrast", 1.0)
        exp = s.get("exposure", 0)

        if self.cap and self.cap.isOpened():
            try:
                self.cap.set(cv2.CAP_PROP_BRIGHTNESS, float(b))
            except Exception:
                pass
            try:
                self.cap.set(cv2.CAP_PROP_CONTRAST, float(c))
            except Exception:
                pass

        try:
            ctrls = []
            if "brightness" in s:
                v4l_b = int(max(0, min(255, int(b) + 128)))
                ctrls.append(f"brightness={v4l_b}")
            if "contrast" in s:
                v4l_c = int(max(0, min(255, int(float(c) * 32))))
                ctrls.append(f"contrast={v4l_c}")
            if "exposure" in s and exp != 0:
                ctrls.append(f"exposure_auto=1")
                v4l_exp = int(max(1, min(10000, 156 + int(exp) * 20)))
                ctrls.append(f"exposure_absolute={v4l_exp}")

            if ctrls:
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, f"--set-ctrl={','.join(ctrls)}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
        except Exception:
            pass

    def auto_adjust_settings(self) -> dict:
        """Measure current frame luminosity and auto-calculate optimal baseline."""
        self._ensure_camera_active()
        time.sleep(0.3)
        frame = self.read_frame()
        if frame is None:
            return self.get_settings()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_lum = float(np.mean(gray))

        new_settings = {
            "brightness": 0,
            "contrast": 1.0,
            "exposure": 0,
            "threshold": 0
        }

        if mean_lum < 60:
            new_settings["brightness"] = int(min(60, (100 - mean_lum) * 0.8))
            new_settings["contrast"] = 1.3
        elif mean_lum > 190:
            new_settings["brightness"] = int(max(-60, (140 - mean_lum) * 0.8))
            new_settings["contrast"] = 1.2
        else:
            new_settings["contrast"] = 1.1

        return self.update_settings(new_settings)

    def reset_to_factory(self) -> dict:
        """Reset hardware and software settings to clean camera device defaults."""
        return self.reset_to_camera_defaults(self.index)

    # -------------------------------------------------------------------------
    # Frame Capturing & QR Code Decoding
    # -------------------------------------------------------------------------

    def set_last_qr_capture(self, frame: np.ndarray, data: str):
        """Save frame snapshot to disk."""
        now = time.time()
        safe_data = self.sanitize_filename(str(data).strip())[:50]
        if not safe_data:
            safe_data = "unknown"

        filename = f"qr_{safe_data}.jpg"
        save_path = os.path.join(self.captures_dir, filename)

        with self.lock:
            self.last_qr_frame = frame.copy() if frame is not None else None
            self.last_qr_data = data
            self.last_qr_time = now
            self.last_qr_filename = filename

        if frame is not None:
            try:
                cv2.imwrite(save_path, frame)
                log.info("Saved QR capture image to: %s", save_path)
            except Exception as e:
                log.error("Failed to save QR capture image: %s", e)

    def get_last_qr_capture(self) -> Tuple[Optional[np.ndarray], Optional[str], Optional[float], Optional[str]]:
        """Get latest saved QR capture frame, text, timestamp, filename."""
        with self.lock:
            if self.last_qr_frame is None:
                return None, None, None, None
            return self.last_qr_frame.copy(), self.last_qr_data, self.last_qr_time, self.last_qr_filename

    def _capture_loop(self):
        """Continuous background thread loop to grab frames while active."""
        consecutive_failures = 0
        while self.running:
            now = time.time()
            with self.lock:
                is_opened = self.cap.isOpened() if self.cap else False
                active_streams = self.active_stream_count
                last_access = self.last_access_time

            # Auto-standby check: If no active streams and idle timeout expired -> release hardware
            if active_streams == 0 and (now - last_access) > self.idle_timeout:
                log.info("No active camera users for %ss -> putting camera into STANDBY", int(self.idle_timeout))
                self.stop_camera()
                break

            if not is_opened:
                time.sleep(0.5)
                continue

            with self.lock:
                ok, raw_frame = self.cap.read() if self.cap else (False, None)
                b = self.settings.get("brightness", 0)
                c = self.settings.get("contrast", 1.0)
                exp = self.settings.get("exposure", 0)
                t_val = self.settings.get("threshold", 0)

            if ok and raw_frame is not None:
                consecutive_failures = 0
                processed = raw_frame

                alpha = c * (2.0 ** (exp * 0.3)) if exp != 0 else c
                beta = float(b)
                if alpha != 1.0 or beta != 0:
                    processed = cv2.convertScaleAbs(processed, alpha=alpha, beta=beta)

                if t_val > 0:
                    gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
                    _, binarized = cv2.threshold(gray, t_val, 255, cv2.THRESH_BINARY)
                    processed = cv2.cvtColor(binarized, cv2.COLOR_GRAY2BGR)

                with self.lock:
                    self.latest_frame = processed
                    self.last_frame_time = time.time()
            else:
                consecutive_failures += 1
                if consecutive_failures >= 15:
                    log.warning("Failed 15 consecutive reads. Releasing camera.")
                    self.stop_camera()
                    break
                time.sleep(0.04)

            time.sleep(0.01)

    def read_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the latest processed frame (wakes camera if in standby)."""
        self._ensure_camera_active()
        # Allow short warm-up for frame to arrive
        for _ in range(20):
            with self.lock:
                if self.latest_frame is not None:
                    return self.latest_frame.copy()
            time.sleep(0.05)

        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def is_ready(self) -> bool:
        """Check if camera device is available and can be activated."""
        avail = self.list_available_cameras()
        return len(avail) > 0

    def get_health(self) -> dict:
        """Return camera diagnostic metrics."""
        with self.lock:
            opened = self.cap.isOpened() if self.cap else False
            has_frame = self.latest_frame is not None
            last_time = self.last_frame_time
            running = self.running

        uptime = round(time.time() - self.start_time, 1)
        return {
            "status": "active" if (opened and has_frame) else ("standby" if not running else "opening"),
            "camera_connected": opened,
            "is_standby": not running,
            "camera_index": self.index,
            "has_latest_frame": has_frame,
            "seconds_since_last_frame": round(time.time() - last_time, 2) if last_time > 0 else None,
            "uptime_seconds": uptime,
            "timestamp": time.time(),
        }

    def read_qr(self, retries: int = 3, retry_interval: float = 0.2) -> Optional[str]:
        """Attempt to decode a QR code from the camera on-demand."""
        self._ensure_camera_active()
        last_frame_ok = False

        for attempt in range(1, retries + 1):
            frame = self.read_frame()
            if frame is None:
                if attempt < retries:
                    time.sleep(0.1)
                continue
            last_frame_ok = True

            results = decode_qr(frame) if decode_qr else []
            if not results:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                results = decode_qr(gray) if decode_qr else []

            if results:
                qr_text = results[0].data.decode("utf-8", errors="replace")
                annotated = frame.copy()
                h_img, w_img = annotated.shape[:2]

                try:
                    points = results[0].polygon
                    if points and len(points) >= 4:
                        pts = np.array([(p.x, p.y) for p in points], dtype=np.int32).reshape((-1, 1, 2))
                        cv2.polylines(annotated, [pts], True, (0, 255, 0), 3)
                    elif results[0].rect:
                        rect = results[0].rect
                        cv2.rectangle(annotated, (rect.left, rect.top), (rect.left + rect.width, rect.top + rect.height), (0, 255, 0), 3)
                except Exception:
                    pass

                try:
                    if points and len(points) >= 4:
                        xs = [p.x for p in points]
                        ys = [p.y for p in points]
                        x_min, x_max = min(xs), max(xs)
                        y_min, y_max = min(ys), max(ys)
                    elif results[0].rect:
                        rect = results[0].rect
                        x_min, x_max = rect.left, rect.left + rect.width
                        y_min, y_max = rect.top, rect.top + rect.height
                    else:
                        x_min, x_max, y_min, y_max = 20, 200, 20, 200

                    if y_max + 48 > h_img:
                        text_y1 = max(22, y_min - 24)
                        text_y2 = text_y1 + 18
                    else:
                        text_y1 = y_max + 22
                        text_y2 = y_max + 40

                    ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    line1 = f"{qr_text}"
                    line2 = f"{ts_str}"

                    font = cv2.FONT_HERSHEY_SIMPLEX
                    scale1, scale2 = 0.6, 0.45
                    thick1, thick2 = 2, 1

                    (t1_w, t1_h), _ = cv2.getTextSize(line1, font, scale1, thick1)
                    (t2_w, t2_h), _ = cv2.getTextSize(line2, font, scale2, thick2)
                    max_w = max(t1_w, t2_w) + 16

                    bg_x1 = max(0, x_min)
                    bg_x2 = min(w_img, bg_x1 + max_w)
                    bg_y1 = text_y1 - t1_h - 6
                    bg_y2 = text_y2 + 6

                    cv2.rectangle(annotated, (bg_x1, bg_y1), (bg_x2, bg_y2), (20, 24, 33), -1)
                    cv2.rectangle(annotated, (bg_x1, bg_y1), (bg_x2, bg_y2), (0, 255, 0), 1)

                    cv2.putText(annotated, line1, (bg_x1 + 8, text_y1), font, scale1, (0, 255, 0), thick1, cv2.LINE_AA)
                    cv2.putText(annotated, line2, (bg_x1 + 8, text_y2), font, scale2, (220, 225, 235), thick2, cv2.LINE_AA)
                except Exception:
                    pass

                self.set_last_qr_capture(annotated, qr_text)
                return qr_text

            if attempt < retries:
                time.sleep(retry_interval)

        if not last_frame_ok:
            raise RuntimeError("Camera device failed to start or produce frames")
        return None

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield MJPEG multipart stream bytes on-demand. Releases camera when stream terminates."""
        self._ensure_camera_active()
        with self.lock:
            self.active_stream_count += 1
            log.info("Client connected to video stream (active streams: %s)", self.active_stream_count)

        try:
            while True:
                with self.lock:
                    self.last_access_time = time.time()
                frame = self.read_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    time.sleep(0.05)
                    continue
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.033)
        finally:
            with self.lock:
                self.active_stream_count = max(0, self.active_stream_count - 1)
                self.last_access_time = time.time()
                log.info("Client disconnected from video stream (remaining active streams: %s)", self.active_stream_count)

    def release(self):
        """Safely stop and release camera resource."""
        self.stop_camera()


# Functional & class aliases for flexible importing
QRCamera = QRCameraManager
Camera = QRCameraManager
list_available_cameras = QRCameraManager.list_available_cameras
