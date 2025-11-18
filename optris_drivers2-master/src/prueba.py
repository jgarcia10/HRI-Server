import yaml
with open('/home/juanjose-ensta/.ros/camera_info/camera.yaml', 'r') as f:
    data = yaml.safe_load(f)
print(data)
