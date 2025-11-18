import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from serial import Serial
from pyshimmer import ShimmerBluetooth, DEFAULT_BAUDRATE, DataPacket, EChannelType

class ShimmerPublisher(Node):
    def __init__(self):
        super().__init__('shimmer_publisher')
        
        # Create publishers for the two topics
        self.gsr_publisher = self.create_publisher(Float32, 'shimmer/gsr', 10)
        self.ppm_publisher = self.create_publisher(Float32, 'shimmer/ppg', 10)
        
        # Set up the serial connection (adjust port as needed)
        self.serial_port = '/dev/rfcomm22'
        self.serial = Serial(self.serial_port, DEFAULT_BAUDRATE)
        
        # Initialize the Shimmer device
        self.shim_dev = ShimmerBluetooth(self.serial)
        self.shim_dev.initialize()
        dev_name = self.shim_dev.get_device_name()
        self.get_logger().info(f"Device Name: {dev_name}")

        # Register the data handler callback
        self.shim_dev.add_stream_callback(self.data_callback)
        
        # Start streaming sensor data
        self.shim_dev.start_streaming()
        self.get_logger().info("Started streaming sensor data")

    def data_callback(self, pkt: DataPacket) -> None:
        """Callback to handle each incoming data packet."""
        try:
            # Extract the desired channels from the data packet
            gsr_value = pkt[EChannelType.GSR_RAW]
            adc_value = pkt[EChannelType.INTERNAL_ADC_13]
            
            # Publish GSR_RAW on the topic "shimmer/gsr"
            gsr_msg = Float32()
            gsr_msg.data = float(gsr_value)
            self.gsr_publisher.publish(gsr_msg)
            
            # Publish INTERNAL_ADC_13 on the topic "shimmer/ppm"
            adc_msg = Float32()
            adc_msg.data = float(adc_value)
            self.ppm_publisher.publish(adc_msg)
            
            # Log published values (optional)
            self.get_logger().info(f"Published GSR_RAW: {gsr_msg.data} | INTERNAL_ADC_13: {adc_msg.data}")
        except Exception as e:
            self.get_logger().error(f"Error in data_callback: {e}")

    def destroy_node(self):
        # Stop sensor streaming and shut down the device before closing the node
        self.shim_dev.stop_streaming()
        self.shim_dev.shutdown()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = ShimmerPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Keyboard Interrupt (SIGINT)")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
