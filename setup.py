import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cellscan",
    version="0.2.0",
    author="Jesse B. Crawford",
    author_email="jesse@jbcrawford.us",
    description="Mobile data collection for IMSI catcher identification",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jcrawfordor/cellscan",
    packages=setuptools.find_packages(),
    python_requires='>=3.7',
    install_requires=[
        'gpiozero',
        'pyserial',
        'pynmea2',
        'peewee'
    ],
    entry_points = {
        'console_scripts': ['cellscan=cellscan.start:__main__', 'cellserv=cellscan.server'],
    }
)