import cv2
import time
import json
import os
import queue
import threading
from datetime import datetime
from flask import Flask, Response, render_template_string

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_NAME = 'Lighting Human Detection Video.mp4'
VIDEO_PATH = os.path.join(SCRIPT_DIR, VIDEO_NAME)

try:
    from arduino.app_utils import Bridge
    HAS_BRIDGE = True
except ImportError:
    HAS_BRIDGE = False

class RealOrDummyBridge:
    def trigger_zone(self, zone_id):
        # zone_id: 1, 2, 3, 4 (0 = clear/idle)
        if HAS_BRIDGE:
            try:
                Bridge.call("trigger_zone", zone_id)
                print(f"[BRIDGE] Invoked trigger_zone({zone_id}) on STM32 MCU")
            except Exception as e:
                print(f"[BRIDGE] Failed to call MCU function: {e}")
        else:
            print(f"[MOCK BRIDGE] Transmitting active zone {zone_id} to STM32 MCU Matrix...")

bridge = RealOrDummyBridge()

app = Flask(__name__)

latest_frame = None
frame_lock = threading.Lock()
log_queue = queue.Queue()

# HTML dashboard representing the Kataria Arcade Smart Lighting SCADA Panel
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kataria Arcade: Edge AI Smart Lighting Monitor</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f172a; color: #f8fafc; }
        .text-cyan { color: #06b6d4; }
        .bg-cyan { background-color: #06b6d4; }
        .border-slate-800 { border-color: #1e293b; }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
        .zone-box { transition: all 0.3s ease; }
    </style>
</head>
<body class="font-sans antialiased min-h-screen flex flex-col justify-between">
    <div class="container mx-auto p-4 md:p-6 flex-grow">
        <!-- Header -->
        <header class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 border-b pb-4 border-slate-800 gap-4">
            <div>
                <h1 class="text-3xl font-extrabold text-white tracking-wide">KATARIA ARCADE <span class="text-cyan">SMART LIGHTS</span></h1>
                <p class="text-slate-400 text-sm">Kataria Arcade 10th Floor — Sandhi Cement Interactive Installation (Uno Q Upgrade)</p>
            </div>
            <div class="flex items-center space-x-2 bg-slate-900 px-4 py-2 rounded-full border border-slate-800">
                <span class="inline-block w-3 h-3 bg-cyan rounded-full animate-pulse"></span>
                <span class="text-cyan font-semibold text-xs tracking-wider">EDGE AI CONTROLLER ONLINE</span>
            </div>
        </header>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <!-- Left: Video Stream (6 cols) -->
            <div class="lg:col-span-6 bg-slate-900 rounded-2xl p-4 border border-slate-800 shadow-2xl flex flex-col justify-between">
                <div class="flex justify-between items-center mb-3">
                    <h2 class="text-md font-bold text-cyan flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                        Space Occupancy Tracking (Qualcomm MPU)
                    </h2>
                    <span class="text-xs text-slate-500 font-mono bg-slate-950 px-2 py-1 rounded">Source: Video feed</span>
                </div>
                <div class="relative overflow-hidden rounded-xl bg-black border border-slate-850 shadow-inner aspect-video flex items-center justify-center">
                    <img src="/video_feed" class="w-full h-full object-contain" alt="Video stream">
                </div>
            </div>

            <!-- Right: Map and Relays (6 cols) -->
            <div class="lg:col-span-6 flex flex-col gap-6">
                <!-- Interactive Floor Map -->
                <div class="bg-slate-900 rounded-2xl p-4 border border-slate-800 shadow-2xl">
                    <h2 class="text-md font-bold mb-4 text-cyan flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"></path></svg>
                        Art Piece Installation Layout (Kataria Arcade Room)
                    </h2>
                    <div class="grid grid-cols-4 gap-3 text-center">
                        <div id="zone-1" class="zone-box bg-slate-950 border border-slate-800 p-4 rounded-xl">
                            <span class="block text-xs text-slate-400 font-semibold mb-1">ZONE 1</span>
                            <span class="text-sm font-bold text-slate-600" id="zone-1-lbl">OFF</span>
                            <span class="block text-[10px] text-slate-500 mt-2">Relays 9 & 10</span>
                        </div>
                        <div id="zone-2" class="zone-box bg-slate-950 border border-slate-800 p-4 rounded-xl">
                            <span class="block text-xs text-slate-400 font-semibold mb-1">ZONE 2</span>
                            <span class="text-sm font-bold text-slate-600" id="zone-2-lbl">OFF</span>
                            <span class="block text-[10px] text-slate-500 mt-2">Relays 7 & 3</span>
                        </div>
                        <div id="zone-3" class="zone-box bg-slate-950 border border-slate-800 p-4 rounded-xl">
                            <span class="block text-xs text-slate-400 font-semibold mb-1">ZONE 3</span>
                            <span class="text-sm font-bold text-slate-600" id="zone-3-lbl">OFF</span>
                            <span class="block text-[10px] text-slate-500 mt-2">Relays 12 & 5</span>
                        </div>
                        <div id="zone-4" class="zone-box bg-slate-950 border border-slate-800 p-4 rounded-xl">
                            <span class="block text-xs text-slate-400 font-semibold mb-1">ZONE 4</span>
                            <span class="text-sm font-bold text-slate-600" id="zone-4-lbl">OFF</span>
                            <span class="block text-[10px] text-slate-500 mt-2">Relay 13</span>
                        </div>
                    </div>
                </div>

                <!-- Event Log & Relay States -->
                <div class="bg-slate-900 rounded-2xl p-4 border border-slate-800 shadow-2xl flex-grow h-[220px] flex flex-col">
                    <h2 class="text-md font-bold mb-3 text-cyan flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        Relay State Transitions & Logs
                    </h2>
                    <div class="flex-grow overflow-y-auto scrollbar-hide rounded-xl border border-slate-950 bg-slate-950 p-3" id="log-container">
                        <div id="log-body" class="space-y-2 font-mono text-[11px] text-slate-300">
                            <!-- Log rows appended dynamically -->
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <footer class="container mx-auto p-4 text-center text-xs text-slate-600 border-t border-slate-800 mt-6">
        Kataria Arcade Smart Lighting Control System • Powered by Arduino® UNO™ Q
    </footer>

    <script>
        const logBody = document.getElementById('log-body');
        const logContainer = document.getElementById('log-container');
        
        // Listen to Server-Sent Events from Flask
        const eventSource = new EventSource('/events');
        
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // 1. Reset all zone UI states
            for (let i = 1; i <= 4; i++) {
                const box = document.getElementById(`zone-${i}`);
                const lbl = document.getElementById(`zone-${i}-lbl`);
                box.className = 'zone-box bg-slate-950 border border-slate-800 p-4 rounded-xl';
                lbl.className = 'text-sm font-bold text-slate-600';
                lbl.innerText = 'OFF';
            }
            
            // 2. Highlight active zone
            if (data.zone > 0) {
                const activeBox = document.getElementById(`zone-${data.zone}`);
                const activeLbl = document.getElementById(`zone-${data.zone}-lbl`);
                activeBox.className = 'zone-box bg-cyan/10 border-cyan p-4 rounded-xl border shadow-lg';
                activeLbl.className = 'text-sm font-bold text-cyan';
                activeLbl.innerText = 'ACTIVE';
            }
            
            // 3. Append to log
            const div = document.createElement('div');
            div.className = 'border-l-2 pl-2 ' + (data.zone > 0 ? 'border-cyan text-cyan bg-cyan/5 py-1' : 'border-slate-800 text-slate-500');
            div.innerHTML = `[${data.time}] ${data.log}`;
            logBody.insertBefore(div, logBody.firstChild);
            
            // Cap log lines to 15
            if (logBody.children.length > 15) {
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

# Background camera/video processing thread
def video_processing_loop():
    global latest_frame
    
    cap = cv2.VideoCapture(VIDEO_PATH if os.path.exists(VIDEO_PATH) else 0)
    if not cap.isOpened():
        print("[CAMERA ERROR] Could not open video source.")
        return

    # Let's perform simple movement tracking using background subtraction
    backSub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16, detectShadows=True)
    
    current_zone = 0
    last_zone_trigger = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            current_zone = 0
            bridge.trigger_zone(0)
            continue
            
        height, width, _ = frame.shape
        
        # Apply background subtraction to find moving people
        fgMask = backSub.apply(frame)
        # Threshold mask
        _, thresh = cv2.threshold(fgMask, 200, 255, cv2.THRESH_BINARY)
        
        # Find contours of moving objects
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        active_centroid_x = -1
        largest_contour_area = 0
        target_box = None
        
        for c in contours:
            area = cv2.contourArea(c)
            # Filter small noises
            if area > 1000:
                if area > largest_contour_area:
                    largest_contour_area = area
                    (x, y, w, h) = cv2.boundingRect(c)
                    target_box = (x, y, w, h)
                    active_centroid_x = x + w // 2
                    
        # Divide frame horizontally into 4 zones representing the installation room layout
        zone_width = width // 4
        detected_zone = 0
        
        if active_centroid_x != -1:
            # Map centroid X coordinate to Zone 1, 2, 3, or 4
            detected_zone = int(active_centroid_x // zone_width) + 1
            detected_zone = min(max(detected_zone, 1), 4) # constrain between 1 and 4
            
            # Draw bounding box around the detected moving person
            x, y, w, h = target_box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            cv2.putText(frame, f"Tracking: Zone {detected_zone}", (x, y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
        # Send status update if zone changes
        if detected_zone != current_zone:
            current_zone = detected_zone
            last_zone_trigger = time.time()
            bridge.trigger_zone(current_zone)
            
            # Format and queue log messages
            log_msg = ""
            if current_zone == 1:
                log_msg = "Person in Zone 1: Activating Relays 9 & 10."
            elif current_zone == 2:
                log_msg = "Person in Zone 2: Activating Relays 7 & 3."
            elif current_zone == 3:
                log_msg = "Person in Zone 3: Activating Relays 12 & 5."
            elif current_zone == 4:
                log_msg = "Person in Zone 4: Activating Relay 13."
            else:
                log_msg = "Area cleared. Initiating idle sweep animation."
                
            log_evt = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "zone": current_zone,
                "log": log_msg
            }
            log_queue.put(json.dumps(log_evt))
            print(f"[{log_evt['time']}] {log_msg}")
            
        # Draw zone separators on frame
        for i in range(1, 4):
            cv2.line(frame, (i * zone_width, 0), (i * zone_width, height), (150, 150, 150), 1)
            cv2.putText(frame, f"ZONE {i}", (i * zone_width - 80, height - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.putText(frame, "ZONE 4", (width - 80, height - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                    
        # General HUD text
        cv2.putText(frame, "SANDHI CEMENT: KATARIA ARCADE MONITOR", (20, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                    
        # Encode frame as JPEG
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            with frame_lock:
                latest_frame = jpeg.tobytes()
                
        time.sleep(0.04) # cap loop at 25 FPS to match video rate

if __name__ == '__main__':
    # Start video processing in background thread
    thread = threading.Thread(target=video_processing_loop, daemon=True)
    thread.start()
    
    # Run the web server
    print("Starting Sandhi Cement Monitor Web Server on 0.0.0.0:5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
