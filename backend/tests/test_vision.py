import asyncio
import io
import time

import pytest


def test_fake_model_returns_structured_report():
    from app.vision import VisionWorker

    def fake_model(data: bytes) -> dict:
        return {
            "flagged": True,
            "findings": [
                {"label": "pulmonary nodule", "score": 0.87, "bbox": [10, 20, 40, 40]},
                {"label": "consolidation", "score": 0.31},
            ],
            "model": "fake",
        }

    worker = VisionWorker(model=fake_model)
    report = asyncio.run(worker.analyze(b"fake-ct-bytes"))
    assert report["flagged"] is True
    assert report["findings"][0]["label"] == "pulmonary nodule"
    assert 0 <= report["findings"][0]["score"] <= 1
    assert report["model"] == "fake"


def test_vision_runs_off_loop_and_loop_stays_responsive():
    from app.vision import VisionWorker

    def slow_model(data: bytes) -> dict:
        time.sleep(0.25)
        return {"flagged": False, "findings": [], "model": "slow"}

    worker = VisionWorker(model=slow_model)

    async def scenario():
        lags = []

        async def heartbeat():
            last = time.perf_counter()
            while True:
                await asyncio.sleep(0.02)
                now = time.perf_counter()
                lags.append(now - last - 0.02)
                last = now

        beat = asyncio.create_task(heartbeat())
        report = await worker.analyze(b"x")
        beat.cancel()
        return report, lags

    report, lags = asyncio.run(scenario())
    assert report["model"] == "slow"
    # loop never blocked by the 250ms worker
    assert max(lags) < 0.1, f"event loop stalled {max(lags):.3f}s"


def test_synthetic_dicom_decodes_to_pixels():
    pydicom = pytest.importorskip("pydicom")
    from app.vision import decode_dicom_pixels

    ds = pydicom.dataset.Dataset()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds.SOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.Rows = 16
    ds.Columns = 16
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = (b"\x10\x00" * 256)
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)

    pixels = decode_dicom_pixels(buf.getvalue())
    assert pixels.shape == (16, 16)


def test_vision_analyze_endpoint_with_fake_model(monkeypatch):
    from fastapi.testclient import TestClient

    import app.vision as vision_mod
    from app.main import app

    monkeypatch.setattr(
        vision_mod,
        "get_vision_worker",
        lambda: vision_mod.VisionWorker(
            model=lambda d: {"flagged": False, "findings": [], "model": "fake"}
        ),
    )
    client = TestClient(app)
    r = client.post(
        "/api/vision/analyze",
        files={"file": ("scan.dcm", b"pretend-dicom", "application/dicom")},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["model"] == "fake"
    assert body["flagged"] is False


@pytest.mark.skipif(
    not __import__("os").environ.get("RUN_VISION_E2E"),
    reason="real BiomedCLIP weights: set RUN_VISION_E2E=1",
)
def test_real_biomedclip_zero_shot():
    from app.vision import VisionWorker

    worker = VisionWorker()  # no fake: loads BiomedCLIP
    report = asyncio.run(worker.analyze(b"not-a-real-image"))
    assert "findings" in report
