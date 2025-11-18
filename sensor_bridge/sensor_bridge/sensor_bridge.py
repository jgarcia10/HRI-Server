import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Float32MultiArray
import math

class HRIDataAggregator(Node):
    def __init__(self):
        super().__init__('hri_data_aggregator')
        print("HRI Data Aggregator node initialized.")
        
        self.gsr = None
        self.ppg = None
        self.facial_temp = None
        self.blinking = None
        
        # Subscriptions
        self.create_subscription(Float32, 'shimmer/gsr', self.gsr_callback, 10)
        self.create_subscription(Float32, 'shimmer/ppg', self.ppg_callback, 10)
        self.create_subscription(Float32MultiArray, '/facial_temperature', self.facial_temp_callback, 10)
        self.create_subscription(Float32, '/blinking', self.blinking_callback, 10)
        
        # Publisher
        self.publisher_ = self.create_publisher(Float32MultiArray, '/hri/combined_data', 10)
        
        # Timer
        self.create_timer(0.1, self.timer_callback)
    
    def gsr_callback(self, msg):
        self.gsr = msg.data
        #print(f"Received GSR: {self.gsr}")
    
    def ppg_callback(self, msg):
        self.ppg = msg.data
        #print(f"Received PPG: {self.ppg}")
    
    def facial_temp_callback(self, msg):
        self.facial_temp = msg.data
        #print(f"Received facial temperature: {len(self.facial_temp)} elements")
    
    def blinking_callback(self, msg):
        self.blinking = msg.data
        #print(f"Received blinking: {self.blinking}")
    
    def timer_callback(self):
        print("Timer callback triggered.")
        if self.gsr is None:
            print("Waiting for GSR data...")
        if self.ppg is None:
            print("Waiting for PPG data...")
        if self.facial_temp is None:
            print("Waiting for facial temperature data...")
        if self.blinking is None:
            print("Waiting for blinking data...")

        
        if all(data is not None for data in [self.gsr, self.ppg, self.facial_temp, self.blinking]):
            combined_data = [self.gsr, self.ppg] + list(self.facial_temp) + [self.blinking]

            # Check for any NaN values
            if any(math.isnan(value) for value in combined_data):
                print("NaN value detected, skipping publish.")
            else:
                print(f"Publishing combined data: {combined_data}")
                msg = Float32MultiArray()
                msg.data = combined_data
                self.publisher_.publish(msg)
        else:
            print("Not all data received yet.")

def main():
    rclpy.init()
    node = HRIDataAggregator()
    print("Starting to spin the node...")
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()