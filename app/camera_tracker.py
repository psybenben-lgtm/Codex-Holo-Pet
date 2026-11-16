# -*- coding: utf-8 -*-
"""
本地 Python 摄像头手部挥拍辅助动捕模块 (app/camera_tracker.py)
作为浏览器 WebRTC 摄像头动捕的原生双保险补充：
当用户运行脚本或勾选本地 OpenCV 动捕时，直接读取电脑摄像头计算手部运动重心与平滑位移速度，
上报至 /api/badminton/camera_frame。默认绝不保存任何视频文件或上传网络。
"""
import json
import math
import time
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from local_runtime import get_local_host_url, get_no_proxy_opener

HTTP = get_no_proxy_opener()
HOST = get_local_host_url()


def run_opencv_hand_tracker(camera_index=0, stop_event=None):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False, "当前 Python 环境未安装 opencv-python，请直接使用导演控制台内置的浏览器摄像头动捕（无需安装任何额外库）"

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return False, f"无法打开摄像头 #{camera_index}，请检查摄像头是否被占用或权限是否开启"

    prev_gray = None
    smooth_speed = 0.0
    hand_x, hand_y = 0.5, 0.5

    try:
        while not (stop_event and stop_event.is_set()):
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            frame = cv2.flip(frame, 1)
            small = cv2.resize(frame, (160, 120))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (7, 7), 0)

            hand_detected = False
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                _, thresh = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
                active_pixels = int(np.count_nonzero(thresh))
                if active_pixels > 45:
                    hand_detected = True
                    ys, xs = np.nonzero(thresh)
                    cx = float(np.mean(xs)) / 160.0
                    cy = float(np.mean(ys)) / 120.0
                    inst_speed = math.hypot(cx - hand_x, cy - hand_y) * 180.0 + (active_pixels / 95.0)
                    smooth_speed = smooth_speed * 0.45 + inst_speed * 0.55
                    hand_x, hand_y = cx, cy
                else:
                    smooth_speed *= 0.6
                    hand_detected = smooth_speed > 3.5

            prev_gray = gray
            payload = {
                "hand_detected": hand_detected,
                "x": round(hand_x, 3),
                "y": round(hand_y, 3),
                "speed": round(smooth_speed, 2),
                "source": "python_opencv"
            }
            try:
                req = Request(
                    f"{HOST}/api/badminton/camera_frame",
                    json.dumps(payload).encode("utf-8"),
                    {"Content-Type": "application/json"}
                )
                with HTTP.open(req, timeout=0.25) as resp:
                    resp.read()
            except Exception:
                pass
            time.sleep(0.03)
    finally:
        cap.release()
    return True, "摄像头动捕已正常结束"


if __name__ == '__main__':
    ok, msg = run_opencv_hand_tracker(0)
    print(msg)
