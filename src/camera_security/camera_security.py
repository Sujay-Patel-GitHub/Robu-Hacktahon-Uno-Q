import cv2
import time
import sys

# Simple simulation of RouterBridge communication
# If running on the UNO Q board, you can use the RouterBridge library to talk to the STM32
class DummyBridge:
    def send_zone(self, zone_id):
        print(f"[BRIDGE] Active Zone: {zone_id} (1=Left, 2=Center, 3=Right)")

bridge = DummyBridge()

def main():
    print("Initializing Edge-AI Camera Security & Zone Lighting System...")
    
    # Open the USB camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open USB camera. Make sure a webcam is plugged in.")
        sys.exit(1)
        
    # Load default Haar Cascade for Face Detection
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    print("Camera running. Detecting people/faces and mapping to physical zones...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to read frame from camera.")
            break
            
        height, width, _ = frame.shape
        # Divide frame horizontally into 3 zones
        zone_width = width // 3
        
        # Convert to grayscale for detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        active_zone = 0  # 0 = No one detected
        
        if len(faces) > 0:
            # Get center of the largest detected face
            largest_face = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = largest_face
            face_center_x = x + w // 2
            
            # Determine which zone the face is in
            if face_center_x < zone_width:
                active_zone = 1  # Left Zone
            elif face_center_x < 2 * zone_width:
                active_zone = 2  # Center Zone
            else:
                active_zone = 3  # Right Zone
                
            # Draw bounding box and zone info on screen
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, f"Zone {active_zone} Active", (x, y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
        # Send active zone to the STM32 MCU via bridge
        bridge.send_zone(active_zone)
        
        # Draw zone boundaries on frame
        cv2.line(frame, (zone_width, 0), (zone_width, height), (255, 255, 255), 1)
        cv2.line(frame, (2 * zone_width, 0), (2 * zone_width, height), (255, 255, 255), 1)
        
        # Label zones
        cv2.putText(frame, "ZONE 1 (LEFT)", (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "ZONE 2 (CENTER)", (zone_width + 10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "ZONE 3 (RIGHT)", (2 * zone_width + 10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Display the frame (Optional - comment out in headless production)
        # cv2.imshow('Smart Zone Detection', frame)
        
        time.sleep(0.1) # 10 FPS is plenty for presence detection
        
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
