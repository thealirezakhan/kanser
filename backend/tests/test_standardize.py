from app.standardize import classify_file, parse_labs, parse_vcf, standardize_case


def test_parse_labs_key_value_lines():
    text = "Hemoglobin: 13.5 g/dL\nCEA: 4.2 ng/mL\n"
    values, flags = parse_labs(text)
    assert values["hemoglobin"] == "13.5 g/dL"
    assert values["cea"] == "4.2 ng/mL"
    assert flags == []


def test_parse_labs_csv():
    text = "name,value,unit\nCEA,4.2,ng/mL\nAFP,10,ng/mL\n"
    values, flags = parse_labs(text)
    assert values["cea"] == "4.2 ng/mL"
    assert values["afp"] == "10 ng/mL"
    assert flags == []


def test_parse_labs_unparseable_flagged():
    values, flags = parse_labs("some random prose without any lab values")
    assert values == {}
    assert any(f["code"] == "labs_unparsed" for f in flags)


def test_parse_vcf_variants():
    text = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "7\t140453136\tEGFR\tA\tT\t.\t.\tGENE=EGFR\n"
        "12\t25245350\t.\tC\tG\t.\t.\tGENE=KRAS\n"
    )
    variants, flags = parse_vcf(text)
    genes = {v["gene"] for v in variants}
    assert genes == {"EGFR", "KRAS"}
    assert flags == []


def test_parse_vcf_without_header_flagged():
    variants, flags = parse_vcf("not really a vcf")
    assert variants == []
    assert any(f["code"] == "vcf_malformed" for f in flags)


def test_classify_file_extensions():
    assert classify_file("panel.vcf", "") == "genomics"
    assert classify_file("cbc.csv", "name,value") == "labs"
    assert classify_file("report.txt", "55yo smoker") == "notes"
    assert classify_file("scan.zip", "") is None


def test_standardize_case_unified_schema():
    case = {
        "patient_ref": "P1",
        "modalities": ["ct", "labs", "notes"],
        "clinical_notes": "55yo smoker, 2.1cm RUL nodule",
        "metadata": {"labs_raw": "CEA: 4.2 ng/mL"},
    }
    out = standardize_case(case)
    assert out["schema_version"] == "1.0"
    assert out["notes"] == "55yo smoker, 2.1cm RUL nodule"
    assert out["labs"]["values"]["cea"] == "4.2 ng/mL"
    assert out["imaging"] == []
    assert isinstance(out["quality_flags"], list)


def test_standardize_case_flags_declared_but_empty():
    case = {
        "patient_ref": "P2",
        "modalities": ["notes"],
        "clinical_notes": "",
        "metadata": {},
    }
    out = standardize_case(case)
    assert any(f["code"] == "notes_empty" for f in out["quality_flags"])


def test_standardize_case_genomics_from_vcf_metadata():
    case = {
        "patient_ref": "P3",
        "modalities": ["genomics"],
        "clinical_notes": "",
        "metadata": {
            "vcf": "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            "7\t1\tEGFR\tA\tT\t.\t.\tGENE=EGFR\n",
        },
    }
    out = standardize_case(case)
    assert {v["gene"] for v in out["genomics"]["variants"]} == {"EGFR"}
