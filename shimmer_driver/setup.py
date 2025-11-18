from setuptools import find_packages, setup

package_name = 'shimmer_driver'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='juanjose-ensta',
    maintainer_email='juan-jose.garcia@ensta-paris.fr',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'shimmer_publisher = shimmer_driver.shimmer_node:main'
        ],
    },
)
