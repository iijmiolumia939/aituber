"""OBS Camera Controller — scene/source switching and screenshot capture.

FR-CAM-01..03: Allows YUI.A to switch OBS scenes (= virtual cameras) and
capture self-view screenshots via GetSourceScreenshot.
Issue: #18 E-8. Virtual Camera + Avatar Self-Perception.

References:
  obs-websocket v5 SetCurrentProgramScene, SetSceneItemEnabled,
  GetSourceScreenshot: https://github.com/obsproject/obs-websocket
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# ── Protocol for obs WS client ────────────────────────────────────────


class ObsWsClient(Protocol):
    """Typing shim — compatible with obsws_python.ReqClient or mock."""

    def call(self, request: Any) -> Any: ...


# ── Data models ───────────────────────────────────────────────────────


@dataclass
class CameraScene:
    """Mapping of a logical camera name to its OBS scene/source.

    FR-CAM-01.
    """

    name: str           # e.g. "A", "B", "C"
    scene_name: str     # OBS scene name (SetCurrentProgramScene)
    source_name: str    # OBS source name within scene (for screenshot / visibility toggle)


@dataclass
class ScreenshotResult:
    """Result from GetSourceScreenshot.

    FR-CAM-03.
    """

    camera_name: str
    image_b64: str      # base64-encoded PNG
    width: int
    height: int
    success: bool
    error: str = ""


class OBSCameraController:
    """Control OBS camera/scene switching and capture self-view frames.

    FR-CAM-01..03.

    Args:
        cameras: ordered list of CameraScene definitions.
        client: obsws-python ReqClient or mock for testing.
        screenshot_width: width in pixels for GetSourceScreenshot.
        screenshot_height: height in pixels for GetSourceScreenshot.
    """

    def __init__(
        self,
        cameras: list[CameraScene] | None = None,
        client: ObsWsClient | None = None,
        screenshot_width: int = 320,
        screenshot_height: int = 180,
    ) -> None:
        # Default 3-camera setup
        self._cameras: dict[str, CameraScene] = {}
        for cam in (cameras or [
            CameraScene("A", "CamA_正面", "UnityCapture_A"),
            CameraScene("B", "CamB_斜め", "UnityCapture_B"),
            CameraScene("C", "CamC_引き", "UnityCapture_C"),
        ]):
            self._cameras[cam.name] = cam

        self._client = client
        self._active_camera: str = "A"
        self._screenshot_width = screenshot_width
        self._screenshot_height = screenshot_height

    # ── Camera control ────────────────────────────────────────────────

    @property
    def active_camera(self) -> str:
        return self._active_camera

    @property
    def available_cameras(self) -> list[str]:
        return list(self._cameras.keys())

    def switch_to_camera(self, name: str) -> bool:
        """Switch active OBS scene to match the named camera.

        FR-CAM-01, FR-CAM-02.
        Returns True on success.
        """
        if name not in self._cameras:
            logger.warning("[OBSCam] Unknown camera: %s", name)
            return False
        cam = self._cameras[name]
        if self._client is None:
            logger.warning("[OBSCam] No OBS client — simulating switch to %s", name)
            self._active_camera = name
            return True
        try:
            import obsws_python as obs  # type: ignore[import]
            self._client.call(obs.requests.SetCurrentProgramScene(scene_name=cam.scene_name))
            self._active_camera = name
            logger.info("[OBSCam] Switched to camera %s (scene=%s)", name, cam.scene_name)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[OBSCam] switch_to_camera failed: %s", exc)
            return False

    # ── Screenshot / self-perception ─────────────────────────────────

    def capture_self_view(self, camera_name: str | None = None) -> ScreenshotResult:
        """Capture a frame from the specified (or active) camera source.

        FR-CAM-03: Returns base64 PNG via GetSourceScreenshot.
        NFR-CAM-01: Uses low resolution (320×180) to avoid impacting stream quality.
        """
        name = camera_name or self._active_camera
        if name not in self._cameras:
            return ScreenshotResult(
                camera_name=name,
                image_b64="",
                width=0,
                height=0,
                success=False,
                error=f"Unknown camera: {name}",
            )

        source = self._cameras[name].source_name
        if self._client is None:
            return ScreenshotResult(
                camera_name=name,
                image_b64="",
                width=0,
                height=0,
                success=False,
                error="No OBS client",
            )

        try:
            import obsws_python as obs  # type: ignore[import]
            resp = self._client.call(
                obs.requests.GetSourceScreenshot(
                    source_name=source,
                    image_format="png",
                    image_width=self._screenshot_width,
                    image_height=self._screenshot_height,
                )
            )
            image_data = getattr(resp, "image_data", "")
            # Strip "data:image/png;base64," prefix if present
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            return ScreenshotResult(
                camera_name=name,
                image_b64=image_data,
                width=self._screenshot_width,
                height=self._screenshot_height,
                success=bool(image_data),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[OBSCam] capture_self_view failed: %s", exc)
            return ScreenshotResult(
                camera_name=name,
                image_b64="",
                width=0,
                height=0,
                success=False,
                error=str(exc),
            )
