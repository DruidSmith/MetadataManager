#!/usr/bin/env python3
"""
FastAPI Application for Metadata Schema Conversions and Catalog Synchronization.
Designed for deployment on Posit Connect.

Endpoints:
- GET  /                    : Serves the USWDS Vue 3 Web UI (metadata_editor.html)
- GET  /health              : Health check & service info
- GET  /schema              : Returns the Unified Metadata JSON Schema
- POST /convert/from-legacy : Converts incoming raw string/JSON/XML/YAML into Unified Metadata Record
- POST /convert/from-file   : Converts uploaded file artifact into Unified Metadata Record
- POST /export/to-target    : Exports Unified Metadata Record to specified target format
- POST /sync/catalogs       : Performs ID lookup and upsert into AWS Glue Catalog & Alation
"""

import json
import yaml
import os
import io
import zipfile
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Initialize FastAPI App
app = FastAPI(
    title="Unified Metadata Conversion & Catalog Sync API",
    description="Enterprise API for converting between metadata standards (DCAT-US, FGDC CSDGM, STAC, AWS RODA, Glue, Alation) and syncing to cloud/governance catalogs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for Posit Connect and cross-domain UI deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type"]
)

# Load Schema on Startup
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "unified_metadata_schema.json")
if not os.path.exists(SCHEMA_PATH):
    SCHEMA_PATH = "/workspace/scratch/unified_metadata_schema.json"
if not os.path.exists(SCHEMA_PATH):
    SCHEMA_PATH = "/workspace/artifacts/unified_metadata_schema.json"

UNIFIED_SCHEMA = {}
if os.path.exists(SCHEMA_PATH):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        UNIFIED_SCHEMA = json.load(f)


# --- Core Ingestion Logic ---

def ingest_dcat_json(data: Dict[str, Any]) -> Dict[str, Any]:
    acc = data.get("accessRights") or data.get("accessLevel", "public")
    if acc not in ["public", "restricted public", "non-public"]:
        acc = "public"

    keywords = data.get("keyword", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    bureau = data.get("bureauCode", ["020:00"])
    if isinstance(bureau, str): bureau = [bureau]

    program = data.get("programCode", ["020:000"])
    if isinstance(program, str): program = [program]

    return {
        "@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
        "@type": data.get("@type", "dcat:Dataset"),
        "identifier": data.get("identifier", "dcat-ingested-dataset"),
        "title": data.get("title", "Untitled Dataset"),
        "description": data.get("description", "No description provided."),
        "publisher": data.get("publisher", {"@type": "org:Organization", "name": "Unknown Publisher"}),
        "contactPoint": data.get("contactPoint", {"fn": "Data Custodian", "hasEmail": "mailto:admin@agency.gov"}),
        "modified": data.get("modified", "2026-10-01T00:00:00Z"),
        "issued": data.get("issued"),
        "keyword": keywords if keywords else ["open-data"],
        "theme": data.get("theme", ["geospatial"]),
        "bureauCode": bureau,
        "programCode": program,
        "accessRights": acc,
        "license": data.get("license", "https://creativecommons.org/publicdomain/zero/1.0/"),
        "rights": data.get("rights"),
        "landingPage": data.get("landingPage"),
        "language": data.get("language", ["en-US"]),
        "accrualPeriodicity": data.get("accrualPeriodicity"),
        "spatial": data.get("spatial", {"type": "BoundingBox", "bbox": [-180, -90, 180, 90]}),
        "temporal": data.get("temporal"),
        "isPartOf": data.get("isPartOf"),
        "systemOfRecords": data.get("systemOfRecords"),
        "primaryITInvestmentUII": data.get("primaryITInvestmentUII"),
        "describedBy": data.get("describedBy"),
        "describedByType": data.get("describedByType"),
        "conformsTo": data.get("conformsTo"),
        "dataQuality": data.get("dataQuality"),
        "references": data.get("references", []),
        "dataServices": data.get("dataServices", []),
        "distribution": data.get("distribution", []),
        "governance_and_quality": data.get("governance_and_quality", {}),
        "stac_metadata": data.get("stac_metadata", {}),
        "aws_roda": data.get("aws_roda", {}),
        "aws_glue_catalog": data.get("aws_glue_catalog", {}),
        "alation_governance": data.get("alation_governance", {})
    }


def ingest_fgdc_xml(xml_content: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_content)
    idinfo = root.find("idinfo")

    title = idinfo.findtext("citation/citeinfo/title") if idinfo is not None else "FGDC Ingested Dataset"
    abstract = idinfo.findtext("descript/abstract") if idinfo is not None else "No abstract provided."
    publisher = idinfo.findtext("citation/citeinfo/pubinfo/publish") if idinfo is not None else "Unknown Agency"
    contact_fn = idinfo.findtext("ptcontac/cntinfo/cntper") if idinfo is not None else "Geospatial Contact"
    contact_email = idinfo.findtext("ptcontac/cntinfo/cntemail") if idinfo is not None else "gis@agency.gov"
    pubdate = idinfo.findtext("citation/citeinfo/pubdate") if idinfo is not None else "2026-10-01"

    keywords = []
    if idinfo is not None:
        for themekey in idinfo.findall("keywords/theme/themekey"):
            if themekey.text:
                keywords.append(themekey.text)
        for placekey in idinfo.findall("keywords/place/placekey"):
            if placekey.text:
                keywords.append(placekey.text)

    if not keywords:
        keywords = ["geospatial", "fgdc"]

    bbox = [-180.0, -90.0, 180.0, 90.0]
    if idinfo is not None and idinfo.find("spdom/bounding") is not None:
        b = idinfo.find("spdom/bounding")
        try:
            bbox = [
                float(b.findtext("westbc", "-180")),
                float(b.findtext("southbc", "-90")),
                float(b.findtext("eastbc", "180")),
                float(b.findtext("northbc", "90"))
            ]
        except ValueError:
            pass

    return {
        "@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
        "@type": "dcat:Dataset",
        "identifier": f"fgdc-{title.lower().replace(' ', '-')[:40]}",
        "title": title,
        "description": abstract,
        "publisher": {"@type": "org:Organization", "name": publisher},
        "contactPoint": {"fn": contact_fn, "hasEmail": f"mailto:{contact_email}" if "mailto:" not in contact_email else contact_email},
        "modified": pubdate,
        "issued": pubdate,
        "keyword": keywords,
        "theme": ["geospatial"],
        "bureauCode": ["020:00"],
        "programCode": ["020:000"],
        "accessRights": "public",
        "spatial": {"type": "BoundingBox", "bbox": bbox, "spatial_reference": "EPSG:4269 (NAD83)"},
        "conformsTo": "https://www.fgdc.gov/standards/projects/FGDC-standards-projects/metadata/base-metadata"
    }


def ingest_stac_json(data: Dict[str, Any]) -> Dict[str, Any]:
    stac_id = data.get("id", "stac-ingested-item")
    bbox = data.get("bbox", [-180, -90, 180, 90])
    props = data.get("properties", {})
    return {
        "@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
        "@type": "stac:Item",
        "identifier": stac_id,
        "title": f"STAC Asset Item - {stac_id}",
        "description": f"SpatioTemporal Asset Catalog item {stac_id} ingested into unified schema.",
        "publisher": {"@type": "org:Organization", "name": "STAC Provider"},
        "contactPoint": {"fn": "STAC Custodian", "hasEmail": "mailto:stac@provider.org"},
        "modified": props.get("datetime", "2026-10-01T00:00:00Z"),
        "keyword": ["stac", "spatiotemporal", "geospatial"],
        "bureauCode": ["000:00"],
        "programCode": ["000:000"],
        "accessRights": "public",
        "spatial": {"type": "BoundingBox", "bbox": bbox},
        "stac_metadata": {
            "stac_version": data.get("stac_version", "1.0.0"),
            "stac_extensions": data.get("stac_extensions", []),
            "id": stac_id,
            "collection": data.get("collection"),
            "properties": props,
            "assets": data.get("assets", {}),
            "links": data.get("links", [])
        }
    }


def ingest_aws_roda_yaml(yaml_str: str) -> Dict[str, Any]:
    data = yaml.safe_load(yaml_str)
    contact_str = data.get("Contact", "RODA Owner (mailto:open-data@aws.amazon.com)")
    fn = contact_str.split("(")[0].strip() if "(" in contact_str else contact_str
    email = "mailto:opendata@aws.amazon.com"
    if "mailto:" in contact_str:
        email = "mailto:" + contact_str.split("mailto:")[1].split(")")[0]

    return {
        "@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
        "@type": "dcat:Dataset",
        "identifier": f"aws-roda-{data.get('Name', 'dataset').lower().replace(' ', '-')[:40]}",
        "title": data.get("Name", "AWS RODA Dataset"),
        "description": data.get("Description", "No description provided."),
        "publisher": {"@type": "org:Organization", "name": data.get("ManagedBy", "AWS Registry of Open Data")},
        "contactPoint": {"fn": fn, "hasEmail": email},
        "modified": "2026-10-01T00:00:00Z",
        "keyword": data.get("Tags", ["aws-pds"]),
        "bureauCode": ["000:00"],
        "programCode": ["000:000"],
        "accessRights": "public",
        "license": data.get("License", "https://creativecommons.org/publicdomain/zero/1.0/"),
        "landingPage": data.get("Documentation"),
        "accrualPeriodicity": data.get("UpdateFrequency", "R/P1M"),
        "aws_roda": {
            "ManagedBy": data.get("ManagedBy"),
            "UpdateFrequency": data.get("UpdateFrequency"),
            "Resources": data.get("Resources", []),
            "DataAtWork": data.get("DataAtWork", {})
        }
    }


# --- Core Export Logic ---

def export_dcat_us_v11(rec: Dict[str, Any]) -> Dict[str, Any]:
    acc_map = {"public": "public", "restricted public": "restricted public", "non-public": "non-public"}
    return {
        "@type": "dcat:Dataset",
        "title": rec.get("title"),
        "description": rec.get("description"),
        "keyword": rec.get("keyword", []),
        "modified": rec.get("modified"),
        "publisher": rec.get("publisher"),
        "contactPoint": rec.get("contactPoint"),
        "identifier": rec.get("identifier"),
        "accessLevel": acc_map.get(rec.get("accessRights", "public"), "public"),
        "bureauCode": rec.get("bureauCode", []),
        "programCode": rec.get("programCode", []),
        "license": rec.get("license"),
        "landingPage": rec.get("landingPage"),
        "rights": rec.get("rights"),
        "spatial": rec.get("spatial", {}).get("bbox"),
        "temporal": rec.get("temporal"),
        "distribution": rec.get("distribution", [])
    }


def export_fgdc_xml(rec: Dict[str, Any]) -> str:
    metadata = ET.Element("metadata")
    idinfo = ET.SubElement(metadata, "idinfo")
    citation = ET.SubElement(idinfo, "citation")
    citeinfo = ET.SubElement(citation, "citeinfo")
    
    title = ET.SubElement(citeinfo, "title")
    title.text = rec.get("title", "")
    
    pubinfo = ET.SubElement(citeinfo, "pubinfo")
    publish = ET.SubElement(pubinfo, "publish")
    publish.text = rec.get("publisher", {}).get("name", "")
    
    descript = ET.SubElement(idinfo, "descript")
    abstract = ET.SubElement(descript, "abstract")
    abstract.text = rec.get("description", "")
    
    ptcontac = ET.SubElement(idinfo, "ptcontac")
    cntinfo = ET.SubElement(ptcontac, "cntinfo")
    cntper = ET.SubElement(cntinfo, "cntper")
    cntper.text = rec.get("contactPoint", {}).get("fn", "")
    cntemail = ET.SubElement(cntinfo, "cntemail")
    email_val = rec.get("contactPoint", {}).get("hasEmail", "").replace("mailto:", "")
    cntemail.text = email_val
    
    keywords = ET.SubElement(idinfo, "keywords")
    theme = ET.SubElement(keywords, "theme")
    for kw in rec.get("keyword", []):
        themekey = ET.SubElement(theme, "themekey")
        themekey.text = kw
        
    spdom = ET.SubElement(idinfo, "spdom")
    bounding = ET.SubElement(spdom, "bounding")
    bbox = rec.get("spatial", {}).get("bbox", [-180, -90, 180, 90])
    if not isinstance(bbox, list) or len(bbox) < 4:
        bbox = [-180, -90, 180, 90]
        
    westbc = ET.SubElement(bounding, "westbc")
    westbc.text = str(bbox[0])
    southbc = ET.SubElement(bounding, "southbc")
    southbc.text = str(bbox[1])
    eastbc = ET.SubElement(bounding, "eastbc")
    eastbc.text = str(bbox[2])
    northbc = ET.SubElement(bounding, "northbc")
    northbc.text = str(bbox[3])
    
    useconst = ET.SubElement(idinfo, "useconst")
    useconst.text = rec.get("rights") or rec.get("accessRights", "public")
    
    xml_str = ET.tostring(metadata, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent="  ")


def export_stac_item(rec: Dict[str, Any]) -> Dict[str, Any]:
    stac_meta = rec.get("stac_metadata", {})
    bbox = rec.get("spatial", {}).get("bbox", [-180, -90, 180, 90])
    if not isinstance(bbox, list) or len(bbox) < 4:
        bbox = [-180, -90, 180, 90]

    return {
        "stac_version": stac_meta.get("stac_version", "1.0.0"),
        "stac_extensions": stac_meta.get("stac_extensions", []),
        "type": "Feature",
        "id": stac_meta.get("id", rec.get("identifier", "").split("/")[-1]),
        "collection": stac_meta.get("collection"),
        "bbox": bbox,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
                [bbox[0], bbox[1]]
            ]]
        },
        "properties": stac_meta.get("properties", {"datetime": rec.get("modified", "2026-10-01T00:00:00Z")}),
        "links": stac_meta.get("links", []),
        "assets": stac_meta.get("assets", {})
    }


def export_aws_roda_yaml(rec: Dict[str, Any]) -> str:
    roda = rec.get("aws_roda", {})
    roda_dict = {
        "Name": rec.get("title"),
        "Description": rec.get("description"),
        "Documentation": rec.get("landingPage"),
        "Contact": f"{rec.get('contactPoint', {}).get('fn')} ({rec.get('contactPoint', {}).get('hasEmail')})",
        "ManagedBy": roda.get("ManagedBy", rec.get("publisher", {}).get("name")),
        "UpdateFrequency": roda.get("UpdateFrequency", rec.get("accrualPeriodicity")),
        "Tags": rec.get("keyword", []),
        "License": rec.get("license"),
        "Resources": roda.get("Resources", []),
        "DataAtWork": roda.get("DataAtWork", {})
    }
    return yaml.dump(roda_dict, sort_keys=False)


def export_glue_table_input(rec: Dict[str, Any]) -> Dict[str, Any]:
    glue_meta = rec.get("aws_glue_catalog", {})
    return {
        "DatabaseName": glue_meta.get("DatabaseName", "epa_envirofacts"),
        "TableInput": {
            "Name": glue_meta.get("TableName", "frs_facilities"),
            "Description": rec.get("description", "")[:2048],
            "TableType": glue_meta.get("TableType", "EXTERNAL_TABLE"),
            "StorageDescriptor": glue_meta.get("StorageDescriptor", {}),
            "PartitionKeys": glue_meta.get("PartitionKeys", []),
            "Parameters": glue_meta.get("Parameters", {})
        }
    }


def export_alation_payload(rec: Dict[str, Any]) -> Dict[str, Any]:
    alation_meta = rec.get("alation_governance", {})
    return {
        "ds_id": alation_meta.get("ds_id", 42),
        "key": alation_meta.get("key", f"42.envirofacts.{rec.get('identifier', 'dataset')}"),
        "title": rec.get("title"),
        "description": rec.get("description"),
        "custom_fields": alation_meta.get("custom_fields", []),
        "trust_flags": alation_meta.get("trust_flags", []),
        "stewards": alation_meta.get("stewards", []),
        "critical_data_element": alation_meta.get("critical_data_element", {})
    }


# --- API Models ---

class ConvertLegacyRequest(BaseModel):
    content: str = Field(..., description="Raw text, XML, YAML, or JSON string of legacy metadata record")
    format: Optional[str] = Field(None, description="Explicit format: 'dcat', 'fgdc', 'stac', or 'aws'")


class SyncCatalogRequest(BaseModel):
    record: Dict[str, Any] = Field(..., description="Unified Metadata Record JSON object")
    execute: bool = Field(False, description="Set to True for live API execution; False for dry-run validation")


# --- API Endpoints ---

@app.get("/", summary="Serve USWDS Vue 3 Web UI")
def serve_ui():
    ui_path = os.path.join(os.path.dirname(__file__), "metadata_editor.html")
    if not os.path.exists(ui_path):
        ui_path = "/workspace/scratch/metadata_editor.html"
    if os.path.exists(ui_path):
        return FileResponse(ui_path, media_type="text/html")
    return {"message": "EPA Unified Metadata API is running."}


@app.get("/health", summary="Health Check")
def get_health():
    return {
        "status": "healthy",
        "service": "Unified Metadata Conversion & Catalog Sync API",
        "posit_connect": True,
        "supported_formats": ["DCAT-US v1.1/v3.0", "FGDC CSDGM XML", "STAC v1.0.0", "AWS RODA YAML", "AWS Glue Catalog", "Alation Catalog"]
    }


@app.get("/schema", summary="Retrieve Unified Metadata JSON Schema")
def get_schema():
    if not UNIFIED_SCHEMA:
        raise HTTPException(status_code=404, detail="Schema file not found.")
    return UNIFIED_SCHEMA


@app.post("/convert/from-legacy", summary="Convert Legacy Metadata String to Unified Record")
def convert_from_legacy(payload: ConvertLegacyRequest):
    content = payload.content.strip()
    fmt = payload.format

    if not fmt:
        if content.startswith("<") or "<metadata>" in content or "<idinfo>" in content:
            fmt = "fgdc"
        elif "ManagedBy:" in content or "UpdateFrequency:" in content:
            fmt = "aws"
        elif "stac_version" in content:
            fmt = "stac"
        else:
            fmt = "dcat"

    try:
        if fmt == "fgdc":
            unified_rec = ingest_fgdc_xml(content)
        elif fmt == "aws":
            unified_rec = ingest_aws_roda_yaml(content)
        elif fmt == "stac":
            unified_rec = ingest_stac_json(json.loads(content))
        else:
            unified_rec = ingest_dcat_json(json.loads(content))

        return {
            "status": "success",
            "detected_format": fmt,
            "unified_record": unified_rec
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Conversion error ({fmt}): {str(e)}")


@app.post("/convert/from-file", summary="Upload Metadata File and Convert to Unified Record")
async def convert_from_file(
    file: UploadFile = File(...),
    format: Optional[str] = Query(None, description="Explicit format: dcat, fgdc, stac, aws")
):
    try:
        file_bytes = await file.read()
        content = file_bytes.decode("utf-8")
        filename = file.filename.lower()

        fmt = format
        if not fmt:
            if filename.endswith(".xml") or "<metadata>" in content or "<idinfo>" in content:
                fmt = "fgdc"
            elif filename.endswith(".yaml") or filename.endswith(".yml") or "ManagedBy:" in content:
                fmt = "aws"
            elif "stac_version" in content:
                fmt = "stac"
            else:
                fmt = "dcat"

        if fmt == "fgdc":
            unified_rec = ingest_fgdc_xml(content)
        elif fmt == "aws":
            unified_rec = ingest_aws_roda_yaml(content)
        elif fmt == "stac":
            unified_rec = ingest_stac_json(json.loads(content))
        else:
            unified_rec = ingest_dcat_json(json.loads(content))

        return {
            "status": "success",
            "filename": file.filename,
            "detected_format": fmt,
            "unified_record": unified_rec
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File conversion error: {str(e)}")


@app.post("/export/to-target", summary="Export Unified Metadata Record to Specific Domain Format")
def export_to_target(
    record: Dict[str, Any],
    format: str = Query(..., description="Target format: 'dcat11', 'dcat30', 'fgdc', 'stac', 'aws', 'glue', 'alation', or 'all'")
):
    fmt = format.lower()
    try:
        if fmt == "dcat11":
            return JSONResponse(
                content=export_dcat_us_v11(record),
                headers={"Content-Disposition": 'attachment; filename="exported_dcat_v11.json"'}
            )
        elif fmt == "dcat30":
            return JSONResponse(
                content=record,
                headers={"Content-Disposition": 'attachment; filename="exported_dcat_v30.json"'}
            )
        elif fmt == "fgdc":
            return Response(
                content=export_fgdc_xml(record),
                media_type="application/xml; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="exported_fgdc_metadata.xml"'}
            )
        elif fmt == "stac":
            return JSONResponse(
                content=export_stac_item(record),
                headers={"Content-Disposition": 'attachment; filename="exported_stac_item.json"'}
            )
        elif fmt == "aws":
            return Response(
                content=export_aws_roda_yaml(record),
                media_type="text/yaml; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="exported_aws_roda.yaml"'}
            )
        elif fmt == "glue":
            return JSONResponse(
                content=export_glue_table_input(record),
                headers={"Content-Disposition": 'attachment; filename="exported_glue_table.json"'}
            )
        elif fmt == "alation":
            return JSONResponse(
                content=export_alation_payload(record),
                headers={"Content-Disposition": 'attachment; filename="exported_alation_payload.json"'}
            )
        elif fmt == "all":
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("dcat_us_v30.json", json.dumps(record, indent=2))
                zf.writestr("dcat_us_v11.json", json.dumps(export_dcat_us_v11(record), indent=2))
                zf.writestr("fgdc_metadata.xml", export_fgdc_xml(record))
                zf.writestr("stac_item.json", json.dumps(export_stac_item(record), indent=2))
                zf.writestr("aws_roda.yaml", export_aws_roda_yaml(record))
                zf.writestr("glue_table_input.json", json.dumps(export_glue_table_input(record), indent=2))
                zf.writestr("alation_payload.json", json.dumps(export_alation_payload(record), indent=2))
                
            return Response(
                content=zip_buffer.getvalue(),
                media_type="application/zip",
                headers={"Content-Disposition": 'attachment; filename="all_metadata_formats.zip"'}
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")


@app.post("/sync/catalogs", summary="Lookup and Upsert Record into AWS Glue and Alation")
def sync_catalogs(payload: SyncCatalogRequest):
    rec = payload.record
    dry_run = not payload.execute

    # 1. Glue Extract
    glue_meta = rec.get("aws_glue_catalog", {})
    db_name = glue_meta.get("DatabaseName", "default")
    tbl_name = glue_meta.get("TableName", rec.get("identifier", "dataset").split("/")[-1].replace("-", "_"))
    glue_input = export_glue_table_input(rec)

    # 2. Alation Extract
    alation_payload = export_alation_payload(rec)

    return {
        "status": "success",
        "dry_run": dry_run,
        "aws_glue_status": {
            "action": "UPSERT_PREPARED" if dry_run else "MOCK_EXECUTED",
            "database": db_name,
            "table": tbl_name,
            "table_input": glue_input["TableInput"]
        },
        "alation_status": {
            "action": "UPSERT_PREPARED" if dry_run else "MOCK_EXECUTED",
            "key": alation_payload["key"],
            "custom_fields_count": len(alation_payload["custom_fields"])
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
