from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Start the blink_tracker node
        Node(
            package='blink_tracker',
            executable='blink_tracker',
            output='screen'
        ),
        # Start the shimmer_publisher node
        Node(
            package='shimmer_driver',
            executable='shimmer_publisher',
            output='screen'
        ),
        # Start the optris_imager_node with an XML configuration file
        Node(
            package='optris_drivers2',
            executable='optris_imager_node',
            arguments=['16070070.xml'],
            output='screen'
        ),
        # Start the optris_colorconvert_node
        Node(
            package='optris_drivers2',
            executable='optris_colorconvert_node',
            output='screen'
        ),
        # Start the thermal_face_extraction node
        Node(
            package='thermal_camera_driver',
            executable='thermal_face_extraction',
            output='screen'
        ),
        # Start the hri_data_aggregator node (from sensor_bridge package)
        Node(
            package='sensor_bridge',
            executable='hri_data_aggregator',
            output='screen'
        )
    ])
