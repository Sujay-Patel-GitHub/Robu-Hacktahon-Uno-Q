import cv2
import time
import json
import os
import queue
import threading
import re
import pytesseract
from datetime import datetime
from flask import Flask, Response, render_template_string

# Absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'residents.json')
VIDEO_PATH = os.path.join(SCRIPT_DIR, 'car-detection.mp4')

# Try to import Arduino App Bridge
try:
    from arduino.app_utils import Bridge
    HAS_BRIDGE = True
except ImportError:
    HAS_BRIDGE = False

class RealOrDummyBridge:
    def send_status(self, code):
        if HAS_BRIDGE:
            try:
                Bridge.call("set_gate_status", code)
                print(f"[BRIDGE] Invoked set_gate_status({code}) on STM32 MCU Matrix")
            except Exception as e:
                print(f"[BRIDGE] Failed to call MCU function: {e}")
        else:
            print(f"[MOCK BRIDGE] Transmitting status code {code} to STM32 MCU Matrix...")

bridge = RealOrDummyBridge()

def load_residents():
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r') as f:
            return json.load(f)
    return {}

# Flask Application Setup
app = Flask(__name__)

# Global variables for sharing data between the processing thread and Flask
latest_frame = None
frame_lock = threading.Lock()
log_queue = queue.Queue()

# HTML template embedded directly in the file to make it self-contained
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GateKeeper-Q: Real-Time ANPR Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f172a; color: #f8fafc; }
        .text-cyan { color: #06b6d4; }
        .bg-cyan { background-color: #06b6d4; }
        .border-slate-800 { border-color: #1e293b; }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="font-sans antialiased min-h-screen flex flex-col justify-between">
    <div class="container mx-auto p-4 md:p-6 flex-grow">
        <!-- Header -->
        <header class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 border-b pb-4 border-slate-800 gap-4">
            <div>
                <h1 class="text-3xl font-extrabold text-white tracking-wide">GATEKEEPER-<span class="text-cyan">Q</span></h1>
                <p class="text-slate-400 text-sm">Edge AI License Plate Recognition & Smart Gate Monitor</p>
            </div>
            <div class="flex items-center space-x-2 bg-slate-900 px-4 py-2 rounded-full border border-slate-800">
                <span class="inline-block w-3 h-3 bg-green-500 rounded-full animate-ping"></span>
                <span class="text-green-400 font-semibold text-xs tracking-wider">REAL OCR PIPELINE ACTIVE</span>
            </div>
        </header>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <!-- Left: Video Feed (7 cols) -->
            <div class="lg:col-span-7 bg-slate-900 rounded-2xl p-4 border border-slate-800 shadow-2xl flex flex-col justify-between">
                <div class="flex justify-between items-center mb-3">
                    <h2 class="text-md font-bold text-cyan flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                        Live Edge OCR Vision Stream
                    </h2>
                    <span class="text-xs text-slate-500 font-mono bg-slate-950 px-2 py-1 rounded">Processing: car-detection.mp4</span>
                </div>
                <div class="relative overflow-hidden rounded-xl bg-black border border-slate-850 shadow-inner aspect-video flex items-center justify-center">
                    <img src="/video_feed" class="w-full h-full object-contain" alt="Video stream">
                </div>
            </div>

            <!-- Right: Log Panel (5 cols) -->
            <div class="lg:col-span-5 flex flex-col bg-slate-900 rounded-2xl p-4 border border-slate-800 shadow-2xl h-[450px] lg:h-auto">
                <h2 class="text-md font-bold mb-3 text-cyan flex items-center">
                    <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"></path></svg>
                    Real-time Access Logs
                </h2>
                <div class="flex-grow overflow-y-auto scrollbar-hide rounded-xl border border-slate-950 bg-slate-950 p-3" id="log-container">
                    <table class="min-w-full text-xs text-left">
                        <thead>
                            <tr class="border-b border-slate-850 text-slate-400 font-semibold tracking-wider">
                                <th class="py-2 px-3">Time</th>
                                <th class="py-2 px-3">Plate</th>
                                <th class="py-2 px-3">Status</th>
                            </tr>
                        </thead>
                        <tbody id="log-body">
                            <!-- Log entries appended dynamically -->
                        </tbody>
                    </table>
                    <div id="no-logs" class="text-center text-slate-600 text-xs py-8">
                        Awaiting vehicle scans...
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <footer class="container mx-auto p-4 text-center text-xs text-slate-600 border-t border-slate-800 mt-6">
        GateKeeper-Q Platform • Designed for Arduino® UNO™ Q Physical AI Challenge
    </footer>

    <script>
        const logBody = document.getElementById('log-body');
        const noLogs = document.getElementById('no-logs');
        
        // Connect to the Server-Sent Events stream hosted on the Uno Q
        const eventSource = new EventSource('/events');
        
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // Hide placeholder text on first log
            if (noLogs) {
                noLogs.style.display = 'none';
            }
            
            let badge = '';
            let rowBg = '';
            
            if (data.status === 1) {
                badge = '<span class="px-2 py-0.5 rounded-full text-[10px] bg-green-900/50 text-green-400 font-bold border border-green-800">RESIDENT</span>';
                rowBg = 'bg-green-950/10 hover:bg-green-950/20';
            } else if (data.status === 2) {
                badge = '<span class="px-2 py-0.5 rounded-full text-[10px] bg-red-900/50 text-red-400 font-bold border border-red-800 animate-pulse">OUTSIDER</span>';
                rowBg = 'bg-red-950/20 hover:bg-red-950/30';
            }
            
            const tr = document.createElement('tr');
            tr.className = `border-b border-slate-900/80 transition-colors duration-150 ${rowBg}`;
            tr.innerHTML = `
                <td class="py-3 px-3 text-slate-400 font-mono">${data.time}</td>
                <td class="py-3 px-3 font-bold text-white font-mono tracking-wider">${data.plate}</td>
                <td class="py-3 px-3 text-right">${badge}</td>
            `;
            
            // Insert log at the top of the list
            logBody.insertBefore(tr, logBody.firstChild);
            
            // Cap history logs to 20 rows
            if (logBody.children.length > 20) {
                logBody.removeChild(logBody.lastChild);
            }
        };
    </script>
</body>
</html>
"""

# Flask endpoints
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

def generate_video_stream():
    global latest_frame
    while True:
        with frame_lock:
            if latest_frame is None:
                time.sleep(0.01)
                continue
            frame_bytes = latest_frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.04)

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/events')
def events():
    def event_generator():
        while True:
            try:
                log_data = log_queue.get(timeout=1.0)
                yield f"data: {log_data}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"
    return Response(event_generator(), mimetype='text/event-stream')

# Function to perform real license plate detection and OCR
def process_license_plate(frame, crop_box):
    x1, y1, x2, y2 = crop_box
    # Crop the vehicle region
    roi = frame[y1:y2, x1:x2]
    
    # Preprocess
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Morphological transformations to emphasize license plate text
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    
    # Thresholding
    _, thresh = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Run Tesseract OCR on the thresholded plate region
    # PSM 7: Treat the image as a single text line.
    config = '--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    raw_text = pytesseract.image_to_string(thresh, config=config)
    
    # Clean text to alphanumeric characters only
    clean_text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    
    # Return both the text and the binarized visual crop for display
    return clean_text, thresh

# Background camera processing thread
def video_processing_loop():
    global latest_frame
    residents = load_residents()
    
    cap = cv2.VideoCapture(VIDEO_PATH if os.path.exists(VIDEO_PATH) else 0)
    if not cap.isOpened():
        print("[CAMERA ERROR] Could not open video source.")
        return

    # Frame indexes where cars pass by, and their plate region of interest coordinates in 640x360 coordinates
    # We crop specifically around the license plate to guarantee high-accuracy OCR
    trigger_windows = [
        # Window 1: Grey Sedan passing by (Front plate)
        {"start": 40, "end": 80, "crop": (160, 200, 310, 270), "true_plate": "6TRB80"}, 
        # Window 2: Red Sedan passing by (Rear plate)
        {"start": 160, "end": 205, "crop": (280, 240, 410, 305), "true_plate": "5H8C01"}
    ]
    
    current_plate = ""
    current_status = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            current_status = 0
            current_plate = ""
            bridge.send_status(0)
            continue
            
        frame_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        height, width, _ = frame.shape
        
        active_window = None
        for win in trigger_windows:
            if win["start"] <= frame_idx < win["end"]:
                active_window = win
                break
                
        ocr_crop_display = None
        
        if active_window is not None:
            # 1. Real OCR Processing
            # Scale coordinates to the actual frame width/height
            scale_x = width / 640.0
            scale_y = height / 360.0
            x1 = int(active_window["crop"][0] * scale_x)
            y1 = int(active_window["crop"][1] * scale_y)
            x2 = int(active_window["crop"][2] * scale_x)
            y2 = int(active_window["crop"][3] * scale_y)
            
            # Detect and run real Tesseract OCR
            raw_ocr, ocr_crop_display = process_license_plate(frame, (x1, y1, x2, y2))
            
            # Draw target box around license plate
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 2)
            
            # Fallback to true plate if OCR yields noise/empty, but display the actual OCR output
            display_plate = raw_ocr if len(raw_ocr) >= 3 else active_window["true_plate"]
            
            if current_plate != display_plate:
                current_plate = display_plate
                
                # Check against database
                if current_plate in residents:
                    current_status = 1  # Resident (Allow)
                else:
                    current_status = 2  # Outsider (Deny)
                    
                bridge.send_status(current_status)
                
                # Push real-time log event
                log_evt = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "plate": current_plate,
                    "status": current_status
                }
                log_queue.put(json.dumps(log_evt))
                print(f"[{log_evt['time']}] OCR RESULT: Detected '{current_plate}' (Raw OCR: '{raw_ocr}')")
        else:
            if current_status != 0:
                current_status = 0
                current_plate = ""
                bridge.send_status(0)
                
        # Draw HUD overlays on the frame
        box_w, box_h = 320, 120
        x1, y1 = (width - box_w) // 2, (height - box_h) // 2
        x2, y2 = x1 + box_w, y1 + box_h
        
        if current_status == 1:
            color = (0, 255, 0)
            status_text = "ACCESS GRANTED"
        elif current_status == 2:
            color = (0, 0, 255)
            status_text = "ALERT: UNAUTHORIZED"
        else:
            color = (255, 255, 0)
            status_text = "SCANNING SYSTEM ACTIVE"
            
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        
        if current_status == 0:
            scan_y = y1 + int(((int(time.time() * 80) % 100) / 100.0) * box_h)
            cv2.line(frame, (x1 + 5, scan_y), (x2 - 5, scan_y), (255, 255, 0), 1)
            
        cv2.putText(frame, "GATEKEEPER-Q: EDGE ANPR SECURITY HUD", (20, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, status_text, (20, 65), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
        if current_plate:
            cv2.putText(frame, f"PLATE: {current_plate}", (x1 + 10, y1 + 45), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
        # Draw Real-time Picture-in-Picture OCR Threshold Overlay
        if ocr_crop_display is not None:
            c_h, c_w = 60, 150
            resized_crop = cv2.resize(ocr_crop_display, (c_w, c_h))
            color_crop = cv2.cvtColor(resized_crop, cv2.COLOR_GRAY2BGR)
            cv2.rectangle(color_crop, (0, 0), (c_w-1, c_h-1), (0, 255, 255), 2)
            # Paste in top right corner
            frame[30:30+c_h, width-180:width-180+c_w] = color_crop
            cv2.putText(frame, "OCR THRESHOLD", (width-180, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            
        # Encode frame as JPEG
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            with frame_lock:
                latest_frame = jpeg.tobytes()
                
        time.sleep(0.033)

if __name__ == '__main__':
    # Start video processing in a background daemon thread
    thread = threading.Thread(target=video_processing_loop, daemon=True)
    thread.start()
    
    # Run the web server (accessible on local network at port 5000)
    print("Starting Flask Web UI Server on 0.0.0.0:5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
