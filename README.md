
<div align="center">

# Simplified Cross-Modal Calibration for Heterogeneous Event-RGB Stereo Systems

**Nico Hessenthaler**, **Adam T. Müller**, and **Nicolaj C. Stache**

_Published at [BMVC 2026]_

[![Paper]()](Link_to_Paper)

</div>

---

> **Abstract:**
>
> Accurate extrinsic calibration between event-based and frame-based cameras remains a practical bottleneck for heterogeneous stereo systems. Existing approaches often require sensor or target motion, precise synchronization, or computationally expensive event-to-image reconstruction using neural networks. We propose a simple, motion-free cross-modal calibration framework that uses a temporally modulated, blended ChArUco target presented on standard consumer displays. By alternating between the original pattern and a partially blended version, the target reliably triggers events while remaining continuously observable to a frame-based camera, avoiding blank frames and reducing synchronization constraints. We discretize events into frames coarsely aligned with the RGB images, apply lightweight denoising, and perform ChArUco-based intrinsic and stereo extrinsic calibration. Extensive experiments analyze operating conditions and robustness, including the influence of blending opacity, display brightness, external illumination disturbances, and handheld acquisition. Compared to both a reconstruction-based baseline (E2Calib) and a ChArUco-adapted variant of this baseline, our approach reduces the mean reprojection error by up to 66 % and yields more robust stereo extrinsic estimation, all while substantially simplifying the calibration procedure. Finally, we demonstrate practical utility in a robotic eye-to-hand calibration case study, showing consistent transformations and stable downstream geometric measurements even under partial occlusions.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
   - [uv Package Manager](#uv-package-manager)
   - [libjpeg-turbo](#libjpeg-turbo)
   - [IDS uEye SDK](#ids-ueye-sdk)
   - [OpenEB (Metavision SDK)](#openeb-metavision-sdk)
2. [Installation](#2-installation)
3. [Virtual Environment Setup](#3-virtual-environment-setup)
4. [Configuration](#4-configuration)
5. [Running the Calibration Tool](#5-running-the-calibration-tool)

---

> [!CAUTION]
> **Note:** This tool has been tested on **Windows 11** and **Linux (Ubuntu 24.04)** with **Python 3.12**.
> We recommend using **Linux** for the calibration workflow, as the OpenEB installation on Windows requires compiling the SDK from source, which significantly increases setup time.

## 1. Prerequisites

Before proceeding with the installation, ensure that all required dependencies are installed on your system.

### uv Package Manager

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver used to manage the virtual environment and project dependencies.

#### Linux

Install uv using the official installer script:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
#### Windows

1. Open **PowerShell** (search for "PowerShell" in the Start menu).
2. Execute the following command:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

3. Restart your terminal to apply the updated `PATH` environment variable.

---

### libjpeg-turbo

libjpeg-turbo is required for efficient JPEG encoding during image capture. Version **3.x** or higher is mandatory.

#### Linux

Download the latest source tarball from the [libjpeg-turbo releases page](https://github.com/libjpeg-turbo/libjpeg-turbo/releases), then install the build dependencies:
```
sudo apt update
sudo apt install build-essential cmake nasm
```
Extract the archive and configure the build:

```bash
tar -xvzf libjpeg-turbo-3.1.4.1.tar.gz
cd libjpeg-turbo-3.1.4.1
```

Compile and install:

```bash
mkdir build && cd build
cmake -G"Unix Makefiles" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr ..
make -j$(nproc)
sudo make install
```

Refresh the shared library cache and verify the installation:

```bash
sudo ldconfig
```

```bash
ldconfig -p | grep turbojpeg
```

#### Windows

Download the precompiled installer (`libjpeg-turbo-3.x.x-vc64.exe`) from the [releases page](https://github.com/libjpeg-turbo/libjpeg-turbo/releases) and run it.

---

### IDS uEye SDK

The IDS uEye SDK provides drivers and APIs for capturing RGB images with IDS uEye cameras.

#### Linux

1. Visit the [IDS Download Center](https://de.ids-imaging.com/downloads.html) and select your camera model.
2. Download the latest **IDS Software Suite for Linux** (Debian package).
3. Extract the downloaded `.tgz` archive.
4. Navigate to the extracted directory and install the packages:
```bash
sudo apt install ./ueye-api*.deb ./ueye-common*.deb ./ueye-demos*.deb ./ueye-dev*.deb ./ueye-driver-eth*.deb ./ueye-driver-usb*.deb ./ueye-tools-cli*.deb ./ueye-tools-qt5*.deb ./ueye-interfaces-halcon*.deb
```

5. Launch the camera manager by executing `idscameramanager` in `/opt/ids/ueye/bin`.
6. Verify that your camera is detected. If necessary, use the manager to configure the IP address or upload a compatible firmware.

#### Windows

1. Visit the [IDS Download Center](https://de.ids-imaging.com/downloads.html) and select your camera model.
2. Download the latest **IDS Software Suite for Windows 11**.
3. Extract the downloaded `.zip` archive.
4. Run the installer and follow the on-screen instructions.

---

### OpenEB (Metavision SDK)

The OpenEB / Metavision SDK provides drivers and APIs for capturing events from Prophesee event-based cameras.

#### Linux

_The following instructions apply to Ubuntu 24.04 with Python 3.12._

Import the JFrog signing key:
```
sudo apt -y install curl
curl -L https://propheseeai.jfrog.io/artifactory/api/security/keypair/prophesee-gpg/public >/tmp/propheseeai.jfrog.op.asc
sudo cp /tmp/propheseeai.jfrog.op.asc /etc/apt/trusted.gpg.d
```
Add the OpenEB repository and install the SDK:
```bash
sudo add-apt-repository 'https://propheseeai.jfrog.io/artifactory/openeb-debian/'
```

```bash
sudo apt update
sudo apt -y install metavision-openeb
```

#### Windows

Installation on Windows requires compiling the SDK from source. Refer to the official [Prophesee documentation](https://docs.prophesee.ai/stable/installation/windows_openeb.html#upgrading-openeb) for detailed instructions.

---

## 2. Installation

Clone this repository and navigate into the project directory:

```bash
git clone git@github.com:nhessenthaler/simple-evrgb-cal.git
```

```bash
cd simple-evrgb-cal
```

---

## 3. Virtual Environment Setup

We recommend using `uv` to create an isolated virtual environment for the calibration tool.

Create the virtual environment (Python 3.12.12):

```bash
uv venv --python 3.12.12
```

### Linux

Activate the environment and synchronize dependencies:

```bash
source .venv/bin/activate
```

```bash
uv sync
```

### Windows

First, allow script execution for the current session:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
```

Then activate the environment and synchronize dependencies:

```powershell
.venv\Scripts\activate
```

```powershell
uv sync
```

---

## 4. Configuration

_[To be documented.]_

---

## 5. Running the Calibration Tool

Once all prerequisites are installed and the configuration is adapted to your hardware setup, start the calibration GUI with:

```bash
python main.py
```

---

## Citation

If you use this work in a research paper, please cite our publication:

```bibtex
@inproceedings{hessenthaler2026simplified,
  title={Simplified Cross-Modal Calibration for Heterogeneous Event-RGB Stereo Systems},
  author={Hessenthaler, Nico and M{\"u}ller, Adam T. and Stache, Nicolaj C.},
  booktitle={British Machine Vision Conference (BMVC)},
  year={2026}
}
```

---

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.

---

## Keywords

_Event Camera · Stereo Vision · Calibration · Cross-Modal · Computer Vision · RGB-Event Fusion_

