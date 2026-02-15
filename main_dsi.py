#!/usr/bin/env python3
"""
OpenClaw CyberDeck - DSI Display Edition
Main entry point for 7" DSI touchscreen.

Unified display with Molty, activity feed, and command buttons.
Integrates with hardware server for LED control and presence detection.
Auto-detects actual screen resolution at runtime.
"""

import argparse
import os
import signal
import sys
import threading
import time
from datetime import datetime

# Ensure X11 display is set before pygame import (avoids offscreen driver)
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("[Main] WARNING: pygame not available - display will not work")

import config_dsi as config
from display_dsi import DSIDisplay
from touch_dsi import TouchHandler, ButtonHitTester
from hardware_client import HardwareClient, PresenceZone
from openclaw_bridge import OpenClawBridge
from openclaw_config import OpenClawConfig
from websocket_client import ConnectionState
from ui.molty import MoltyState


class DSICommandCenter:
    """Main application coordinator for DSI display version."""

    def __init__(self, demo_mode: bool = False, openclaw_config: OpenClawConfig = None):
        self.demo_mode = demo_mode
        self.openclaw_config = openclaw_config or OpenClawConfig.load()
        self.running = False

        # Screen size will be detected at init time
        self.screen_size = (config.DSI_DISPLAY["width"], config.DSI_DISPLAY["height"])

        # Components (created after resolution detection in initialize())
        self.display = None
        self.touch = None
        self.hardware = HardwareClient(demo_mode=demo_mode)
        self.bridge = OpenClawBridge(demo_mode=demo_mode, config=self.openclaw_config)

        # Pygame display
        self.screen = None
        self.clock = None

        # State tracking
        self._was_connected = False
        self._active_button_id = None
        self._molty_state_timer = None

        # Demo mode state
        self._demo_action_index = 0

    def _setup_bridge_callbacks(self):
        """Configure bridge event handlers."""

        def on_notification(notification):
            """Forward notifications to activity feed and update Molty state."""
            activity_type = "tool"
            status = "done"

            if "Starting" in notification.message or notification.title.startswith("Tool:"):
                activity_type = "tool"
                status = "running"
                self.display.set_molty_state(MoltyState.WORKING)
                self.hardware.set_led_state("working")
            elif "Completed" in notification.message or "Success" in notification.message:
                activity_type = "status"
                status = "done"
                self._set_molty_state_with_timer(MoltyState.SUCCESS, 2.0)
                self.hardware.set_led_state("success")
            elif "Failed" in notification.message or "Error" in notification.message:
                activity_type = "error"
                status = "fail"
                self._set_molty_state_with_timer(MoltyState.ERROR, 3.0)
                self.hardware.set_led_state("error")
            elif notification.type == "info":
                activity_type = "notification"

            self.display.add_activity(
                activity_type,
                notification.title,
                notification.message,
                status
            )

            # Update button state
            if self._active_button_id:
                if status == "done":
                    self.display.set_button_state(self._active_button_id, "success")
                    self._reset_button_after_delay(self._active_button_id, 1.0)
                elif status == "fail":
                    self.display.set_button_state(self._active_button_id, "error")
                    self._reset_button_after_delay(self._active_button_id, 1.5)

        def on_connection_change(state):
            """Handle connection state changes."""
            if state == ConnectionState.CONNECTED:
                if not self._was_connected:
                    print("[Main] Connected to OpenClaw")
                    self.display.add_activity("status", "Connected", "OpenClaw online")
                    self.display.set_molty_state(MoltyState.IDLE)
                    self.hardware.set_led_state("connected")
                self._was_connected = True
            elif state == ConnectionState.DISCONNECTED:
                if self._was_connected:
                    print("[Main] Disconnected from OpenClaw")
                    self.display.add_activity("error", "Disconnected", "Connection lost")
                    self.display.set_molty_state(MoltyState.ERROR)
                    self.hardware.set_led_state("disconnected")
                self._was_connected = False
            elif state == ConnectionState.RECONNECTING:
                print("[Main] Reconnecting to OpenClaw...")
                self.display.add_activity("notification", "Reconnecting...", "")
                self.display.set_molty_state(MoltyState.THINKING)

        def on_message_chunk(msg_id, chunk):
            """Handle streaming message chunks."""
            self.display.set_molty_state(MoltyState.LISTENING)

        def on_status_update(status):
            """Handle status updates from OpenClaw."""
            if status.get("is_streaming"):
                self.display.set_molty_state(MoltyState.WORKING)
            elif status.get("current_task") == "Idle":
                self.display.set_molty_state(MoltyState.IDLE)

            # Update connection info
            self.display.set_connection_status(
                connected=status.get("connected", False),
                model=status.get("model", ""),
                cost=status.get("api_cost", 0.0)
            )

        def on_message_complete(message):
            """Handle completed response from OpenClaw."""
            content = message.get("content", "")
            self.display.add_activity("status", "Response", content, "done")

            self._set_molty_state_with_timer(MoltyState.SUCCESS, 2.0)
            self.hardware.set_led_state("success")

            if self._active_button_id:
                self.display.set_button_state(self._active_button_id, "success")
                self._reset_button_after_delay(self._active_button_id, 1.0)
                self._active_button_id = None

        self.bridge.set_callbacks(
            on_message_chunk=on_message_chunk,
            on_message_complete=on_message_complete,
            on_notification=on_notification,
            on_status_change=on_status_update,
            on_connection_change=on_connection_change,
        )

    def _set_molty_state_with_timer(self, state: MoltyState, delay_seconds: float):
        """Set Molty state and schedule return to IDLE."""
        self.display.set_molty_state(state)

        if self._molty_state_timer:
            self._molty_state_timer.cancel()

        def return_to_idle():
            if self.display.get_molty_state() == state:
                self.display.set_molty_state(MoltyState.IDLE)
                self.hardware.set_led_state("idle")

        self._molty_state_timer = threading.Timer(delay_seconds, return_to_idle)
        self._molty_state_timer.daemon = True
        self._molty_state_timer.start()

    def _reset_button_after_delay(self, button_id: str, delay_seconds: float):
        """Reset button to normal state after delay."""
        def reset():
            self.display.reset_button(button_id)
            if self._active_button_id == button_id:
                self._active_button_id = None

        timer = threading.Timer(delay_seconds, reset)
        timer.daemon = True
        timer.start()

    def _setup_touch_callbacks(self):
        """Configure touch event handlers."""

        def on_tap(x, y):
            """Handle tap events."""
            print(f"[Main] Tap at ({x}, {y})")

            # Dismiss overlay if visible (consumes tap)
            if self.display.is_overlay_visible():
                self.display.dismiss_overlay()
                return

            # Check if tap hits an activity entry with detail text
            entry = self.display.find_activity_entry(x, y)
            if entry and entry.detail:
                self.display.show_overlay(entry)
                return

            button = self.display.find_button(x, y)

            if button:
                print(f"[Main] Button tapped: {button['id']} - {button['label']}")

                # Visual feedback
                self.display.set_button_state(button["id"], "pressed")

                if self.bridge.is_connected():
                    self.display.set_button_state(button["id"], "running")
                    self._active_button_id = button["id"]

                    self.display.add_activity(
                        "tool",
                        f"Command: {button['label']}",
                        button["command"],
                        "running"
                    )
                    self.display.set_molty_state(MoltyState.WORKING)
                    self.hardware.set_led_state("working")

                    # Send command
                    self.bridge.send_message(button["command"])

                    # Timeout handler
                    active_btn = button["id"]
                    def command_timeout():
                        if self._active_button_id == active_btn:
                            print(f"[Main] Command timeout for {active_btn}")
                            self.display.set_molty_state(MoltyState.IDLE)
                            self.display.update_latest_activity_status("done")
                            self.display.reset_button(active_btn)
                            self._active_button_id = None
                            self.hardware.set_led_state("idle")

                    timer = threading.Timer(15.0, command_timeout)
                    timer.daemon = True
                    timer.start()

                else:
                    # Not connected
                    self.display.set_button_state(button["id"], "error")
                    self._reset_button_after_delay(button["id"], 1.0)
                    self.display.add_activity(
                        "error",
                        "Not Connected",
                        "Cannot send command",
                        "fail"
                    )
                    self.display.set_molty_state(MoltyState.ERROR)
                    self.hardware.set_led_state("error")

            else:
                # Tap outside buttons - check for connection/cost area tap
                if x < config.LAYOUT["molty_panel_width"] and y < config.LAYOUT["button_panel_y_offset"]:
                    # Tapping Molty/label area - reconnect if disconnected
                    if not self.bridge.is_connected():
                        print("[Main] Molty area tap - forcing reconnect")
                        self.bridge.force_reconnect()
                        self.display.add_activity("notification", "Reconnecting...", "")
                        self.display.set_molty_state(MoltyState.THINKING)

        def on_long_press(x, y):
            """Handle long press events."""
            print(f"[Main] Long press at ({x}, {y})")

            # Dismiss overlay if visible (consumes long press)
            if self.display.is_overlay_visible():
                self.display.dismiss_overlay()
                return

            if x < config.LAYOUT["molty_panel_width"] and y < config.LAYOUT["button_panel_y_offset"]:
                # Long press on Molty/status area (above buttons) - force reconnect
                print("[Main] Molty area long press - forcing reconnect")
                self.bridge.force_reconnect()
            else:
                # Long press elsewhere - cancel current operation
                if self.bridge.is_connected() and self._active_button_id:
                    print("[Main] Long press - cancelling current task")
                    self.bridge.cancel_current()
                    self.display.reset_all_buttons()
                    self._active_button_id = None
                    self.display.add_activity("notification", "Cancelled", "Operation cancelled")
                    self.display.set_molty_state(MoltyState.IDLE)
                    self.hardware.set_led_state("idle")

        self.touch.on_tap = on_tap
        self.touch.on_long_press = on_long_press

    def _setup_presence_callback(self):
        """Configure presence change handler."""

        def on_presence_change(zone: PresenceZone):
            if zone == PresenceZone.AWAY:
                print("[Main] User away - dimming display")
            elif zone == PresenceZone.NEAR:
                print("[Main] User present - full brightness")

        self.hardware.set_presence_callback(on_presence_change)

    def initialize(self) -> bool:
        """Initialize all components."""
        print("=" * 60)
        print("OpenClaw CyberDeck - DSI Display Edition")
        print(f"Mode: {'Demo' if self.demo_mode else 'Production'}")
        if not self.demo_mode:
            print(f"OpenClaw URL: {self.openclaw_config.url}")
        print("=" * 60)

        # Initialize pygame and detect actual screen resolution
        if PYGAME_AVAILABLE:
            pygame.init()

            # Detect actual screen resolution
            display_info = pygame.display.Info()
            detected_w = display_info.current_w
            detected_h = display_info.current_h
            print(f"[Main] Detected screen resolution: {detected_w}x{detected_h}")

            # Set up display
            display_flags = 0
            if config.DSI_DISPLAY["fullscreen"]:
                display_flags |= pygame.FULLSCREEN

            try:
                if config.DSI_DISPLAY["fullscreen"]:
                    # Use (0, 0) with FULLSCREEN to get native resolution
                    self.screen = pygame.display.set_mode((0, 0), display_flags)
                else:
                    self.screen = pygame.display.set_mode(
                        (config.DSI_DISPLAY["width"], config.DSI_DISPLAY["height"]),
                        display_flags
                    )

                # Get actual surface size (confirms what we got)
                actual_w, actual_h = self.screen.get_size()
                self.screen_size = (actual_w, actual_h)

                pygame.display.set_caption("OpenClaw CyberDeck")
                pygame.mouse.set_visible(False)  # Hide cursor on touch screen
                print(f"[Main] Display initialized: {actual_w}x{actual_h}")
            except pygame.error as e:
                print(f"[Main] Display error: {e}")
                if not self.demo_mode:
                    return False

            self.clock = pygame.time.Clock()
        else:
            print("[Main] WARNING: pygame not available")
            if not self.demo_mode:
                return False

        # Create display and touch components with actual screen size
        self.display = DSIDisplay(demo_mode=self.demo_mode, screen_size=self.screen_size)
        self.touch = TouchHandler(screen_size=self.screen_size)

        # Setup callbacks
        self._setup_bridge_callbacks()
        self._setup_touch_callbacks()
        self._setup_presence_callback()

        # Initialize bridge
        if not self.bridge.connect():
            print("[Main] WARNING: Bridge connection failed")
            self.display.add_activity("warning", "Connection Failed", "Will retry automatically")

        # Start hardware monitoring
        if not self.demo_mode:
            self.hardware.start_presence_monitoring()

        # Initialize display state
        if self.demo_mode:
            print("[Main] Seeding demo state...")
            self.display.add_activity("status", "System Online", "DSI Display Active")
            self.display.add_activity("notification", "Demo Mode", "Simulated data")
            self.display.set_molty_state(MoltyState.IDLE)
            self.display.set_connection_status(True, "demo-model", 0.0)
            self.hardware.set_led_state("idle")
        else:
            self.display.add_activity("status", "Initializing", "Connecting to OpenClaw...")

        print("[Main] Initialization complete")
        return True

    def run(self):
        """Main event loop."""
        self.running = True
        print("[Main] Starting main loop")

        target_fps = config.DSI_DISPLAY["fps"]

        while self.running:
            try:
                # Handle pygame events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.running = False
                        elif event.key == pygame.K_q:
                            self.running = False
                    else:
                        # Process touch/mouse events
                        self.touch.process_event(event)

                # Check for long press timeout
                self.touch.check_long_press()

                # Update bridge status
                if self.demo_mode:
                    self._demo_update()
                else:
                    status = self.bridge.get_status()
                    self.display.set_connection_status(
                        connected=status.get("connected", False),
                        model=status.get("model", ""),
                        cost=status.get("api_cost", 0.0)
                    )

                # Render display
                if self.screen:
                    surface = self.display.render_to_surface()
                    self.screen.blit(surface, (0, 0))
                    pygame.display.flip()

                # Frame rate control
                if self.clock:
                    self.clock.tick(target_fps)

            except Exception as e:
                print(f"[Main] Loop error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.1)

        print("[Main] Main loop stopped")

    def _demo_update(self):
        """Update demo state periodically."""
        import random

        # Randomly add activities
        if random.random() > 0.995:
            mock_actions = [
                ("tool", "Checked inbox", "3 new messages"),
                ("tool", "Running backup", "rsync to NAS"),
                ("status", "Focus mode", "Notifications paused"),
                ("notification", "Reminder", "Meeting in 15 min"),
            ]
            action = random.choice(mock_actions)
            self.display.add_activity(action[0], action[1], action[2])
            self._demo_action_index += 1

        # Update connection status
        self.display.set_connection_status(
            connected=True,
            model="claude-opus (demo)",
            cost=self._demo_action_index * 0.001
        )

    def stop(self):
        """Signal to stop the main loop."""
        print("\n[Main] Shutting down...")
        self.running = False

        if self._molty_state_timer:
            self._molty_state_timer.cancel()

    def cleanup(self):
        """Clean up all resources."""
        self.hardware.cleanup()
        self.bridge.cleanup()
        self.display.cleanup()

        if PYGAME_AVAILABLE:
            pygame.quit()

        print("[Main] Cleanup complete")


def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw CyberDeck - DSI Display Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main_dsi.py --demo                    Run in demo mode
  python main_dsi.py --url ws://192.168.1.x:18789  Connect to OpenClaw
  python main_dsi.py --windowed                Run windowed (not fullscreen)

Hardware Integration:
  Expects hardware server running at localhost:5000 with endpoints:
    /led          - LED control (r, g, b, mode)
    /presence     - Presence detection (zone)
    /brightness   - Display brightness (level)
    /voice/speak  - TTS (text, priority)

  Start hardware server:
    cd ~/Projects/dashboard/hardware && python server.py &
"""
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with simulated data"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="OpenClaw WebSocket URL"
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Authentication password"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to config file"
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in windowed mode (not fullscreen)"
    )
    args = parser.parse_args()

    # Override fullscreen setting
    if args.windowed:
        config.DSI_DISPLAY["fullscreen"] = False

    # Load configuration
    openclaw_config = OpenClawConfig.load(
        cli_url=args.url,
        cli_password=args.password,
        config_path=args.config,
    )

    # Create application
    app = DSICommandCenter(
        demo_mode=args.demo,
        openclaw_config=openclaw_config
    )

    # Setup signal handlers
    def signal_handler(sig, frame):
        app.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize and run
    if not app.initialize():
        print("[Main] Initialization failed")
        sys.exit(1)

    try:
        app.run()
    finally:
        app.cleanup()

    print("[Main] Goodbye!")


if __name__ == "__main__":
    main()
