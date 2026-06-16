#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: main.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Main entry point for the application. Initializes and runs the GUI.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

import os
import platform
import sys

if platform.system() == "Linux":
    sys.path.append("/usr/lib/python3/dist-packages/")

    # Silence Qt warnings before OpenCV loads its binaries
    os.environ["QT_LOGGING_RULES"] = "*.warning=false"

import flet as ft
from src.gui import gui_build_and_run

if __name__ == "__main__":
    ft.run(main=gui_build_and_run)
