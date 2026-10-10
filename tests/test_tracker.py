"""Prueba de integración con MediaPipe real usando fotos de muestra de Google.

Necesita internet la primera vez (descarga modelos e imágenes); si no hay, se omite.
"""
import urllib.request

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("mediapipe")

from sofia.config import Config  # noqa: E402
from sofia.gestures import HandController, HeadController  # noqa: E402
from sofia.preview import draw  # noqa: E402

IMAGES = {
    "hand": "https://storage.googleapis.com/mediapipe-tasks/hand_landmarker/woman_hands.jpg",
    "face": "https://storage.googleapis.com/mediapipe-assets/business-person.png",
}


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    d = tmp_path_factory.mktemp("assets")
    imgs = {}
    try:
        for kind, url in IMAGES.items():
            path = d / url.rsplit("/", 1)[-1]
            urllib.request.urlretrieve(url, path)
            imgs[kind] = cv2.imread(str(path))
        from sofia.tracker import ensure_model

        for kind in ("hand", "face"):
            ensure_model(kind, d)
    except Exception as exc:  # sin red o sin bibliotecas gráficas
        pytest.skip(f"no se pudieron preparar los recursos: {exc}")
    return d, imgs


def test_hand_tracker_end_to_end(assets):
    from sofia.tracker import Tracker

    model_dir, imgs = assets
    tracker = Tracker("hand", model_dir=model_dir)
    try:
        obs = None
        for _ in range(3):  # modo video: varios cuadros seguidos
            obs = tracker.process(imgs["hand"])
        assert obs is not None and len(obs.landmarks) == 21
        assert obs.handedness in ("left", "right")
        ctrl = HandController(Config(), (1440, 900))
        actions, status = ctrl.update(obs, 0.0)
        assert status.pointer is not None
        img = draw(imgs["hand"], Config(), status, obs.landmarks, (1440, 900), False, "hand")
        assert img.shape == imgs["hand"].shape
    finally:
        tracker.close()


def test_face_tracker_end_to_end(assets):
    from sofia.tracker import Tracker

    model_dir, imgs = assets
    tracker = Tracker("face", model_dir=model_dir)
    try:
        obs = tracker.process(imgs["face"])
        assert obs is not None and len(obs.landmarks) >= 468
        assert "jawOpen" in obs.blendshapes
        ctrl = HeadController(Config(), (1440, 900))
        _, status = ctrl.update(obs, 0.0)
        assert status.pointer == pytest.approx((719.5, 449.5), abs=1)  # primera posición = centro
        assert tracker.process(np.zeros((480, 640, 3), np.uint8)) is None
    finally:
        tracker.close()


class FakeCamera:
    def __init__(self, frames):
        self.frames = list(frames)

    def isOpened(self):
        return True

    def read(self):
        if not self.frames:
            raise KeyboardInterrupt  # termina el bucle de la app
        return True, self.frames.pop(0)

    def release(self):
        pass


class FakeMouse:
    def __init__(self):
        self.calls = []

    def screen_size(self):
        return (1440, 900)

    def __getattr__(self, name):
        return lambda *a: self.calls.append((name, *a))


def test_app_loop_moves_mouse(assets, monkeypatch, tmp_path):
    import sofia.app as app_mod
    import sofia.tracker as tracker_mod

    model_dir, imgs = assets
    monkeypatch.setattr(tracker_mod, "config_dir", lambda: model_dir.parent / model_dir.name.replace("assets", "cfg"))
    monkeypatch.setattr(tracker_mod, "ensure_model", lambda kind, d=None: model_dir / f"{kind}_landmarker.task")
    mouse = FakeMouse()
    monkeypatch.setattr(app_mod, "create_mouse", lambda: mouse)
    monkeypatch.setattr(app_mod, "open_camera", lambda i: FakeCamera([imgs["hand"]] * 5))
    cfg = Config(show_preview=False, sounds=False)
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    app = app_mod.App(cfg)
    assert app.run() == 0
    assert any(c[0] == "move" for c in mouse.calls)
    # Cambiar de modo (tecla m) hasta cabeza crea el detector de cara.
    app.handle_key(ord("m"))
    app.handle_key(ord("m"))
    assert cfg.mode == "head" and app.tracker.kind == "face"
    app.tracker.close()
