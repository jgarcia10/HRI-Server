import cv2
import mediapipe as mp
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage  # Import CompressedImage
from std_msgs.msg import Float32
from cv_bridge import CvBridge

class BlinkTracker(Node):
    def __init__(self):
        super().__init__('blink_tracker')
        self.bridge = CvBridge()
        
        # Initialize MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Blink detection parameters
        self.ear_threshold = 0.25  # Adjusted for MediaPipe landmarks
        self.consecutive_frames = 3
        self.blink_frames = 0
        self.was_closed = False
        
        # Option 1: Cumulative blink counter (10% weight)
        self.blink_counter = 0
        self.start_time_secs = self.get_clock().now().nanoseconds / 1e9
        
        # Option 2: Sliding window method (5-second window, 70% weight)
        self.blink_timestamps_sliding = []
        self.window2 = 5.0  # window duration in seconds
        
        # Option 3: Instantaneous blink rate using time difference (20% weight)
        self.t_last_blink_instant = None
        self.instant_blink_rate = 0.0
        
        # Publisher for weighted blink rate
        self.blink_pub = self.create_publisher(Float32, '/blinking', 10)
        
        # Publisher for the compressed image
        self.compressed_image_pub = self.create_publisher(CompressedImage, '/blink_image/compressed', 10)
        
        # Timer to process frames (~30 FPS)
        self.create_timer(0.033, self.process_frame)

    def process_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            self.get_logger().error("Failed to grab frame")
            return

        # Convert the frame to RGB for MediaPipe processing
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(frame_rgb)
        
        # Get current time in seconds
        current_time_ros = self.get_clock().now()
        current_time_secs = current_time_ros.nanoseconds / 1e9

        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                # Extract eye landmarks (using predefined indices)
                left_eye = self.get_eye_landmarks(face_landmarks, [33, 160, 158, 133, 153, 144])
                right_eye = self.get_eye_landmarks(face_landmarks, [362, 385, 387, 263, 373, 380])
                
                # Calculate EAR for both eyes and average them
                left_ear = self.calculate_ear(left_eye)
                right_ear = self.calculate_ear(right_eye)
                avg_ear = (left_ear + right_ear) / 2.0

                # Blink detection using EAR threshold and consecutive frames
                if avg_ear < self.ear_threshold:
                    self.blink_frames += 1
                else:
                    if self.blink_frames >= self.consecutive_frames and not self.was_closed:
                        # A blink event is detected.
                        # Option 1: Update cumulative blink counter.
                        self.blink_counter += 1
                        
                        # Option 2: Append current timestamp to sliding window list.
                        self.blink_timestamps_sliding.append(current_time_secs)
                        
                        # Option 3: Compute instantaneous blink rate if possible.
                        if self.t_last_blink_instant is not None:
                            dt = current_time_secs - self.t_last_blink_instant
                            self.instant_blink_rate = 60.0 / dt if dt > 0 else 0.0
                        self.t_last_blink_instant = current_time_secs
                        
                        self.was_closed = True
                    # Reset blink frame counter and flag.
                    self.blink_frames = 0
                    self.was_closed = False

                # Draw landmarks on the eyes and display EAR value.
                self.draw_landmarks(frame, left_eye)
                self.draw_landmarks(frame, right_eye)
                cv2.putText(frame, f"EAR: {avg_ear:.2f}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # --- Compute the three blink rates ---
        # Option 1: Cumulative blink rate (blinks per minute)
        elapsed_time_secs = current_time_secs - self.start_time_secs
        elapsed_time_minutes = elapsed_time_secs / 60.0
        blink_rate_option1 = self.blink_counter / elapsed_time_minutes if elapsed_time_minutes > 0 else 0.0

        # Option 2: Sliding window blink rate (using the last 5 seconds)
        # Remove any blink timestamps older than the 5-second window.
        self.blink_timestamps_sliding = [ts for ts in self.blink_timestamps_sliding 
                                         if current_time_secs - ts <= self.window2]
        blink_rate_option2 = len(self.blink_timestamps_sliding) * (60.0 / self.window2)
        
        # Option 3: Instantaneous blink rate (already computed as self.instant_blink_rate)
        
        # --- Weighted average calculation ---
        weighted_blink_rate = (0.1 * blink_rate_option1 +
                               0.7 * blink_rate_option2 +
                               0.2 * self.instant_blink_rate)
        
        # Publish the weighted blink rate.
        blink_msg = Float32()
        blink_msg.data = weighted_blink_rate
        self.blink_pub.publish(blink_msg)

        # Display the weighted blink rate on the frame.
        cv2.putText(frame, f"Weighted Blink Rate: {weighted_blink_rate:.2f} blinks/min", (10, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow('instant blinking average', frame)
        cv2.waitKey(1)

        # Compress the frame into a JPEG image and publish it.
        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            compressed_msg = CompressedImage()
            compressed_msg.header.stamp = current_time_ros.to_msg()
            compressed_msg.format = "jpeg"
            compressed_msg.data = np.array(buffer).tobytes()
            self.compressed_image_pub.publish(compressed_msg)

    def get_eye_landmarks(self, landmarks, indices):
        # Assuming a default webcam resolution; adjust if needed.
        h, w = 480, 640
        return np.array([(int(landmarks.landmark[i].x * w), int(landmarks.landmark[i].y * h))
                         for i in indices])

    def calculate_ear(self, eye):
        # Calculate the Eye Aspect Ratio (EAR)
        A = np.linalg.norm(eye[1] - eye[5])
        B = np.linalg.norm(eye[2] - eye[4])
        C = np.linalg.norm(eye[0] - eye[3])
        ear = (A + B) / (2.0 * C)
        return ear

    def draw_landmarks(self, frame, eye):
        for point in eye:
            cv2.circle(frame, tuple(point), 2, (0, 255, 0), -1)

    def destroy_node(self):
        self.cap.release()
        cv2.destroyAllWindows()
        super().destroy_node()

    @property
    def cap(self):
        # Lazily initialize the camera.
        if not hasattr(self, '_cap'):
            self._cap = cv2.VideoCapture(6)
            if not self._cap.isOpened():
                self.get_logger().error("Cannot open camera")
                rclpy.shutdown()
        return self._cap

def main(args=None):
    rclpy.init(args=args)
    node = BlinkTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
