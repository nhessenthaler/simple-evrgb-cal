#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: flet_controls.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides custom flet controls for the GUI.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from dataclasses import field
import flet as ft


@ft.control
class BlueCustomButton(ft.Button):
    """Custom button class for a standard blue button."""

    color: ft.Colors = ft.Colors.WHITE
    bgcolor: ft.Colors = "#004f9e"
    style: ft.ButtonStyle = field(
        default_factory=lambda: ft.ButtonStyle(
            padding=20,
            shape=ft.RoundedRectangleBorder(radius=4),
            mouse_cursor={
                ft.ControlState.HOVERED: ft.MouseCursor.CLICK,
                ft.ControlState.DEFAULT: ft.MouseCursor.BASIC,
            },
            elevation=8,
            overlay_color="#003f8e",
            text_style=ft.TextStyle(weight="bold", size=18),
        )
    )


@ft.control
class RedCustomButton(ft.Button):
    """Custom button class for a standard red button."""

    color: ft.Colors = ft.Colors.WHITE
    bgcolor: ft.Colors = "#e30613"
    style: ft.ButtonStyle = field(
        default_factory=lambda: ft.ButtonStyle(
            padding=20,
            shape=ft.RoundedRectangleBorder(radius=4),
            mouse_cursor={
                ft.ControlState.HOVERED: ft.MouseCursor.CLICK,
                ft.ControlState.DEFAULT: ft.MouseCursor.BASIC,
            },
            elevation=8,
            overlay_color="#c20510",
            text_style=ft.TextStyle(weight="bold", size=18),
        )
    )


@ft.control
class BlueCustomIconButton(ft.IconButton):
    """Custom button class for a standard blue button."""

    color: ft.Colors = ft.Colors.WHITE
    icon_color = ft.Colors.WHITE
    bgcolor: ft.Colors = "#004f9e"
    style: ft.ButtonStyle = field(
        default_factory=lambda: ft.ButtonStyle(
            padding=12,
            shape=ft.RoundedRectangleBorder(radius=4),
            mouse_cursor={
                ft.ControlState.HOVERED: ft.MouseCursor.CLICK,
                ft.ControlState.DEFAULT: ft.MouseCursor.BASIC,
            },
            elevation=8,
            overlay_color="#003f8e",
            text_style=ft.TextStyle(weight="bold", size=18),
        )
    )


@ft.control
class BlueCustomMediumText(ft.Text):
    """Custom text class for a standard, medium size blue text."""

    color: ft.Colors = "#004f9e"
    weight: ft.FontWeight = ft.FontWeight.BOLD
    size: int = 32
    text_align: ft.TextAlign = ft.TextAlign.CENTER


@ft.control
class BlueCustomImageContainer(ft.Container):
    """Custom container class for displaying images with a fixed size and a placeholder in case of errors."""

    bgcolor: ft.Colors = ft.Colors.WHITE
    border_radius: int = 4
    padding: int = 10
    shadow: ft.BoxShadow = field(
        default_factory=lambda: ft.BoxShadow(blur_radius=8, color="#004f9e", offset=ft.Offset(0, 4))
    )


@ft.control
class CountdownTimer(ft.Container):
    """Custom container class for a countdown timer widget with a progress ring and text."""

    def __init__(
        self,
        countdown_value: int,
        countdown_max: int,
        label_text: str,
        automatic: bool = False,
        error: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.countdown_value = countdown_value
        self.countdown_max = countdown_max
        self.automatic = automatic
        self.error = error
        self.label_text = label_text

        # Initialize properties to be available right after instantiation
        self.height = 55
        self.width = 300
        self.alignment = ft.Alignment.CENTER
        self.padding = 6
        self.bgcolor = ft.Colors.WHITE
        self.shadow = ft.BoxShadow(blur_radius=8, color="#004f9e", offset=ft.Offset(0, 4))
        self.border_radius = 0
        self.expand = False

    # ##### PRIVATE METHODS #####
    def _update_visibility(self) -> None:
        """
        Method to update the visibility of the countdown timer based on the automatic and error states.

        Args:
            ():

        Returns:
            ():
        """

        if not self.automatic or self.error:
            self.visible = False
        else:
            self.visible = True

        return

    # ##### PUBLIC METHODS #####
    def build(self) -> None:
        """
        Method to build the countdown timer widget, including the label, progress ring, and timer text.

        Args:
            ():

        Returns:
            ():
        """

        self.label = ft.Text(
            self.label_text,
            size=15,
            color="#004f9e",
            weight="bold",
            text_align=ft.TextAlign.CENTER,
        )

        self.progress_ring = ft.ProgressRing(
            value=0.0,
            width=43,
            height=43,
            color="#004f9e",
            bgcolor="#a9a9a9",
        )

        self.timer_text = ft.Text(
            value=f"{self.countdown_value:.1f} s",
            size=15,
            weight="bold",
            color="#004f9e",
            text_align=ft.TextAlign.CENTER,
        )

        self.timer_container = ft.Container(
            content=self.timer_text,
            alignment=ft.Alignment.CENTER,
            width=43,
            height=43,
            padding=0,
            bgcolor="transparent",
        )

        self.content = ft.Row(
            [
                self.label,
                ft.Stack(
                    [
                        self.progress_ring,
                        self.timer_container,
                    ],
                    alignment=ft.Alignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
        )

        self._update_visibility()

        return

    def update_timer(self, value: float, max_value: float) -> None:
        """
        Method to update the countdown timer value and progress ring.

        Args:
            value (float): The current countdown value.
            max_value (float): The maximum countdown value for calculating the progress.

        Returns:
            ():
        """

        self.countdown_value = value
        self.countdown_max = max_value
        self.timer_text.value = f"{value:.1f} s"
        if max_value > 0:
            self.progress_ring.value = 1.0 - (value / max_value)
        else:
            self.progress_ring.value = 0.0
        self.update()

        return
