
# Simplified Cross-Modal Calibration for Heterogeneous Event-RGB Stereo Systems

This repository contains the official implementation and source code for the academic paper:
**"Simplified Cross-Modal Calibration for Heterogeneous Event-RGB Stereo Systems"** (Published at [BMVC, 2026])  

*Authors: Nico Hessenthaler, Adam T. Müller, and Nicolaj C. Stache* 
Topics: event-camera, stereo-vision, calibration, cross-modal, computer-vision, rgb-event  
[![Paper]()]([Link_to_Paper]) 


>**Abstract:**

---

## Getting Started

### 1. Install prerequesites

#### uv
Use the UV package installer to create a virtual environment and manage the required Python packages very easily and fast.

##### Linux
You can install uv with a single standalone script:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
##### Windows
To install uv on Windows, perform the following steps:
1. Click the Start menu, type PowerShell, and open it.
2. Copy and paste the following command, then hit enter:
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
3. Restart your terminal. Close PowerShell and open a fresh window so your system registers the new PATH changes.
<br>
<br>
#### Turbo JPEG
##### Linux
Download latest libjpeg-turbo tar ball from the releases: https://github.com/libjpeg-turbo/libjpeg-turbo/releases ( version > 3 is required). Then install all dependencies for the installation:
```
sudo apt update
sudo apt install build-essential cmake nasm
```
Extract the tar ball:
```
tar -xvzf libjpeg-turbo-3.1.4.1.tar.gz
cd libjpeg-turbo-3.1.4.1
```
Build the package:
```
mkdir build && cd build
cmake -G"Unix Makefiles" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr ..
make -j$(nproc)
sudo make install
```
Update the cache:
```
sudo ldconfig
```
Check the installation:
```
ldconfig -p | grep turbojpeg
```

##### Windows
Download latest libjpeg-turbo .exe (libjpeg-turbo-3.x.x-vc64.exe) from the releases: https://github.com/libjpeg-turbo/libjpeg-turbo/releases ( version > 3 is required). Then run the .exe installer. Make sure to tick the box that says "Add to PATH".
<br>
<br>
#### IDS uEye
Make sure to install the drivers required to capture RGB images with the uEye camera.
##### Linux
1. Visit the IDS download center https://de.ids-imaging.com/downloads.html and select the version of your uEye camera.
2. Download the latest IDS Software Suite for Linux (Debian Package).
3. Extract the .tgz by double clicking it.
4. Navigate to the extracted directory and open a terminal.
5. Install all dependencies with the following command:
```
sudo apt install ./ueye-api*.deb ./ueye-common*.deb ./ueye-demos*.deb ./ueye-dev*.deb ./ueye-driver-eth*.deb ./ueye-driver-usb*.deb ./ueye-tools-cli*.deb ./ueye-tools-qt5*.deb ./ueye-interfaces-halcon*.deb
```
6. Navigate to the installation folder in /opt/ids/ueye/bin and double click on idscameramanager to launch the GUI for the camera manager.
7. Try to open your connected camera via camera manager. If it is not working instantly, use the manager to configure the IP adress or to upload a matching starter firmware.

##### Windows
<br>
<br>
#### OpenEB (Metavision SDK)
Make sure to install the OpenEB or Metavision SDK drivers required to capture events with the Prophesee event-based camera.
##### Linux
This installation guide relates to Ubuntu 24.04 with Python 3.12.
Install the JFrog server signing public key:
```
sudo apt -y install curl
curl -L https://propheseeai.jfrog.io/artifactory/api/security/keypair/prophesee-gpg/public >/tmp/propheseeai.jfrog.op.asc
sudo cp /tmp/propheseeai.jfrog.op.asc /etc/apt/trusted.gpg.d
```
Add the OpenEB repository of Prophesee’s JFROG server to the list of APT repositories with this command:
```
sudo add-apt-repository 'https://propheseeai.jfrog.io/artifactory/openeb-debian/'
```
Update the list of repositories/packages and install OpenEB:
```
sudo apt update
sudo apt -y install metavision-openeb
```
##### Windows

---

### 2. Clone the repository

To set up a local copy of this project, clone the repository using Git. Open your terminal or command prompt and run the following commands:

bash
#### Clone the repository
```
git clone git@github.com:nhessenthaler/simple-evrgb-cal.git
```

#### Navigate into the project directory
```
cd simple-evrgb-cal
```

---

### 3. Setup of virtual environment
It is recommended to run the cross-modal stereo calibration tool in a virtual uv environment. Thus, create a virtual environment with the following command:
```
uv venv --python 3.12.12
```
Then, activate the virtual environment:
```
source .venv/bin/activate
```
Synchronize the packages specified in the pyproject.toml in the virtual environment:
```
uv sync
```

---

### 4. Adapt configuration

---

### 5. Start the calibration tool
Start the GUI of the cross-modal stereo calibration tool:
```
python main.py
```

