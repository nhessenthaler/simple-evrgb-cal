#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: stereo_calibration.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides functionality to perform stereo calibration on the event camera and RGB camera.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from __future__ import annotations

from pathlib import Path
import sys

t_project_path = Path(__file__).parents[1]
sys.path.append(str(t_project_path))

import atexit
import asyncio
import configparser
import flet as ft
from .flet_controls import (
    BlueCustomButton,
    RedCustomButton,
    BlueCustomIconButton,
    BlueCustomMediumText,
    BlueCustomImageContainer,
    CountdownTimer,
)
from core import (
    B64SharedMemory,
    CoreStereoCalibration,
    CalibrationPhase,
    CameraState,
    CameraType,
    create_image_placeholder,
    RawSharedMemory,
)
from multiprocessing import Queue, Manager
from multiprocessing.managers import ValueProxy, SyncManager
from multiprocessing.synchronize import Event as EventProxy


class StereoCalibrationGUI:
    """A Flet GUI showing image displays of event and RGB cameras along configuration options."""

    def __init__(self, page: ft.Page, width: int = 1300, height: int = 700):
        self.__width = width
        self.__height = height
        self.__page = page
        self.__page.theme_mode = "light"
        self.__page.window.maximized = True

        # Configure correct closing behavior
        self.__page.window.prevent_close = True
        self.__page.window.on_event = self._on_window_event

        # Get the parameters from the configuration file
        self.__gui_config = configparser.ConfigParser()

        self.__gui_config.read(Path(__file__).parents[2] / "parameter" / "gui.ini")

        # Read the data capture parameters from the configuration file
        self.__image_width = self.__gui_config.getint("data_capture", "image_width")
        self.__image_height = self.__gui_config.getint("data_capture", "image_height")
        self.__image_display_height = self.__gui_config.getint("data_capture", "image_display_height")
        self.__b64_shared_memory_size = self.__gui_config.getint("data_capture", "b64_shared_memory_size")
        self.__raw_shared_memory_size = self.__gui_config.getint("data_capture", "raw_shared_memory_size")

        # Initialize raw image shared memory (producers: rgb and event cameras, consumer: calibration core)
        self.__event_raw_shared_memory = RawSharedMemory(size=self.__raw_shared_memory_size)
        self.__rgb_raw_shared_memory = RawSharedMemory(size=self.__raw_shared_memory_size)

        # Initialize base64 shared-memory frame buffers (producer: calibration core, consumer: calibration GUI)
        self.__event_frame_shared_memory = B64SharedMemory(size=self.__b64_shared_memory_size)
        self.__rgb_frame_shared_memory = B64SharedMemory(size=self.__b64_shared_memory_size)

        # Initialize synchonization queue for coarse synchronization between event and RGB camera processes
        # (e.g. to signal simultaneous capture)
        self.__synchronization_queue = Queue()

        # Initialize shared-memory manager related attributes for inter-process communication and data sharing.
        self.__shared_memory_manager = Manager()
        self.__rgb_recording_path = self.__shared_memory_manager.Value(str, "")
        self.__event_recording_path = self.__shared_memory_manager.Value(str, "")
        self.__rgb_recording_active = self.__shared_memory_manager.Event()
        self.__event_recording_active = self.__shared_memory_manager.Event()
        self.__rgb_camera_ready = self.__shared_memory_manager.Event()
        self.__stereo_calibration_active = self.__shared_memory_manager.Event()
        self.__generate_targets_triggered = self.__shared_memory_manager.Event()
        self.__next_capture_timer = self.__shared_memory_manager.Value("d", -1.0)

        # Initialize shared value for calibration phase
        self.__current_calibration_phase = self.__shared_memory_manager.Value("i", -1)

        # Create phase display box
        self.__phase_label = ft.Text(
            value="Status: Calibration Inactive",
            color=ft.Colors.WHITE,
            size=26,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        self.__phase_display = ft.Container(
            content=self.__phase_label,
            bgcolor="#004f9e",
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=30, vertical=12),
            width=750,
        )

        # Initialize checkerboard square size from config
        self.__checkerboard_config = configparser.ConfigParser()
        self.__checkerboard_config.read(Path(__file__).parents[2] / "parameter" / "stereo_calibration.ini")
        t_initial_square_size = self.__checkerboard_config.getfloat("target", "target_square_size")
        self.__target_square_size = self.__shared_memory_manager.Value("d", t_initial_square_size)
        self.__capture_interval = self.__checkerboard_config.getfloat("recording", "capture_interval")

        # Compute fixed image box size and create an SVG placeholder
        self.__initialization_src = create_image_placeholder(
            self.__image_width, self.__image_display_height, annotation="Camera Initialization ..."
        )
        self.__error_src = create_image_placeholder(
            self.__image_width, self.__image_display_height, annotation="Connection Error ..."
        )

        # Image placeholders (use placeholder so box always has defined content/size)
        self.__event_image = ft.Image(
            src=self.__initialization_src, width=self.__image_width, height=self.__image_height, gapless_playback=True
        )
        self.__rgb_image = ft.Image(
            src=self.__initialization_src, width=self.__image_width, height=self.__image_height, gapless_playback=True
        )

        # Countdown timer widget to display time until next capture
        self.__countdown_timer = CountdownTimer(
            countdown_value=self.__capture_interval,
            countdown_max=self.__capture_interval,
            label_text="Next image in:",
        )
        self.__countdown_timer_placeholder = ft.Container(
            height=self.__countdown_timer.height,
            width=self.__countdown_timer.width,
            visible=True,
        )

        # Create target size controls
        self.__target_size_text = BlueCustomMediumText(
            value=f"{self.__target_square_size.value:.3f} m",
            size=20,
        )

        self.__decrease_size_button = BlueCustomIconButton(
            icon=ft.Icons.REMOVE,
            icon_color=ft.Colors.WHITE,
            on_click=lambda e: self._adjust_target_size(e, -0.001),
            tooltip="Decrease grid size by 1 mm",
        )

        self.__increase_size_button = BlueCustomIconButton(
            icon=ft.Icons.ADD,
            icon_color=ft.Colors.WHITE,
            on_click=lambda e: self._adjust_target_size(e, 0.001),
            tooltip="Increase grid size by 1 mm",
        )

        self.__generate_target_button = BlueCustomButton(
            content="Generate Target",
            on_click=self._trigger_target_generation,
            tooltip="Generates a hybrid calibration target for RGB / Event cameras as video and bitmap for Arduino displays",
        )

        # Create buttons
        self.__blue_stereo_calibration_button = BlueCustomButton(
            content="Start Calibration",
            on_click=self._stereo_calibration_button_clicked,
            disabled=True,
            bgcolor="#a9a9a9",
        )

        self.__red_stereo_calibration_button = RedCustomButton(
            content="Stop Calibration",
            on_click=self._stereo_calibration_button_clicked,
            bgcolor="#e30613",
        )

        self.__stereo_calibration_button_container = ft.Container(content=self.__blue_stereo_calibration_button)

        # Instantiate core calibration logic
        self.__core_stereo_calibration = CoreStereoCalibration(self)

        # Initialize camera states
        self.__camera_states = {CameraType.EVENT: CameraState.INIT, CameraType.RGB: CameraState.INIT}

        # Perform asynchonous setup
        self._get_event_loop()
        self.__event_image_task = asyncio.create_task(
            self.image_live_stream_updater(self.event_frame_shared_memory, self.event_image, CameraType.EVENT)
        )
        self.__rgb_image_task = asyncio.create_task(
            self.image_live_stream_updater(self.rgb_frame_shared_memory, self.rgb_image, CameraType.RGB)
        )
        self.__timer_task = asyncio.create_task(self._timer_updater())
        self.__stop_event = asyncio.Event()

        # Register cleanup function to ensure proper release of shared memory resources on application exit
        atexit.register(self.cleanup)

    # ##### GETTER #####
    @property
    def width(self) -> int:
        """
        Getter for the attribute '__width'.

        Args:
            ():

        Returns:
            width (int): The attribute '__width'.
        """

        return self.__width

    @property
    def height(self) -> int:
        """
        Getter for the attribute '__height'.

        Args:
            ():

        Returns:
            height (int): The attribute '__height'.
        """

        return self.__height

    @property
    def page(self) -> ft.Page:
        """
        Getter for the attribute '__page'.

        Args:
            ():

        Returns:
            page (ft.Page): The attribute '__page'.
        """

        return self.__page

    @property
    def event_image(self) -> ft.Image:
        """
        Getter for the attribute '__event_image'.

        Args:
            ():

        Returns:
            event (ft.Image): The attribute '__event_image'.
        """

        return self.__event_image

    @property
    def rgb_image(self) -> ft.Image:
        """
        Getter for the attribute '__rgb_image'.

        Args:
            ():

        Returns:
            rgb_image (ft.Image): The attribute '__rgb_image'.
        """

        return self.__rgb_image

    @property
    def countdown_timer(self) -> CountdownTimer:
        """
        Getter for the attribute '__countdown_timer'.

        Args:
            ():

        Returns:
            countdown_timer (CountdownTimer): The attribute '__countdown_timer'.
        """

        return self.__countdown_timer

    @property
    def countdown_timer_placeholder(self) -> ft.Container:
        """
        Getter for the attribute '__countdown_timer_placeholder'.

        Args:
            ():

        Returns:
            countdown_timer_placeholder (ft.Container): The attribute '__countdown_timer_placeholder'.
        """

        return self.__countdown_timer_placeholder

    @property
    def target_size_text(self) -> BlueCustomMediumText:
        """
        Getter for the attribute '__target_size_text'.

        Args:
            ():

        Returns:
            target_size_text (BlueCustomMediumText): The attribute '__target_size_text'.
        """

        return self.__target_size_text

    @property
    def decrease_size_button(self) -> BlueCustomIconButton:
        """
        Getter for the attribute '__decrease_size_button'.

        Args:
            ():

        Returns:
            decrease_size_button (BlueCustomIconButton): The attribute '__decrease_size_button'.
        """

        return self.__decrease_size_button

    @property
    def increase_size_button(self) -> BlueCustomIconButton:
        """
        Getter for the attribute '__increase_size_button'.

        Args:
            ():

        Returns:
            increase_size_button (BlueCustomIconButton): The attribute '__increase_size_button'.
        """

        return self.__increase_size_button

    @property
    def generate_target_button(self) -> BlueCustomButton:
        """
        Getter for the attribute '__generate_target_button'.

        Args:
            ():

        Returns:
            generate_target_button (BlueCustomButton): The attribute '__generate_target_button'.
        """

        return self.__generate_target_button

    @property
    def blue_stereo_calibration_button(self) -> BlueCustomButton:
        """
        Getter for the attribute '__blue_stereo_calibration_button'.

        Args:
            ():

        Returns:
            stereo_calibration_button (BlueCustomButton): The attribute '__blue_stereo_calibration_button'.
        """

        return self.__blue_stereo_calibration_button

    @property
    def red_stereo_calibration_button(self) -> RedCustomButton:
        """
        Getter for the attribute '__red_stereo_calibration_button'.

        Args:
            ():

        Returns:
            red_stereo_calibration_button (RedCustomButton): The attribute '__red_stereo_calibration_button'.
        """

        return self.__red_stereo_calibration_button

    @property
    def stereo_calibration_button_container(self) -> ft.Container:
        """
        Getter for the attribute '__stereo_calibration_button_container'.

        Args:
            ():

        Returns:
            stereo_calibration_button_container (ft.Container): The attribute '__stereo_calibration_button_container'.
        """

        return self.__stereo_calibration_button_container

    @property
    def stereo_calibration_active(self) -> EventProxy:
        """
        Getter for the attribute '__stereo_calibration_active'.

        Args:
            ():

        Returns:
            stereo_calibration_active (multiprocessing.Event): The attribute '__stereo_calibration_active'.
        """

        return self.__stereo_calibration_active

    @property
    def core_stereo_calibration(self) -> CoreStereoCalibration:
        """
        Getter for the attribute '__core_stereo_calibration'.

        Args:
            ():

        Returns:
            core_stereo_calibration (CoreStereoCalibration): The attribute '__core_stereo_calibration'.
        """

        return self.__core_stereo_calibration

    @property
    def camera_states(self) -> dict[CameraType, CameraState]:
        """
        Getter for the attribute '__camera_states'.

        Args:
            ():

        Returns:
            camera_states (dict[CameraType, CameraState]): The attribute '__camera_states'.
        """

        return self.__camera_states

    @property
    def event_frame_shared_memory(self) -> B64SharedMemory:
        """
        Getter for the attribute '__event_frame_shared_memory'.

        Args:
            ():

        Returns:
            event_frame_shared_memory (B64SharedMemory): The attribute '__event_frame_shared_memory'.
        """

        return self.__event_frame_shared_memory

    @property
    def rgb_frame_shared_memory(self) -> B64SharedMemory:
        """
        Getter for the attribute '__rgb_frame_shared_memory'.

        Args:
            ():

        Returns:
            rgb_frame_shared_memory (B64SharedMemory): The attribute '__rgb_frame_shared_memory'.
        """

        return self.__rgb_frame_shared_memory

    @property
    def event_raw_shared_memory(self) -> RawSharedMemory:
        """
        Getter for the attribute '__event_raw_shared_memory'.

        Args:
            ():

        Returns:
            event_raw_shared_memory (RawSharedMemory): The attribute '__event_raw_shared_memory'.
        """
        return self.__event_raw_shared_memory

    @property
    def rgb_raw_shared_memory(self) -> RawSharedMemory:
        """
        Getter for the attribute '__rgb_raw_shared_memory'.

        Args:
            ():

        Returns:
            rgb_raw_shared_memory (RawSharedMemory): The attribute '__rgb_raw_shared_memory'.
        """
        return self.__rgb_raw_shared_memory

    @property
    def synchronization_queue(self) -> Queue:
        """
        Getter for the attribute '__synchronization_queue'.

        Args:
            ():

        Returns:
            synchronization_queue (Queue): The attribute '__synchronization_queue'.
        """

        return self.__synchronization_queue

    @property
    def shared_memory_manager(self) -> SyncManager:
        """
        Getter for the attribute '__shared_memory_manager'.

        Args:
            ():

        Returns:
            shared_memory_manager (Manager): The attribute '__shared_memory_manager'.
        """

        return self.__shared_memory_manager

    @property
    def rgb_recording_path(self) -> ValueProxy:
        """
        Getter for the attribute '__rgb_recording_path'.

        Args:
            ():

        Returns:
            rgb_recording_path (ValueProxy): The attribute '__rgb_recording_path'.
        """

        return self.__rgb_recording_path

    @property
    def rgb_recording_active(self) -> EventProxy:
        """
        Getter for the attribute '__rgb_recording_active'.

        Args:
            ():

        Returns:
            rgb_recording_active (multiprocessing.Event): The attribute '__rgb_recording_active'.
        """

        return self.__rgb_recording_active

    @property
    def event_recording_path(self) -> ValueProxy:
        """
        Getter for the attribute '__event_recording_path'.

        Args:
            ():

        Returns:
            event_recording_path (ValueProxy): The attribute '__event_recording_path'.
        """

        return self.__event_recording_path

    @property
    def event_recording_active(self) -> EventProxy:
        """
        Getter for the attribute '__event_recording_active'.

        Args:
            ():

        Returns:
            event_recording_active (multiprocessing.Event): The attribute '__event_recording_active'.
        """

        return self.__event_recording_active

    @property
    def rgb_camera_ready(self) -> EventProxy:
        """
        Getter for the attribute '__rgb_camera_ready'.

        Args:
            ():

        Returns:
            rgb_camera_ready (multiprocessing.Event): The attribute '__rgb_camera_ready'.
        """

        return self.__rgb_camera_ready

    @property
    def generate_targets_triggered(self) -> EventProxy:
        """
        Getter for the attribute '__generate_targets_triggered'.

        Args:
            ():

        Returns:
            generate_targets_triggered (multiprocessing.Event): The attribute '__generate_targets_triggered'.
        """

        return self.__generate_targets_triggered

    @property
    def next_capture_timer(self) -> ValueProxy:
        """
        Getter for the attribute '__next_capture_timer'.

        Args:
            ():

        Returns:
            next_capture_timer (ValueProxy): The attribute '__next_capture_timer'.
        """

        return self.__next_capture_timer

    @property
    def current_calibration_phase(self) -> ValueProxy:
        """
        Getter for the attribute '__current_calibration_phase'.

        Args:
            ():

        Returns:
            current_calibration_phase (ValueProxy): The attribute '__current_calibration_phase'.
        """

        return self.__current_calibration_phase

    @property
    def phase_label(self) -> ft.Text:
        """
        Getter for the attribute '__phase_label'.

        Args:
            ():

        Returns:
            phase_label (ft.Text): The attribute '__phase_label'.
        """

        return self.__phase_label

    @property
    def phase_display(self) -> ft.Container:
        """
        Getter for the attribute '__phase_display'.

        Args:
            ():

        Returns:
            phase_display (ft.Container): The attribute '__phase_display'.
        """

        return self.__phase_display

    @property
    def target_square_size(self) -> ValueProxy:
        """
        Getter for the attribute '__target_square_size'.

        Args:
            ():

        Returns:
            target_square_size (ValueProxy): The attribute '__target_square_size'.
        """

        return self.__target_square_size

    @property
    def event_image_task(self) -> asyncio.Task:
        """
        Getter for the attribute '__event_image_task'.

        Args:
            ():

        Returns:
            event_image_task (asyncio.Task): The attribute '__event_image_task'.
        """

        return self.__event_image_task

    @property
    def rgb_image_task(self) -> asyncio.Task:
        """
        Getter for the attribute '__rgb_image_task'.

        Args:
            ():

        Returns:
            rgb_image_task (asyncio.Task): The attribute '__rgb_image_task'.
        """

        return self.__rgb_image_task

    @property
    def timer_task(self) -> asyncio.Task:
        """
        Getter for the attribute '__timer_task'.

        Args:
            ():

        Returns:
            timer_task (asyncio.Task): The attribute '__timer_task'.
        """

        return self.__timer_task

    @property
    def stop_event(self) -> asyncio.Event:
        """
        Getter for the attribute '__stop_event'.

        Args:
            ():

        Returns:
            stop_event (asyncio.Event): The attribute '__stop_event'.
        """

        return self.__stop_event

    # ##### SETTER #####

    # ##### UI #####
    def _create_image_titles(self) -> ft.Row:
        """
        Method that creates the titles above the image fields for the Cobot Image Fetch page.

        Args:
            ():

        Returns:
            titles_row (ft.Row): A row containing the titles for the image fields.
        """

        return ft.Row(
            [
                ft.Container(
                    content=BlueCustomMediumText(
                        "RGB Camera:",
                    ),
                    alignment=ft.Alignment.CENTER,
                    width=self.__image_width,
                ),
                ft.Container(
                    content=BlueCustomMediumText(
                        "Event-Based Camera:",
                    ),
                    alignment=ft.Alignment.CENTER,
                    width=self.__image_width,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=30,
        )

    def _build(self) -> None:
        """
        Build the GUI layout on the given Flet page.

        Args:
            page (ft.Page): The Flet page to build the GUI on.

        Returns:
            ():
        """

        self.page.window_width = self.width
        self.page.window_height = self.height
        self.page.window_resizable = False
        self.page.window.icon = str(Path(__file__).parent / "assets" / "AI-TRAQC-Logo-1.ico")
        self.page.title = "Cross-modal Stereo-Calibration of Event-based and RGB Cameras"

        t_settings_row = ft.Row(
            [
                ft.Container(
                    expand=True,
                ),
                ft.Container(
                    expand=True,
                ),
                ft.Container(
                    content=self.generate_target_button,
                    padding=ft.Padding.only(bottom=20),
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                    visible=True,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            BlueCustomMediumText("Square Size:", size=18),
                            self.decrease_size_button,
                            self.target_size_text,
                            self.increase_size_button,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    padding=ft.Padding.only(bottom=20),
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                    visible=True,
                ),
                ft.Container(
                    expand=True,
                ),
                ft.Container(
                    expand=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

        t_titles_row = self._create_image_titles()

        t_images_row = ft.Row(
            [
                BlueCustomImageContainer(
                    content=self.rgb_image,
                    width=self.rgb_image.width,
                    height=self.rgb_image.height,
                ),
                BlueCustomImageContainer(
                    content=self.event_image,
                    width=self.event_image.width,
                    height=self.event_image.height,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=24,
        )

        t_countdown_row = ft.Container(
            content=ft.Row(
                [self.countdown_timer, self.countdown_timer_placeholder],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(top=20, bottom=10),
        )

        t_footer = ft.Row(
            [
                self.stereo_calibration_button_container,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=30,
        )

        t_footer_container = ft.Container(
            content=t_footer,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.only(top=10),
        )

        t_phase_display_row = ft.Container(
            content=ft.Row(
                [self.phase_display],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(top=10, bottom=10),
        )

        self.page.add(
            ft.Column(
                [t_phase_display_row, t_settings_row, t_titles_row, t_images_row, t_countdown_row, t_footer_container],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
        )

        return

    # ##### PRIVATE METHODS #####
    def _get_event_loop(self) -> None:
        """
        Method to get or create the asyncio event loop for all asynchronous operations in the core.
        Mainly required to display live video feed frames in the GUI.

        Args:
            ():

        Returns:
            ():
        """

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            t_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(t_loop)

        return

    async def _on_window_event(self, e: ft.WindowEvent) -> None:
        """
        Event handler for the window events.
        Ensures proper cleanup of resources before closing the application if event is a close event.

        Args:
            e (ft.WindowEvent): The Flet window event object.

        Returns:
            ():
        """

        if e.type == ft.WindowEventType.CLOSE:
            self.cleanup()
            await self.page.window.destroy()

        return

    def _reset_calibration_gui(self) -> None:
        """
        Method to reset the calibration-related UI elements to their default state when calibration is stopped or finished.

        Args:
            ():

        Returns:
            ():
        """

        self.stereo_calibration_button_container.content = self.blue_stereo_calibration_button
        self.decrease_size_button.disabled = False
        self.decrease_size_button.bgcolor = "#004f9e"
        self.increase_size_button.disabled = False
        self.increase_size_button.bgcolor = "#004f9e"
        self.generate_target_button.disabled = False
        self.generate_target_button.bgcolor = "#004f9e"
        self.decrease_size_button.update()
        self.increase_size_button.update()
        self.generate_target_button.update()
        self.stereo_calibration_button_container.update()
        self.current_calibration_phase.value = -1
        self.phase_label.value = "Status: Calibration Inactive"
        self.phase_display.update()

        return

    def _adjust_target_size(self, _, delta: float) -> None:
        """
        Method to adjust the target square size based on GUI button inputs.
        Increments or decrements the target square size by 1 mm.

        Args:
            delta (float): Amount to change the target size by (e.g. -0.001 or 0.001).

        Returns:
            (): None
        """

        # Ensure minimum size of 1 mm
        t_new_target_size = max(0.001, self.target_square_size.value + delta)
        self.target_square_size.value = t_new_target_size
        self.target_size_text.value = f"{self.target_square_size.value:.3f} m"
        self.target_size_text.update()

        return

    def _trigger_target_generation(self, _) -> None:
        """
        Method that triggers the calibration target generation process for an Arduino display bitmap and video of a flickering calibration target.

        Args:
            ():

        Returns:
            ():
        """

        self.generate_targets_triggered.set()

        return

    def _stereo_calibration_button_clicked(self, _) -> None:
        """
        Method that coordinates all core logic for the stereo calibration process.

        Args:
            ():

        Returns:
            ():
        """

        if not self.stereo_calibration_active.is_set():
            self.stereo_calibration_active.set()
            self.stereo_calibration_button_container.content = self.red_stereo_calibration_button

            # Disable target size controls and generation button
            self.decrease_size_button.disabled = True
            self.decrease_size_button.bgcolor = "#a9a9a9"
            self.increase_size_button.disabled = True
            self.increase_size_button.bgcolor = "#a9a9a9"
            self.generate_target_button.disabled = True
            self.generate_target_button.bgcolor = "#a9a9a9"
            self.decrease_size_button.update()
            self.increase_size_button.update()
            self.generate_target_button.update()
            self.stereo_calibration_button_container.update()
        else:
            self.stereo_calibration_active.clear()
            self._reset_calibration_gui()

        return

    async def _timer_updater(self) -> None:
        """
        Asynchronous method to continuously update the timer text display in the GUI.
        Reads the remaining time from the shared memory updated by the core.

        Args:
            ():

        Returns:
            ():
        """

        t_was_calibration_active = False

        while True:
            await asyncio.sleep(0.1)

            if self.stop_event.is_set():
                break

            t_is_calibration_active = self.stereo_calibration_active.is_set()

            # Falling edge: core cleared the flag externally (robot-assisted calibration finished)
            if t_was_calibration_active and not t_is_calibration_active:
                self._reset_calibration_gui()

            # Store current state for edge detection in the next iteration
            t_was_calibration_active = t_is_calibration_active

            # Update phase display label from shared value
            if t_is_calibration_active:
                t_phase_value = self.current_calibration_phase.value
                try:
                    t_new_label = CalibrationPhase(t_phase_value).label
                except ValueError:
                    t_new_label = "Status: Calibration Inactive"
                if self.phase_label.value != t_new_label:
                    self.phase_label.value = t_new_label
                    self.phase_display.update()

                # Get the timer for the next image capture in manual calibration mode
                t_remaining = self.next_capture_timer.value

                # Update countdown timer widget
                # The timer is automatic if calibration is active
                self.countdown_timer.automatic = True

                # Check for camera errors
                t_error_state = (
                    self.camera_states[CameraType.EVENT] == CameraState.ERROR
                    or self.camera_states[CameraType.RGB] == CameraState.ERROR
                )
                self.countdown_timer.error = t_error_state

                # Update visual timer value
                self.countdown_timer.update_timer(t_remaining, self.countdown_timer.countdown_max)

                # Specific visibility logic: only if active, no errors, and not in robot mode
                # (t_remaining == -1 signals robot-driven mode where no countdown is needed)
                t_show_timer = not t_error_state and t_remaining >= 0
                self.countdown_timer.visible = t_show_timer
                self.countdown_timer_placeholder.visible = not t_show_timer
                self.countdown_timer.update()
                self.countdown_timer_placeholder.update()

            else:
                self.countdown_timer.automatic = False
                self.countdown_timer.visible = False
                self.countdown_timer_placeholder.visible = True
                self.countdown_timer.update()
                self.countdown_timer_placeholder.update()

        return

    # ##### PUBLIC METHODS #####
    def build_gui(self) -> None:
        """
        Public method to build the GUI layout by calling the internal build method.

        Args:
            ():

        Returns:
            ():
        """

        self._build()

        return

    def cleanup(self) -> None:
        """
        Method to perform cleanup operations on application exit, such as releasing shared memory resources.

        Args:
            ():

        Returns:
            ():
        """

        self.stop_event.set()
        self.core_stereo_calibration.terminate_processes()
        self.event_frame_shared_memory.close()
        self.rgb_frame_shared_memory.close()
        self.synchronization_queue.close()
        self.rgb_image_task.cancel()
        self.event_image_task.cancel()
        self.timer_task.cancel()
        self.shared_memory_manager.shutdown()

        return

    def update_camera_state(self, camera_type: CameraType, state: CameraState) -> None:
        """
        Update the state of a camera and adjust the start calibration button accordingly.

        Args:
            camera_type (CameraType): The type of camera (EVENT or RGB).
            state (CameraState): The new state (INIT, RUNNING, or ERROR).

        Returns:
            ():
        """

        self.camera_states[camera_type] = state

        # Enable start calibration button only if both cameras are running
        if (
            self.camera_states[CameraType.EVENT] == CameraState.RUNNING
            and self.camera_states[CameraType.RGB] == CameraState.RUNNING
        ):
            self.blue_stereo_calibration_button.disabled = False
            self.blue_stereo_calibration_button.bgcolor = "#004f9e"
        else:
            self.blue_stereo_calibration_button.disabled = True
            self.blue_stereo_calibration_button.bgcolor = "#a9a9a9"

        self.blue_stereo_calibration_button.update()

        return

    async def image_live_stream_updater(
        self, shared_memory: B64SharedMemory, image_widget: ft.Image, camera_type: CameraType
    ) -> None:
        """
         Asynchronous method to continuously update a given Flet Image widget with frames from a shared memory buffer.
         This is used to display the live video feed from the event and rgb cameras in the GUI.

         Args:
            shared_memory (B64SharedMemory): The shared memory buffer from which to read the latest frames.
            image_widget (ft.Image): The Flet Image widget to update with the latest frames.
            camera_type (CameraType): The type of camera being updated (e.g., CameraType.EVENT, CameraType.RGB).

        Returns:
            ():
        """

        # Infinite loop to continuously check for new frames in the shared memory buffer and update the image widget
        while True:

            # Half of the actual frame time for smoother updates (e.g., ~25ms => ~40 FPS, twice as fast to fulfill nyquist sampling theorem )
            await asyncio.sleep(0.010)
            t_last_frame = None

            # Keep only the latest frame from the shared memory buffer
            while not self.stop_event.is_set() and not shared_memory.empty():
                t_last_frame = shared_memory.get_nowait()

            # If the shared memory buffer was not empty, update the image widget with the latest frame, otherwise no update to reduce load
            if t_last_frame is not None:
                try:
                    # Check if the frame is a signal to switch from INIT to RUNNING
                    if t_last_frame == "INITIALIZED":
                        self.update_camera_state(camera_type, CameraState.RUNNING)
                    else:
                        image_widget.src = "data:image/jpeg;base64," + t_last_frame
                        image_widget.update()
                        self.update_camera_state(camera_type, CameraState.RUNNING)
                except Exception:
                    # On any error, restore placeholder so the box stays defined
                    image_widget.src = self.__error_src
                    image_widget.update()
                    self.update_camera_state(camera_type, CameraState.ERROR)

            else:
                # If the process has terminated, display an error placeholder in the image box
                t_is_running = (
                    self.core_stereo_calibration.ueye_running()
                    if camera_type == CameraType.RGB
                    else self.core_stereo_calibration.prophesee_running()
                )

                if not t_is_running:
                    if image_widget.src != self.__error_src:
                        image_widget.src = self.__error_src
                        image_widget.update()
                        self.update_camera_state(camera_type, CameraState.ERROR)

                # If no frame received, manage the transition status
                elif self.camera_states[camera_type] == CameraState.INIT:
                    if image_widget.src != self.__initialization_src:
                        image_widget.src = self.__initialization_src
                        image_widget.update()

        return


def gui_build_and_run(page: ft.Page) -> None:
    """
    Function to build and run the Flet GUI.

    Args:
        ():

    Returns:
        ():
    """

    try:
        t_gui = StereoCalibrationGUI(page=page)
        t_gui.build_gui()

    except KeyboardInterrupt:
        t_gui.cleanup()

    return


if __name__ == "__main__":
    ft.run(main=gui_build_and_run)
