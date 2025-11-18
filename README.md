# HRI Server

Human-Robot Interaction (HRI) server system for collecting and processing multimodal sensor data including thermal camera, blink detection, and physiological sensors (Shimmer).

## Overview

This project consists of multiple servers and components:

1. **hri_server.py** - Main Flask server that integrates thermal camera, blink detection, and Shimmer sensor data
2. **shimmer_server.py** - Standalone FastAPI server for Shimmer sensor data
3. **ROS2 packages** - For distributed sensor processing (blink_tracker, shimmer_driver, thermal_camera_driver, sensor_bridge)
4. **Video player** - ROS2-based video player with HRI data recording

## Prerequisites

### System Requirements

- **Python 3.8+**
- **ROS2** (Humble or later) - Required for ROS2-based components
- **Linux** (tested on Ubuntu 22.04)
- **Thermal Camera SDK** - libirimager library (for thermal camera support)
- **Bluetooth** - For Shimmer sensor connection

### Hardware Requirements

- Optris thermal camera (with XML configuration file)
- Shimmer sensor (GSR/PPG) connected via Bluetooth
- Webcam or camera for blink detection (if using blink_tracker)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd HRIServcer
```

### 2. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Install ROS2 Dependencies

If you plan to use the ROS2 components, ensure ROS2 is installed and sourced:

```bash
# Source ROS2 (adjust path for your installation)
source /opt/ros/humble/setup.bash

# Build ROS2 packages (if needed)
colcon build --packages-select blink_tracker shimmer_driver thermal_camera_driver sensor_bridge
```

### 4. Install System Dependencies

#### Thermal Camera SDK

The thermal camera requires the `libirimager` library. Install according to your camera manufacturer's instructions.

#### dlib Models

Ensure the dlib model files are present:
- `dlib_files/dlib_face_detector.svm`
- `dlib_files/dlib_landmark_predictor.dat`

These should already be included in the repository.

## Configuration

### Thermal Camera Configuration

1. Place your thermal camera XML configuration file in the project root (e.g., `16070070.xml`)
2. Update the path in `hri_server.py` if your XML file has a different name or location:

```python
pathXml = b'./16070070.xml'  # Update this path
```

### Shimmer Sensor Configuration

1. Connect your Shimmer sensor via Bluetooth
2. Find the serial port (usually `/dev/rfcommXX` on Linux)
3. Update the port in the relevant files:
   - `hri_server.py`: Line 588 - `shimmer_port = "/dev/rfcomm22"`
   - `HRI_data/shimmer_server.py`: Command line argument or default
   - `shimmer_driver/shimmer_driver/shimmer_node.py`: Line 17 - `self.serial_port = '/dev/rfcomm22'`

## Usage

### Running the Main HRI Server

The main server integrates all components (thermal camera, blink detection, and Shimmer):

```bash
python3 hri_server.py
```

The server will start on `http://localhost:8080` with the following endpoints:

- `GET /` - Raw thermal camera image
- `GET /thermal` - Processed thermal image with temperature ROIs
- `GET /blink` - Blink detection image with blink rate overlay
- `GET /data` - Combined JSON data (temperatures, blink rate, GSR, PPG)
- `GET /temperatures` - Temperature data only
- `GET /shimmer` - Shimmer sensor data (GSR, PPG)

**Note**: Make sure your thermal camera and Shimmer sensor are connected before starting the server.

### Running the Shimmer Server Separately

To run only the Shimmer sensor server:

```bash
python3 HRI_data/shimmer_server.py /dev/rfcomm22 --port 8000
```

Arguments:
- `shimmer_port` - Bluetooth serial port (e.g., `/dev/rfcomm22`)
- `--port` or `-p` - HTTP server port (default: 8000)
- `--output` or `-o` - Optional CSV output file for data logging

The server provides:
- `GET /latest` - Latest Shimmer data (GSR, PPG, timestamp)

### Running ROS2 Components

#### Launch All ROS2 Nodes

To launch all ROS2 nodes together:

```bash
source /opt/ros/humble/setup.bash
ros2 launch sensor_bridge hri-data-launch.py
```

This launches:
- `blink_tracker` - Blink detection node
- `shimmer_publisher` - Shimmer data publisher
- `optris_imager_node` - Thermal camera node
- `optris_colorconvert_node` - Thermal image color conversion
- `thermal_face_extraction` - Face temperature extraction
- `hri_data_aggregator` - Data aggregation node

#### Running Individual ROS2 Nodes

**Blink Tracker:**
```bash
ros2 run blink_tracker blink_tracker
```

**Shimmer Publisher:**
```bash
ros2 run shimmer_driver shimmer_publisher
```

**Thermal Camera Driver:**
```bash
ros2 run thermal_camera_driver thermal_face_extraction
```

**Sensor Bridge (Data Aggregator):**
```bash
ros2 run sensor_bridge hri_data_aggregator
```

### Running the Video Player

The video player subscribes to ROS2 HRI data and allows recording:

```bash
python3 HRI_data/video_player/player.py
```

Place video files in `HRI_data/video_player/vids/` directory.

### Running the Shimmer Client Plot

To visualize Shimmer data from the standalone server:

```bash
python3 HRI_data/shimmer_client_plot.py http://localhost:8000
```

## Project Structure

```
HRIServcer/
├── hri_server.py                 # Main Flask server
├── HRI_data/
│   ├── shimmer_server.py         # Standalone Shimmer FastAPI server
│   ├── shimmer_client_plot.py    # Shimmer data visualization client
│   └── video_player/
│       ├── player.py             # ROS2 video player
│       └── dummy_hri_publisher.py # Dummy HRI data publisher
├── blink_tracker/                # ROS2 blink detection package
├── shimmer_driver/               # ROS2 Shimmer driver package
├── thermal_camera_driver/        # ROS2 thermal camera package
├── sensor_bridge/                # ROS2 sensor data bridge package
├── dlib_files/                   # dlib model files
├── optris_drivers2-master/       # Optris thermal camera drivers
├── *.xml                         # Thermal camera configuration files
└── requirements.txt              # Python dependencies
```

## API Endpoints

### Main HRI Server (Port 8080)

- `GET /` - Raw thermal camera palette image (JPEG)
- `GET /thermal` - Processed thermal image with temperature ROIs (JPEG)
- `GET /blink` - Blink detection image with blink rate overlay (JPEG)
- `GET /data` - Combined JSON data:
  ```json
  {
    "temperatures": {...},
    "blink_rate": 0.0,
    "shimmer": {
      "timestamp": 0,
      "gsr": 0.0,
      "ppg": 0.0
    }
  }
  ```
- `GET /temperatures` - Temperature data only (JSON)
- `GET /shimmer` - Shimmer sensor data only (JSON)

### Shimmer Server (Port 8000)

- `GET /latest` - Latest Shimmer sample:
  ```json
  {
    "timestamp": 0,
    "gsr": 0.0,
    "ppg": 0.0
  }
  ```

## Troubleshooting

### Thermal Camera Issues

- Ensure the XML configuration file matches your camera serial number
- Check that `libirimager` library is installed and accessible
- Verify camera is connected via USB

### Shimmer Sensor Issues

- Check Bluetooth connection: `rfcomm -a` or `ls /dev/rfcomm*`
- Verify the serial port path matches your system
- Ensure Shimmer sensor is powered on and paired

### ROS2 Issues

- Ensure ROS2 is properly sourced: `source /opt/ros/humble/setup.bash`
- Build packages if needed: `colcon build`
- Check node status: `ros2 node list`

### Port Conflicts

- Change ports in the code if default ports (8080, 8000) are in use
- For Flask: `app.run(host='0.0.0.0', port=8080)` in `hri_server.py`
- For FastAPI: `--port` argument in `shimmer_server.py`

## Logging

Log files are automatically generated and stored in the project root:
- `log.txt` - General log file
- `logfilename_*.log` - Timestamped thermal camera logs

These files are excluded from git via `.gitignore`.

## License

[Add your license information here]

## Contributing

[Add contribution guidelines if applicable]

## Contact

[Add contact information if desired]

