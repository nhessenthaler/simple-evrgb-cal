# Copyright 2026 [Nico Hessenthaler, Heilbronn University of Applied Sciences]
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: main.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Main entry point for the application. Initializes and runs the GUI.
License: Licensed under the Apache License, Version 2.0
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
