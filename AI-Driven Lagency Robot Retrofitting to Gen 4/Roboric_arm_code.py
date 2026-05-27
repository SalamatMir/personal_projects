import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import time
import json
import numpy as np
from scipy.interpolate import griddata
from typing import Dict, Tuple, Optional, List
import threading
import cv2
from ultralytics import YOLO
from queue import Queue
import os
from pupil_apriltags import Detector

# ====== CONFIG ======
MOTOR_RANGES: Dict[str, Tuple[int, int]] = {
    'base': (568, 17900),
    'arm1': (4700, 26220),
    'arm2': (1000, 17295),
    'gripper1': (0, 26500),
    'gripper2': (0, 26500),
    'clipper': (2000, 26000),  # Updated for clipper feedback
}
MOTOR_PINS: Dict[str, Tuple[int, int]] = {
    'base': (20, 19),
    'arm1': (16, 13),
    'arm2': (21, 26),
    'gripper1': (1, 0),
    'gripper2': (8, 7),
    'clipper': (5, 12),
    # 'left': (11, 9),
    
    #'right' : (25, 10),
}
CLIPPER_ANGLES: Dict[str, float] = {
    'open': 60.0,
    'close': 170.0,
}
START_POSITION: Dict[str, float] = {
    'arm1': 235.7,
    'arm2': 120.7,
    'base': 180.6,
    'gripper1': 159,
    'gripper2': 25,
    'clipper': CLIPPER_ANGLES['open'],  # Start with clipper open
}
cl1 = 118
cl2 = 51
PICKING_POSITIONS: List[Dict[str, float]] = [
    {'base': 174.6, 'arm1': 273.1, 'arm2': 94.7, 'gripper1': 143.08, 'gripper2': 45.8, 'clipper': CLIPPER_ANGLES['close']},
    {'base': 174.1, 'arm1': 283.8, 'arm2': 96.4, 'gripper1': 132.8, 'gripper2': 55.2, 'clipper': CLIPPER_ANGLES['close']},
    {'base': 174.8, 'arm1': 293.6, 'arm2': 104.1, 'gripper1': 132.9, 'gripper2': 55.8, 'clipper': CLIPPER_ANGLES['close']},
    {'base': 174.6, 'arm1': 307.6, 'arm2': 114.1, 'gripper1': 132.8, 'gripper2': 55.4, 'clipper': CLIPPER_ANGLES['close']},
]
GRIPPER_PICK_CONFIGURATIONS: Dict[str, Dict[str, float]] = {
    'default': {
        'gripper1': cl1,

'gripper2': cl2,
        'clipper': CLIPPER_ANGLES['close'],
    },
    'small_object': {
        'gripper1': cl1,
        'gripper2': cl2,
        'clipper': CLIPPER_ANGLES['close'],
    },
    'large_object': {
        'gripper1': cl1,
        'gripper2': cl2,
        'clipper': CLIPPER_ANGLES['close'],
    },
    'vertical': {
        'gripper1': cl1,
        'gripper2': cl2,
        'clipper': CLIPPER_ANGLES['close'],
    },
    '45_to_vertical': {
        'gripper1': cl1,
        'gripper2': cl2,
        'clipper': CLIPPER_ANGLES['close'],
    },
    'horizontal': {
        'gripper1': cl1,
        'gripper2': cl2,
        'clipper': CLIPPER_ANGLES['close'],
    }
}
DUSTBINS: Dict[int, Dict[str, float]] = {
    1: {'arm1': 85.7, 'arm2': 286.6, 'base': 103.8, 'gripper1': 177.0, 'gripper2': 10, 'clipper': CLIPPER_ANGLES['open']},
    2: {'arm1': 98.0, 'arm2': 286.5, 'base': 157.6, 'gripper1': 177.0, 'gripper2': 10.0, 'clipper': CLIPPER_ANGLES['open']},
    3: {'arm1': 98.7, 'arm2': 286.9, 'base': 198.7, 'gripper1': 177.0, 'gripper2': 10.0, 'clipper': CLIPPER_ANGLES['open']},
    4: {'arm1': 85.7, 'arm2': 286.9, 'base': 250.7, 'gripper1': 177.0, 'gripper2': 10.0, 'clipper': CLIPPER_ANGLES['open']},
}
CLASS_TO_DUSTBIN_MAP: Dict[int, int] = {
    0: 1, 1: 2, 2: 3, 3: 4,
}
IGNORED_CLASS_IDS = {4}  # Set of class IDs to ignore (e.g., class ID 4 for the new environment class)
ANGLE_TOLERANCE: float = 3.0
REVERSE_ANGLES = ['gripper2']
DIRECTION_REVERSE = ['gripper2']
USE_DIFFERENTIAL_GRIPPER = True
YOLO_MODEL_PATH = '/home/salamat/Downloads/best (11) (1).pt'
PIXEL_MAP_PATH = '/home/salamat/pixel_map_1.json'
DISPLAY_WEBCAM = True
CAMERA_RESOLUTION = (640, 480)
FRAME_RATE = 15
ROI_X = 0
ROI_Y = 140
ROI_WIDTH = 130
ROI_HEIGHT = 340

IMGSZ = int(os.getenv("IMGSZ", "640"))
CONF_THRESHOLD = float(os.getenv("CONF", "0.70"))
IOU = float(os.getenv("IOU", "0.50"))
MAX_DET = int(os.getenv("MAX_DET", "15"))
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "1"))

# ====== GLOBALS ======
adc_lock = threading.Lock()
vision_lock = threading.Lock()
model = None
cap = None
pixel_map_data = None
bin_queue = Queue()
detection_queue = Queue()
vision_thread_running = False
camera_active = threading.Event()
ADC_CHANNELS = {}
apriltag_detector = None

# ====== COORDINATE MAPPING SYSTEM ======
def load_pixel_map() -> bool:
    global pixel_map_data
    try:
        if not os.path.exists(PIXEL_MAP_PATH):
            print(f"⚠️ Pixel map file not found at {PIXEL_MAP_PATH}, using fallback mode")
            return False
        with open(PIXEL_MAP_PATH, 'r') as f:
            pixel_map_data = json.load(f)
        print(f"✅ Loaded {len(pixel_map_data)} coordinate mappings from pixel map")
        coords = list(pixel_map_data.keys())
        print(f"📍 Available coordinates: {coords[0]} to {coords[-1]}")
        return True
    except Exception as e:
        print(f"❌ Failed to load pixel map: {e}")
        return False

def parse_pixel_coordinates():
    if not pixel_map_data:
        return None
    pixels_x = []
    pixels_y = []
    base_angles = []
    arm1_angles = []
    arm2_angles = []
    for coord_str, angles in pixel_map_data.items():
        coord_str = coord_str.strip("()")
        x, y = map(int, coord_str.split(","))
        pixels_x.append(x * 40)
        pixels_y.append(y * 40)
        base_angles.append(angles['base'])
        arm1_angles.append(angles['arm1'])
        arm2_angles.append(angles['arm2'])
    return (np.array(pixels_x), np.array(pixels_y), 
            np.array(base_angles), np.array(arm1_angles), np.array(arm2_angles))

def pixel_to_robot_coords(pixel_x: int, pixel_y: int, pick_config: str = 'default', tag_center: Optional[Tuple[int, int]] = (0, 0)) -> Optional[Dict[str, float]]:
    if not pixel_map_data:
        print("⚠️ Pixel map not loaded, using fallback picking position")
        fallback = PICKING_POSITIONS[0].copy()
        fallback.update(GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default']))
        return fallback
    
    try:
        origin_x, origin_y = tag_center
        print(f"🎯 Using fixed AprilTag at ({origin_x}, {origin_y}) as grid origin")
        
        grid_width = ROI_WIDTH
        grid_height = ROI_HEIGHT / 5  # 1x5 grid
        rel_x = pixel_x - origin_x
        rel_y = pixel_y - origin_y
        if not (0 <= rel_x < ROI_WIDTH and 0 <= rel_y < ROI_HEIGHT):
            print(f"⚠️ Pixel ({pixel_x}, {pixel_y}) outside grid bounds, using fallback")
            fallback = PICKING_POSITIONS[0].copy()
            fallback.update(GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default']))
            return fallback
        
        col = 0  # Single column
        row = int(rel_y / grid_height)
        grid_key = f"({row+1},{col+1})"
        print(f"🎯 Mapped pixel ({pixel_x}, {pixel_y}) to grid cell {grid_key}")
        
        if grid_key in pixel_map_data:
            robot_position = pixel_map_data[grid_key].copy()
            gripper_config = GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default'])
            robot_position.update(gripper_config)
            print(f"🤖 Direct pixel map position: Base={robot_position['base']:.1f}°, "
                  f"Arm1={robot_position['arm1']:.1f}°, Arm2={robot_position['arm2']:.1f}°")
            print(f"🤏 Gripper config ({pick_config}): "
                  f"Gripper1={robot_position['gripper1']:.1f}°, Gripper2={robot_position['gripper2']:.1f}°, "
                  f"Clipper={robot_position['clipper']:.1f}°")
            return robot_position
        
        print(f"⚠️ Grid cell {grid_key} not in pixel map, using predefined picking position")
        row = min(row, 4)  # Ensure row is within 0-4
        robot_position = PICKING_POSITIONS[row].copy()
        gripper_config = GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default'])
        robot_position.update(gripper_config)
        
        print(f"🤖 Using predefined position for row {row+1}: Base={robot_position['base']:.1f}°, "
              f"Arm1={robot_position['arm1']:.1f}°, Arm2={robot_position['arm2']:.1f}°")
        print(f"🤏 Gripper config ({pick_config}): "
              f"Gripper1={robot_position['gripper1']:.1f}°, Gripper2={robot_position['gripper2']:.1f}°, "
              f"Clipper={robot_position['clipper']:.1f}°")
        
        return robot_position
    except Exception as e:
        print(f"❌ Error in coordinate transformation: {e}, using fallback")
        fallback = PICKING_POSITIONS[0].copy()
        fallback.update(GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default']))
        return fallback

# ====== DIAGNOSTIC FUNCTION ======
def diagnose_adc() -> None:
    print("Diagnosing ADC channels...")
    with adc_lock:
        for motor, channel in ADC_CHANNELS.items():
            try:
                value = channel.value
                angle = map_to_degrees(value, *MOTOR_RANGES.get(motor, (0, 65535)))
                print(f"{motor}: Raw ADC = {value}, Angle = {angle:.1f}°")
            except Exception as e:
                print(f"Error reading {motor}: {e}")
    time.sleep(0.5)

# ====== INIT ======
def initialize_hardware() -> None:
    global ADC_CHANNELS, USE_DIFFERENTIAL_GRIPPER
    try:
        print("Initializing GPIO...")
        GPIO.setmode(GPIO.BCM)
        for pin_pair in MOTOR_PINS.values():
            for pin in pin_pair:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
        print("GPIO initialized successfully")
        
        print("Initializing I2C and ADC...")
        i2c = busio.I2C(board.SCL, board.SDA)
        
        try:
            ads1 = ADS.ADS1115(i2c)
            ADC_CHANNELS.update({
                'arm2': AnalogIn(ads1, ADS.P0),
                'base': AnalogIn(ads1, ADS.P1),
                'arm1': AnalogIn(ads1, ADS.P2),
                'clipper': AnalogIn(ads1, ADS.P3),  # Added clipper to ADC channels
            })
            print("First ADS1115 (0x48) initialized successfully")
        except Exception as e:
            print(f"Failed to initialize first ADS1115 (0x48): {e}")
            raise
        
        try:
            ads2 = ADS.ADS1115(i2c, address=0x4A)
            ADC_CHANNELS.update({
                'gripper1': AnalogIn(ads2, ADS.P1),
                'gripper2': AnalogIn(ads2, ADS.P0)
            })
            print("Second ADS1115 (0x4A) initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize second ADS1115 (0x4A): {e}")
            print("Falling back to clipper-only mode (differential gripper disabled)")
            USE_DIFFERENTIAL_GRIPPER = False
        
        diagnose_adc()
    except Exception as e:
        print(f"Hardware initialization failed: {e}")
        raise

def initialize_vision() -> None:
    global model, cap, vision_thread_running, apriltag_detector
    try:
        print("Initializing YOLO model...")
        model = YOLO(YOLO_MODEL_PATH)
        print("YOLO model loaded successfully")
        print(f"📋 Classes: {model.names}")
        
        print("Initializing AprilTag detector...")
        try:
            apriltag_detector = Detector(families="tag36h11")
            print("AprilTag detector initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize AprilTag detector: {e}")
            print("Falling back to default ROI origin")
            apriltag_detector = None
        
        print("Initializing webcam...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise Exception("Failed to open webcam")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
        cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)
        print("Webcam initialized successfully")
        
        load_pixel_map()
        
        vision_thread_running = True
        vision_thread = threading.Thread(target=vision_loop, daemon=True)
        vision_thread.start()
        print("Vision thread started")
    except Exception as e:
        print(f"Vision initialization failed: {e}")
        raise

def detect_boundary(frame):
    x = 200
    y = 80
    w = 240
    h = 360
    return x, y, w, h

def vision_loop() -> None:
    global vision_thread_running
    frame_count = 0
    while vision_thread_running:
        camera_active.wait()
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to capture image from webcam")
            time.sleep(0.1)
            continue

        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            if DISPLAY_WEBCAM:
                annotated_frame = frame.copy()
                draw_grid(annotated_frame, None, None)
                cv2.rectangle(annotated_frame, (ROI_X, ROI_Y), (ROI_X + ROI_WIDTH, ROI_Y + ROI_HEIGHT), (255, 0, 0), 2)
                cv2.imshow("YOLO Detection", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            continue

        dynamic_roi = detect_boundary(frame)
        if dynamic_roi:
            roi_x, roi_y, roi_width, roi_height = dynamic_roi
            print("✅ Dynamic boundary detected")
        else:
            roi_x, roi_y, roi_width, roi_height = ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT
            print("⚠️ Using fixed ROI")

        tag_center = (0, 0)  # Fixed AprilTag center
        print(f"🏷️ Using fixed AprilTag at ({tag_center[0]}, {tag_center[1]})")
        if apriltag_detector is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            tags = apriltag_detector.detect(gray)
            for tag in tags:
                if tag.tag_family.decode('utf-8') == 'tag36h11':
                    tag_center = (int(tag.center[0]), int(tag.center[1]))
                    print(f"🏷️ AprilTag detected at ({tag_center[0]}, {tag_center[1]})")
                    corners = tag.corners.astype(int)
                    cv2.polylines(frame, [corners], True, (0, 255, 255), 2)
                    cv2.circle(frame, tag_center, 5, (0, 255, 255), -1)
                    cv2.putText(frame, "AprilTag (0,0)", (tag_center[0], tag_center[1] - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                    break

        roi_frame = frame[roi_y:roi_y + roi_height, roi_x:roi_x + roi_width]
        results = model(roi_frame, imgsz=IMGSZ, conf=CONF_THRESHOLD, iou=IOU, max_det=MAX_DET, verbose=False)[0]
        
        detections = []
        if results.boxes is not None:
            for box in results.boxes:
                x1_roi, y1_roi, x2_roi, y2_roi = map(int, box.xyxy[0])
                confidence = box.conf.item()
                class_id = int(box.cls.item())
                class_name = model.names[class_id]
                
                # Skip ignored class
                if class_id in IGNORED_CLASS_IDS:
                    print(f"🚫 Ignoring detection: {class_name} (ID: {class_id}) at pixel ({(x1_roi + x2_roi) // 2 + roi_x}, {(y1_roi + y2_roi) // 2 + roi_y})")
                    continue
                
                bbox_center_x = (x1_roi + x2_roi) // 2 + roi_x
                bbox_center_y = (y1_roi + y2_roi) // 2 + roi_y
                
                object_roi = roi_frame[y1_roi:y2_roi, x1_roi:x2_roi]
                orientation = detect_object_orientation(object_roi)
                
                detection = YOLODetection(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                    bbox_center_x=bbox_center_x,
                    bbox_center_y=bbox_center_y,
                    bbox=(x1_roi + roi_x, y1_roi + roi_y, x2_roi + roi_x, y2_roi + roi_y),
                    orientation=orientation,
                    tag_center=tag_center
                )
                
                detections.append(detection)
                print(f"🎯 {class_name} detected at pixel ({bbox_center_x}, {bbox_center_y}) "
                      f"with confidence {confidence:.2f}, orientation: {orientation}")
                if detection.robot_position:
                    print(f"   Robot position: {detection.robot_position}")
                    print(f"   Safe: {detection.is_safe}, Pickable: {detection.is_pickable}")
        
        if DISPLAY_WEBCAM:
            annotated_frame = frame.copy()
            cv2.rectangle(annotated_frame, (roi_x, roi_y), (roi_x + roi_width, roi_y + roi_height), (255, 0, 0), 2)
            
            best_detection = None
            if detections:
                pickable_detections = [d for d in detections if d.is_pickable]
                if pickable_detections:
                    best_detection = max(pickable_detections, key=lambda d: d.confidence)
            draw_grid(annotated_frame, best_detection, tag_center)
            
            for detection in detections:
                x1, y1, x2, y2 = detection.bbox
                color = (0, 255, 0) if detection.is_pickable else (0, 255, 255) if detection.dustbin_number else (0, 0, 255)
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                cv2.circle(annotated_frame, (detection.bbox_center_x, detection.bbox_center_y), 5, color, -1)
                label = f"{detection.class_name} {detection.confidence:.2f} ({detection.bbox_center_x},{detection.bbox_center_y})"
                if detection.dustbin_number:
                    label += f" -> Bin{detection.dustbin_number} ({detection.orientation})"
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                cv2.rectangle(annotated_frame, (x1, y1 - h - 5), (x1 + w, y1), color, -1)
                cv2.putText(annotated_frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            
            cv2.imshow("YOLO Detection with AprilTag", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        with vision_lock:
            pickable_detections = [d for d in detections if d.is_pickable]
            if pickable_detections:
                best_detection = max(pickable_detections, key=lambda d: d.confidence)
                detection_queue.put(best_detection)
                bin_queue.put(best_detection.dustbin_number)
                print(f"✅ Queued best detection: {best_detection.class_name} for Dustbin {best_detection.dustbin_number}")
            elif detections:
                valid_detections = [d for d in detections if d.dustbin_number is not None]
                if valid_detections:
                    best_detection = max(valid_detections, key=lambda d: d.confidence)
                    print(f"⚠️ Using unsafe detection: {best_detection.class_name} for Dustbin {best_detection.dustbin_number}")
                    bin_queue.put(best_detection.dustbin_number)
            else:
                print(f"❌ No valid objects detected within ROI; queue unchanged")
        
        time.sleep(1.0 / FRAME_RATE)

def draw_grid(frame, detection: Optional['YOLODetection'], tag_center: Optional[Tuple[int, int]]):
    if tag_center:
        x, y = tag_center
        origin_x, origin_y = x+1, y+1
    else:
        origin_x, origin_y = ROI_X+1, ROI_Y+1
    
    grid_width = ROI_WIDTH
    grid_height = ROI_HEIGHT / 4  # 1x5 grid
    
    for i in range(1, 4):
        y = int(origin_y + i * grid_height)
        cv2.line(frame, (origin_x, y), (origin_x + ROI_WIDTH, y), (128, 128, 128), 1)
    
    if detection:
        rel_x = detection.bbox_center_x - origin_x
        rel_y = detection.bbox_center_y - origin_y
        if 0 <= rel_x < ROI_WIDTH and 0 <= rel_y < ROI_HEIGHT:
            row = int(rel_y / grid_height)
            top_left_x = int(origin_x)
            top_left_y = int(origin_y + row * grid_height)
            bottom_right_x = int(top_left_x + grid_width)
            bottom_right_y = int(top_left_y + grid_height)
            color = (0, 255, 0) if detection.is_pickable else (0, 0, 255)
            cv2.rectangle(frame, (top_left_x, top_left_y), (bottom_right_x, bottom_right_y), color, 2)
            label = f"({row+1},1)"
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(frame, (top_left_x, top_left_y - h - 5), (top_left_x + w, top_left_y), color, -1)
            cv2.putText(frame, label, (top_left_x, top_left_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

def detect_object_orientation(object_roi):
    if object_roi.size == 0:
        return 'default'
    
    gray = cv2.cvtColor(object_roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 'default'
    
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 100:
        return 'default'
    
    rect = cv2.minAreaRect(contour)
    angle = rect[2]
    
    if -10 <= angle <= 10 or 80 <= abs(angle) <= 100:
        return 'vertical'
    elif 35 <= abs(angle) <= 55:
        return '45_to_vertical'
    elif -35 <= angle <= 35:
        return 'horizontal'
    elif 125 <= abs(angle) <= 145:
        return '45_to_horizontal'
    else:
        return 'default'

# ====== MOTOR CONTROL FUNCTIONS ======
def map_to_degrees(value: int, min_val: int, max_val: int) -> float:
    if min_val == 2000 and max_val == 17000:  # Clipper-specific mapping
        return 23 + (max(min_val, min(value, max_val)) - min_val) * (200 - 23) / (max_val - min_val)
    return (max(min_val, min(value, max_val)) - min_val) * 360 / (max_val - min_val)

def get_degrees(motor: str) -> float:
    if motor not in ADC_CHANNELS:
        print(f"Warning: No ADC channel for {motor}")
        return 0.0
    with adc_lock:
        try:
            value = ADC_CHANNELS[motor].value
        except Exception as e:
            print(f"Error reading ADC for {motor}: {e}")
            return 0.0
    angle = map_to_degrees(value, *MOTOR_RANGES.get(motor, (0, 65535)))
    if motor in REVERSE_ANGLES:
        angle = 360 - angle
    return angle

def set_motor(motor: str, direction: str) -> None:
    if motor not in MOTOR_PINS:
        print(f"Warning: No pins defined for {motor}")
        return
    pin_fwd, pin_rev = MOTOR_PINS[motor]
    GPIO.output(pin_fwd, GPIO.HIGH if direction == "cw" else GPIO.LOW)
    GPIO.output(pin_rev, GPIO.HIGH if direction == "ccw" else GPIO.LOW)

def stop_motor(motor: str) -> None:
    if motor not in MOTOR_PINS:
        print(f"Warning: No pins defined for {motor}")
        return
    pin_fwd, pin_rev = MOTOR_PINS[motor]
    GPIO.output(pin_fwd, GPIO.LOW)
    GPIO.output(pin_rev, GPIO.LOW)

def move_motor_to_angle(motor: str, target: float, tolerance: float = ANGLE_TOLERANCE) -> None:
    if motor not in ADC_CHANNELS:
        print(f"Error: Cannot move {motor} (no ADC channel)")
        return
    print(f"Moving {motor} to {target:.1f} degrees...")
    while True:
        current = get_degrees(motor)
        if abs(current - target) <= tolerance:
            break
        dir_str = "cw" if target > current else "ccw"
        if motor in DIRECTION_REVERSE:
            dir_str = "ccw" if dir_str == "cw" else "cw"
        set_motor(motor, dir_str)
        time.sleep(0.05)
    stop_motor(motor)
    print(f"✅ {motor.capitalize()} reached target.")
    time.sleep(0.1)

def move_to_position(position: Dict[str, float]) -> None:
    threads = []
    for motor, target in position.items():
        if motor not in ADC_CHANNELS:
            print(f"Skipping {motor}: No ADC channel")
            continue
        t = threading.Thread(target=move_motor_to_angle, args=(motor, target))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

# ====== GRIPPER CONTROL ======
def open_gripper() -> None:
    print("🔴 Opening gripper to 200 degrees...")
    move_motor_to_angle('clipper', CLIPPER_ANGLES['open'])
    print("✅ Gripper opened")
    print("Current positions:", read_positions())

def close_gripper() -> None:
    print("🔴 Closing gripper to 23 degrees...")
    move_motor_to_angle('clipper', CLIPPER_ANGLES['close'])
    print("✅ Gripper closed")
    print("Current positions:", read_positions())

# ====== DIFFERENTIAL GRIPPER CONTROL ======
def diff_rotate(dirn: int) -> None:
    if not USE_DIFFERENTIAL_GRIPPER:
        print("Differential gripper disabled due to ADC failure")
        return
    print(f"Differential rotate: {'CW' if dirn > 0 else 'CCW'}")
    motor_drive('gripper1', dirn)
    motor_drive('gripper2', dirn)

def diff_bend(dirn: int) -> None:
    if not USE_DIFFERENTIAL_GRIPPER:
        print("Differential gripper disabled due to ADC failure")
        return
    print(f"Differential bend: {'Forward' if dirn > 0 else 'Backward'}")
    motor_drive('gripper1', dirn)
    motor_drive('gripper2', -dirn)

def diff_stop() -> None:
    if not USE_DIFFERENTIAL_GRIPPER:
        return
    print("Differential gripper stopped")
    motor_drive('gripper1', 0)
    motor_drive('gripper2', 0)

def motor_drive(motor: str, state: int) -> None:
    if motor not in MOTOR_PINS:
        print(f"Warning: No pins defined for {motor}")
        return
    pin_fwd, pin_rev = MOTOR_PINS[motor]
    if state > 0:
        dir_str = "cw"
    elif state < 0:
        dir_str = "ccw"
    else:
        GPIO.output(pin_fwd, GPIO.LOW)
        GPIO.output(pin_rev, GPIO.LOW)
        return
    if motor in DIRECTION_REVERSE:
        dir_str = "ccw" if dir_str == "cw" else "cw"
    set_motor(motor, dir_str)

def rotate_gripper(target_angle: float) -> None:
    if not USE_DIFFERENTIAL_GRIPPER:
        print("Differential gripper disabled; skipping rotation")
        return
    print(f"Rotating gripper to {target_angle:.1f} degrees...")
    threads = []
    threads.append(threading.Thread(target=move_motor_to_angle, args=('gripper1', 0)))
    threads.append(threading.Thread(target=move_motor_to_angle, args=('gripper2', 230)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("✅ Gripper rotated")
    print("Gripper feedback:", read_positions())

def read_positions() -> Dict[str, float]:
    result = {}
    for motor in list(MOTOR_PINS.keys()):
        result[motor] = get_degrees(motor) if motor in ADC_CHANNELS else None
    return result

# ====== VISION AND DETECTION FUNCTIONS ======
class YOLODetection:
    def __init__(self, class_id: int, class_name: str, confidence: float,
                 bbox_center_x: int, bbox_center_y: int, bbox: Tuple[int, int, int, int],
                 orientation: str, tag_center: Optional[Tuple[int, int]] = None):
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox_center_x = bbox_center_x
        self.bbox_center_y = bbox_center_y
        self.bbox = bbox
        self.orientation = orientation
        self.timestamp = time.time()
        self.tag_center = tag_center
        
        # Skip pick config and robot position for ignored classes
        if class_id in IGNORED_CLASS_IDS:
            self.pick_config = 'default'
            self.robot_position = None
            self.is_safe = False
            self.dustbin_number = None
            self.is_pickable = False
        else:
            self.pick_config = self.get_pick_config_for_class(class_name, orientation)
            self.robot_position = pixel_to_robot_coords(bbox_center_x, bbox_center_y, self.pick_config, tag_center)
            self.is_safe = is_position_safe(self.robot_position)
            self.dustbin_number = CLASS_TO_DUSTBIN_MAP.get(class_id)
            self.is_pickable = self.is_safe and self.dustbin_number is not None and class_id not in IGNORED_CLASS_IDS
    
    def get_pick_config_for_class(self, class_name: str, orientation: str) -> str:
        small_objects = ['bottle_cap', 'small_item']
        large_objects = ['large_bottle', 'big_item']
        
        if orientation in ['vertical', '45_to_vertical', 'horizontal', '45_to_horizontal']:
            return orientation
        elif class_name in small_objects:
            return 'small_object'
        elif class_name in large_objects:
            return 'large_object'
        else:
            return 'default'

def is_position_safe(position: Dict[str, float]) -> bool:
    safe_ranges = {
        'base': (0, 355),
        'arm1': (0, 355),
        'arm2': (0, 355),
        'gripper1': (0, 355),
        'gripper2': (0, 355),
        'clipper': (23, 300),
    }
    for joint, angle in position.items():
        if joint in safe_ranges and angle is not None:
            min_angle, max_angle = safe_ranges[joint]
            if not (min_angle <= angle <= max_angle):
                print(f"❌ {joint} angle {angle:.1f}° outside safe range [{min_angle}, {max_angle}]")
                return False
    return True

def detect_bin_number() -> int:
    with vision_lock:
        if not bin_queue.empty():
            latest_bin = None
            while not bin_queue.empty():
                latest_bin = bin_queue.get()
            return latest_bin
        return None

def get_best_detection() -> Optional[YOLODetection]:
    with vision_lock:
        if not detection_queue.empty():
            latest = None
            while not detection_queue.empty():
                latest = detection_queue.get()
            return latest
    return None

def get_stable_detection(num_frames=3, timeout=5.0) -> Optional[YOLODetection]:
    start_time = time.time()
    centers = []
    detections = []
    while len(detections) < num_frames and time.time() - start_time < timeout:
        detection = get_best_detection()
        if detection and detection.is_pickable:
            centers.append((detection.bbox_center_x, detection.bbox_center_y))
            detections.append(detection)
        time.sleep(0.1)
    if centers:
        avg_x = sum(x for x, _ in centers) / len(centers)
        avg_y = sum(y for _, y in centers) / len(centers)
        best_detection = max(detections, key=lambda d: d.confidence)
        best_detection.bbox_center_x = int(avg_x)
        best_detection.bbox_center_y = int(avg_y)
        best_detection.robot_position = pixel_to_robot_coords(int(avg_x), int(avg_y), best_detection.pick_config, best_detection.tag_center)
        return best_detection
    return None

def go_to_start() -> None:
    print("➡ Moving to start position...")
    pos = START_POSITION.copy()
    if is_position_safe(pos):
        move_to_position(pos)
        print("✅ Reached start position")
        print("Current positions:", read_positions())
    else:
        print("❌ Start position unsafe, stopping")
        return
    print("▶️ Activating camera for object detection...")
    camera_active.set()
    time.sleep(1)

def go_to_picking(target_position: Optional[Dict[str, float]] = None) -> None:
    if target_position is None:
        target_position = PICKING_POSITIONS[0].copy()
        target_position.update(GRIPPER_PICK_CONFIGURATIONS['default'])
    
    print("➡ Moving to picking position...")
    print(f"🎯 Target position: {target_position}")
    
    if is_position_safe(target_position):
        # Step 1: Move arm joints (base, arm1, arm2)
        arm_position = {k: v for k, v in target_position.items() if k in ['base', 'arm1', 'arm2']}
        if arm_position:
            print("🦾 Moving arm joints to position...")
            move_to_position(arm_position)
            print("✅ Arm joints reached position")
            print("Current positions:", read_positions())
            time.sleep(0.5)
        
        # Step 2: Move gripper joints (gripper1, gripper2)
        gripper_position = {k: v for k, v in target_position.items() if k in ['gripper1', 'gripper2']}
        if gripper_position:
            print("🤏 Moving gripper joints to position...")
            move_to_position(gripper_position)
            print("✅ Gripper joints reached position")
            print("Current positions:", read_positions())
            time.sleep(0.5)
        
        # Step 3: Move clipper joint
        clipper_position = {k: v for k, v in target_position.items() if k == 'clipper'}
        if clipper_position:
            print("✂️ Moving clipper to position...")
            move_to_position(clipper_position)
            print("✅ Clipper reached position")
            print("Current positions:", read_positions())
            time.sleep(0.5)
        
        print("✅ Reached picking position")
    else:
        print("❌ Picking position unsafe, stopping")

def place_to_dustbin(bin_number: int) -> None:
    if bin_number not in DUSTBINS:
        print(f"❌ Dustbin {bin_number} not found!")
        return
    print(f"➡ Moving to Dustbin {bin_number}...")
    pos = DUSTBINS[bin_number].copy()
    if is_position_safe(pos):
        # Step 1: Move arm joints (base, arm1, arm2)
        arm_position = {k: v for k, v in pos.items() if k in ['base', 'arm1', 'arm2']}
        if arm_position:
            print("🦾 Moving arm joints to dustbin position...")
            move_to_position(arm_position)
            print("✅ Arm joints reached dustbin position")
            print("Current positions:", read_positions())
            time.sleep(0.5)
        
        # Step 2: Move gripper joints (gripper1, gripper2)
        gripper_position = {k: v for k, v in pos.items() if k in ['gripper1', 'gripper2']}
        if gripper_position:
            print("🤏 Moving gripper joints to dustbin position...")
            move_to_position(gripper_position)
            print("✅ Gripper joints reached dustbin position")
            print("Current positions:", read_positions())
            time.sleep(0.5)
        
        # Step 3: Move clipper joint (open gripper)
        print("🤏 Opening clipper to release object...")
        open_gripper()
        print(f"✅ Object released at Dustbin {bin_number}")
        time.sleep(0.5)
    else:
        print(f"❌ Dustbin {bin_number} position unsafe, stopping")

# ====== HELPER FUNCTIONS ======
def test_fixed_gripper_position(pick_config: str = 'default') -> None:
    print(f"🧪 Testing fixed gripper position: {pick_config}")
    
    gripper_config = GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default'])
    print(f"📍 Gripper config: {gripper_config}")
    
    move_to_position(gripper_config)
    print("✅ Fixed gripper position reached")
    print("Current gripper positions:", {k: get_degrees(k) for k in ['gripper1', 'gripper2', 'clipper']})

def print_current_gripper_config(pick_config: str) -> None:
    gripper_config = GRIPPER_PICK_CONFIGURATIONS.get(pick_config, GRIPPER_PICK_CONFIGURATIONS['default'])
    print(f"📍 Current gripper config ({pick_config}): {gripper_config}")

# ====== TESTING AND DEBUGGING FUNCTIONS ======
def test_all_gripper_configs() -> None:
    for config in GRIPPER_PICK_CONFIGURATIONS:
        test_fixed_gripper_position(config)
        time.sleep(1)

def calibrate_gripper_position() -> None:
    print("🛠️ Calibrating gripper positions...")
    for motor in ['gripper1', 'gripper2', 'clipper']:
        if motor in ADC_CHANNELS:
            print(f"Current {motor} position: {get_degrees(motor):.1f}°")
            target = float(input(f"Enter target angle for {motor}: "))
            move_motor_to_angle(motor, target)
            print(f"✅ {motor} calibrated to {target:.1f}°")
            time.sleep(0.5)

def manual_move_to_coordinates(x: int, y: int, pick_config: str = 'default') -> None:
    print(f"📍 Moving to pixel coordinates ({x}, {y}) with gripper config {pick_config}")
    robot_position = pixel_to_robot_coords(x, y, pick_config)
    if robot_position and is_position_safe(robot_position):
        move_to_position(robot_position)
        print("✅ Reached target coordinates")
        print("Current positions:", read_positions())
    else:
        print("❌ Target position unsafe or invalid")

# ====== MAIN ======
def main() -> None:
    global vision_thread_running
    try:
        print("🚀 Starting Robot Control System with AprilTag Tracking")
        print(f"📋 Available gripper configurations: {list(GRIPPER_PICK_CONFIGURATIONS.keys())}")
        print(f"🚫 Ignored classes: {IGNORED_CLASS_IDS}")
        
        initialize_hardware()
        initialize_vision()
        go_to_start()
        time.sleep(1)
        cycle = 1

        while True:
            print(f"\n🎯 Cycle {cycle}: Waiting for a valid object detection...")
            detection = get_stable_detection()
            if detection and detection.is_pickable:
                print(f"✅ Detected: {detection.class_name} at pixel ({detection.bbox_center_x}, {detection.bbox_center_y}) "
                      f"for Dustbin {detection.dustbin_number}")
                print(f"🤏 Using gripper config: {detection.pick_config} (Orientation: {detection.orientation})")
                print_current_gripper_config(detection.pick_config)
                print("⏸️ Object detected! Pausing camera to begin pick and place.")
                camera_active.clear()
                go_to_picking(detection.robot_position)
                place_to_dustbin(detection.dustbin_number)
                go_to_start()
                time.sleep(1)
            else:
                bin_number = detect_bin_number()
                if bin_number is not None:
                    print(f"✅ Legacy detection for Dustbin {bin_number}")
                    print("🤏 Using default gripper configuration")
                    print_current_gripper_config('default')
                    print("⏸️ Object detected! Pausing camera to begin pick and place.")
                    camera_active.clear()
                    go_to_picking()
                    place_to_dustbin(bin_number)
                    go_to_start()
                else:
                    print("❌ No valid objects detected (ignored classes or no detections); continuing to next cycle")
                    time.sleep(1)
                    continue
            cycle += 1

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        print("Cleaning up resources...")
        vision_thread_running = False
        camera_active.set()
        time.sleep(0.5)
        for motor in MOTOR_PINS:
            stop_motor(motor)
        diff_stop()
        GPIO.cleanup()
        if cap is not None:
            cap.release()
        if DISPLAY_WEBCAM:
            cv2.destroyAllWindows()
        print("✅ Cleanup complete. Program terminated.")

if __name__ == "__main__":
    main()
