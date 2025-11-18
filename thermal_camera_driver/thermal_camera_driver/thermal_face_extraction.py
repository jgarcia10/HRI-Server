import os
import time
import numpy as np
import dlib
import cv2
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray
from cv_bridge import CvBridge

class RegionsOfInterest(object):
    """Class for regions of interest."""

    def __init__(self, coords_x, coords_y):
        """Initialization method."""
        self.coords_x = coords_x
        self.coords_y = coords_y

        self.eyes_dist = self.coords_x[45] - self.coords_x[36]

        self.regions = {'face': self.define_entire_face(),
                        'forehead': self.define_forehead(),
                        'left_cheek': self.define_left_cheek(),
                        'right_cheek': self.define_right_cheek(),
                        # 'left_periorbital': self.define_left_periorbital(),
                        # 'right_periorbital': self.define_right_periorbital(),
                        'chin': self.define_chin(),
                        'nose': self.define_nose()}

        self.eng_regions = {'forehead': self.define_forehead(),
                            'nose': self.define_nose()}
    
    
    def define_forehead(self):
        """Method which returns the coordinates of the forehead region."""
        interm_point = self.coords_x[23] - self.coords_x[20]
        coord_x = self.coords_x[21]
        coord_y = self.coords_y[20] - interm_point / 2
        coord_x1 = self.coords_x[22]
        coord_y1 = self.coords_y[23] - interm_point / 4

        forehead = [coord_x, coord_y, coord_x1, coord_y1]
        return forehead

    def define_left_periorbital(self):
        """Method which returns the coordinates of the periorbital region."""
        coord_x = self.coords_x[4] - self.half_small
        coord_y = self.coords_y[4] - self.half_small
        coord_x1 = self.coords_x[4] + self.half_small
        coord_y1 = self.coords_y[4] + self.half_small

        left_periorbital = [coord_x, coord_y, coord_x1, coord_y1]
        return left_periorbital

    def define_right_periorbital(self):
        """Method which returns the coordinates of the periorbital region."""
        coord_x = self.coords_x[3] - self.half_small
        coord_y = self.coords_y[3] - self.half_small
        coord_x1 = self.coords_x[3] + self.half_small
        coord_y1 = self.coords_y[3] + self.half_small

        right_periorbital = [coord_x, coord_y, coord_x1, coord_y1]
        return right_periorbital

    def define_right_cheek(self):
        """Method which returns the coordinates of the cheek region."""
        coord_x = self.coords_x[10]
        coord_y = self.coords_y[14]
        coord_x1 = self.coords_x[12]
        coord_y1 = self.coords_y[13]

        right_cheek = [coord_x, coord_y, coord_x1, coord_y1]
        return right_cheek

    def define_left_cheek(self):
        """Method which returns the coordinates of the cheek region."""
        coord_x = self.coords_x[4]
        coord_y = self.coords_y[14]
        coord_x1 = self.coords_x[6]
        coord_y1 = self.coords_y[13]

        left_cheek = [coord_x, coord_y, coord_x1, coord_y1]
        return left_cheek

    def define_chin(self):
        """Method which returns the coordinates of the chin region."""
        interm_point_chin = self.coords_x[9] - self.coords_x[7]
        coord_x = self.coords_x[7]
        coord_y = self.coords_y[7] - interm_point_chin/2
        coord_x1 = self.coords_x[9]
        coord_y1 = self.coords_y[9] - interm_point_chin/4

        chin = [coord_x, coord_y, coord_x1, coord_y1]
        return chin

    def define_nose(self):
        """Method which returns the coordinates of the nose region."""
        coord_x = self.coords_x[32] 
        coord_y = self.coords_y[29]
        coord_x1 = self.coords_x[34]
        coord_y1 = self.coords_y[30]

        nose = [coord_x, coord_y, coord_x1, coord_y1]
        return nose

    def define_entire_face(self):
        """Method which returns the coordinates of the face region."""
        coord_x = self.coords_x[2]
        coord_y = self.coords_y[0] - self.eyes_dist
        coord_x1 = self.coords_x[5]
        coord_y1 = self.coords_y[10] + self.eyes_dist

        face = [coord_x, coord_y, coord_x1, coord_y1]
        return face

    def get_all_regions(self):
        """Method which returns the coordinates of all ROIs."""
        return self.regions
    
    def get_eng_regions(self):
        return self.eng_regions

    def get_one_region(self, region):
        """Method which returns the coordinates of only one ROI."""
        return self.regions[region]

    def get_multiple_regions(self, regions):
        """Method which returns the coordinates of a selection of ROIs."""
        # regions is a list with all the regions to be extracted
        region = {}
        for index, reg in enumerate(regions):
            region[reg] = self.regions[reg]
        return region



class FacialTemperatureExtractor(Node):
    def __init__(self):
        super().__init__('facial_temperature_extractor')

        # Define regions of interest
        self.regions = ['forehead', 'left_cheek', 'right_cheek', 'nose']
        self.redetect_time = 5.0  # Time to redetect face in seconds

        # Load Dlib models from the package's resource folder
        package_share_dir = get_package_share_directory('thermal_camera_driver')
        detector_path = '/home/juanjose-ensta/cognitive_load_interface_ws/src/thermal_camera_driver/resource/dlib_face_detector.svm'
        predictor_path = '/home/juanjose-ensta/cognitive_load_interface_ws/src/thermal_camera_driver/resource/dlib_landmark_predictor.dat'
        self.detector = dlib.simple_object_detector(detector_path)
        self.predictor = dlib.shape_predictor(predictor_path)

        # Initialize variables
        self.tracker = dlib.correlation_tracker()
        self.detected = []
        self.start_time = time.time()
        self.temp = None
        self.frame = None
        self.face_rectangle = None
        self.bridge = CvBridge()

        # Subscribers
        self.create_subscription(Image, '/thermal_image_view', self.process_thermal_view, 10)
        self.create_subscription(Image, '/thermal_image', self.process_thermal, 10)

        # Publisher for facial temperatures
        self.temp_pub = self.create_publisher(Float32MultiArray, '/facial_temperature', 10)

        self.get_logger().info('Facial Temperature Extractor Node initialized.')

    def process_thermal_view(self, msg):
        """Process the thermal image view for face detection, ROI extraction, and visualization."""
        # Convert ROS Image message to OpenCV format
        try:
            self.frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error(f"Error converting thermal view image: {str(e)}")
            return

        # Face detection and tracking
        if not self.detected:
            self.detected = self.detector(self.frame, 1)
            if self.detected:
                # Use the first detected face
                rect = self.detected[0]
                # Set self.face_rectangle as a list of [left, top, right, bottom]
                self.face_rectangle = [rect.left(), rect.top(), rect.right(), rect.bottom()]
                # Start tracking with this rectangle
                self.tracker.start_track(self.frame, rect)
                self.get_logger().info("Face detected and tracking started.")
        else:
            # Update tracker position
            tracking_quality = self.tracker.update(self.frame)
            if tracking_quality >= 8.75:  # Adjust threshold as needed
                tracked_position = self.tracker.get_position()
                self.face_rectangle = [int(tracked_position.left()), int(tracked_position.top()),
                                    int(tracked_position.right()), int(tracked_position.bottom())]
            else:
                # Reset detection if tracking quality is too low
                self.detected = []

        # Redetect face periodically
        if time.time() - self.start_time > self.redetect_time:
            self.start_time = time.time()
            self.detected = []
            self.get_logger().info("Redetecting face...")

        # Process face if detected or tracked
        if self.detected or self.face_rectangle:
            if self.face_rectangle is not None:
                # Get landmarks
                shapes = self.predictor(self.frame, dlib.rectangle(*self.face_rectangle))
                landmarks_x = [p.x for p in shapes.parts()]
                landmarks_y = [p.y for p in shapes.parts()]

                # Draw landmarks (optional, for debugging)
                for x, y in zip(landmarks_x, landmarks_y):
                    cv2.circle(self.frame, (x, y), 1, (255, 0, 0), 2)

                # Extract ROIs and temperatures
                rois = RegionsOfInterest(landmarks_x, landmarks_y)
                coord = rois.get_multiple_regions(self.regions)
                temperatures = []

                for region in self.regions:
                    if region in coord:
                        points = coord[region]
                        x_left, y_top, x_right, y_bottom = map(int, points)
                        # Draw ROI rectangle
                        cv2.rectangle(self.frame, (x_left, y_top), (x_right, y_bottom), (0, 255, 0), 1)
                        if self.temp is not None:
                            # Extract and compute average temperature
                            temperature = self.temp[y_top:y_bottom, x_left:x_right]
                            avg_temp = float(np.mean(temperature))
                            temperatures.append(avg_temp)
                    else:
                        self.get_logger().warn(f"Region '{region}' not found in ROI coordinates.")
            else:
                self.get_logger().warn("Face rectangle not set; skipping landmark prediction.")

            # Publish and log temperatures if available
            if self.temp is not None and temperatures:
                temp_msg = Float32MultiArray()
                temp_msg.data = temperatures
                self.temp_pub.publish(temp_msg)
                log_str = "Facial Temperatures: " + ", ".join(
                    f"{reg}={temp:.2f}°C" for reg, temp in zip(self.regions, temperatures)
                )
                self.get_logger().info(log_str)

        # Visualize the frame with ROIs
        cv2.imshow('Thermal Image View with ROIs', self.frame)
        cv2.waitKey(1)

    def process_thermal(self, msg):
        """Process raw thermal image to extract temperature data."""
        try:
            thermal_data = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)
            self.temp = (thermal_data - 1000) / 10.0  # Convert to temperature
        except Exception as e:
            self.get_logger().error(f"Error processing thermal image: {str(e)}")

def main(args=None):
    rclpy.init(args=args)
    node = FacialTemperatureExtractor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down node.")
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()