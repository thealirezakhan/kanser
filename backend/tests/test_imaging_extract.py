"""File extraction: DICOM headers, radiology report measurements, content classify."""

import io
import json

from fastapi.testclient import TestClient

from app.imaging import classify_imaging_modality, extract_dicom_header, extract_imaging_findings
from app.main import app
from app.standardize import classify_file

client = TestClient(app)


def _make_dicom_bytes() -> bytes:
    import pydicom
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    meta = Dataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset("x.dcm", {}, file_meta=meta, preamble=b"\x00" * 128)
    ds.Modality = "CT"
    ds.BodyPartExamined = "CHEST"
    ds.StudyDate = "20260115"
    ds.StudyDescription = "CT CHEST W CONTRAST"
    ds.SeriesDescription = "AXIAL 1.25mm"
    ds.Manufacturer = "DemoVendor"
    buf = io.BytesIO()
    pydicom.dcmwrite(buf, ds, enforce_file_format=True)
    return buf.getvalue()


def test_extract_dicom_header_from_real_dicom(tmp_path):
    p = tmp_path / "scan.dcm"
    p.write_bytes(_make_dicom_bytes())
    header = extract_dicom_header(p)
    assert header is not None
    assert header["modality"] == "CT"
    assert header["body_part"] == "CHEST"
    assert header["study_date"] == "20260115"
    assert header["study_description"] == "CT CHEST W CONTRAST"


def test_extract_dicom_header_rejects_non_dicom(tmp_path):
    p = tmp_path / "fake.dcm"
    p.write_bytes(b"this is not a dicom at all")
    assert extract_dicom_header(p) is None


def test_extract_imaging_findings_measurements():
    text = "RUL solid nodule measures 14 mm. A second 6x4 mm focus in the LLL."
    out = extract_imaging_findings(text)
    assert out["max_mm"] == 14.0
    assert "RUL" in out["lobes"]
    assert "LLL" in out["lobes"]


def test_extract_imaging_findings_empty():
    out = extract_imaging_findings("No focal lesion identified.")
    assert out["max_mm"] is None
    assert out["lobes"] == []


def test_classify_imaging_modality():
    assert classify_imaging_modality("CT chest with contrast, 14 mm nodule") == "ct"
    assert classify_imaging_modality("Chest x-ray shows no consolidation") == "cxr"
    assert classify_imaging_modality("random prose") == "ct"


def test_classify_pathology_report_content():
    assert classify_file("report.txt", "BIOPSY: adenocarcinoma, specimen from RUL") == "pathology"
    assert classify_file("report.txt", "CT CHEST: 12 mm RUL nodule") == "imaging_report"
    assert classify_file("report.txt", "patient tolerated procedure well") == "notes"


def test_ingest_dicom_extracts_header_into_case():
    cid = client.post("/api/cases", json={"patient_ref": "d1"}).json()["data"]["id"]
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("chest.dcm", _make_dicom_bytes(), "application/dicom")},
        data={"case_id": cid},
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["kind"] == "ct"
    got = client.get(f"/api/cases/{cid}").json()["data"]
    assert "ct" in got["modalities"]
    header = json.loads(got["metadata"]["dicom_header"])
    assert header["modality"] == "CT"
    assert header["study_date"] == "20260115"


def test_ingest_pathology_report_adds_modality():
    cid = client.post("/api/cases", json={"patient_ref": "d2"}).json()["data"]["id"]
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("path.txt", b"LUNG BIOPSY: adenocarcinoma, grade 2", "text/plain")},
        data={"case_id": cid},
    )
    assert r.status_code == 201
    assert r.json()["data"]["kind"] == "pathology"
    got = client.get(f"/api/cases/{cid}").json()["data"]
    assert "pathology" in got["modalities"]
    assert "adenocarcinoma" in got["metadata"]["pathology_report"]


def test_ingest_ct_report_extracts_measurements():
    cid = client.post("/api/cases", json={"patient_ref": "d3"}).json()["data"]["id"]
    r = client.post(
        "/api/documents/ingest",
        files={
            "file": (
                "ct_report.txt",
                b"CT CHEST: 17 mm solid nodule in the RUL, compared with 8 mm previously.",
                "text/plain",
            )
        },
        data={"case_id": cid},
    )
    assert r.status_code == 201
    assert r.json()["data"]["kind"] == "imaging_report"
    got = client.get(f"/api/cases/{cid}").json()["data"]
    assert "ct" in got["modalities"]
    findings = json.loads(got["metadata"]["imaging_findings"])
    assert findings["max_mm"] == 17.0
    assert "RUL" in findings["lobes"]


def test_readiness_preview_endpoint():
    r = client.post(
        "/api/readiness/preview",
        json={
            "patient_ref": "x",
            "modalities": ["ct"],
            "intake": {
                "age": 62,
                "sex": "male",
                "reason_for_presentation": "Abnormal CT",
                "imaging": ["ct_chest"],
            },
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["system_status"] in {
        "READY_FOR_DIAGNOSIS",
        "READY_FOR_STAGING",
        "READY_FOR_TREATMENT_PLANNING",
        "NOT_READY",
    }
    assert "diagnostic" in data["pathways"]
    assert data["pathways"]["diagnostic"]["ready"] is True
