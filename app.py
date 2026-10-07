#!/usr/bin/env python3
"""
FastAPI Application for Metadata Schema Conversions and Catalog Synchronization.
Designed for deployment on Posit Connect.
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
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Unified Metadata Conversion & Catalog Sync API",
    description="Enterprise API for converting between metadata standards and syncing to cloud/governance catalogs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type"]
)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "unified_metadata_schema.json")
if not os.path.exists(SCHEMA_PATH):
    SCHEMA_PATH = "/workspace/artifacts/unified_metadata_schema.json"

UNIFIED_SCHEMA = {}
if os.path.exists(SCHEMA_PATH):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        UNIFIED_SCHEMA = json.load(f)

EMBEDDED_UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EPA Unified Metadata Studio</title>
  
  <!-- USWDS CSS & JS -->
  <script src="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.0/dist/js/uswds-init.min.js"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.0/dist/css/uswds.min.css">
  
  <!-- Leaflet CSS & JS for Spatial Bounding Box Map -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

  <!-- Vue 3 & JS-YAML CDN -->
  <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js"></script>

  <style>
    .badge-mandatory { background-color: #d9381e; color: #ffffff; }
    .badge-optional { background-color: #005ea2; color: #ffffff; }
    .section-divider { border-top: 2px dashed #a9aeb1; margin-top: 2rem; padding-top: 1.5rem; }
    .guidance-tooltip { background-color: #f0f4f8; border-left: 4px solid #005ea2; padding: 0.5rem 0.75rem; font-size: 0.875rem; margin-top: 0.25rem; border-radius: 2px; }
    #bbox-map { height: 340px; width: 100%; border: 2px solid #a9aeb1; border-radius: 4px; margin-bottom: 1rem; z-index: 1; }
    .api-settings-panel { background-color: #f0f4f8; border-left: 4px solid #005ea2; padding: 1rem; margin-bottom: 1.5rem; }
  </style>
</head>
<body>
  <div id="app">
    <div class="usa-overlay-wrapper">
      
      <!-- USWDS Extended Header -->
      <header class="usa-header usa-header--extended" role="banner">
        <div class="usa-navbar">
          <div class="usa-logo" id="extended-logo">
            <em class="usa-logo__text">
              <a href="#" title="Home">EPA Unified Metadata Studio</a>
            </em>
          </div>
        </div>
        <nav class="usa-nav" role="navigation">
          <div class="usa-nav__inner">
            <ul class="usa-nav__primary usa-accordion">
              <li class="usa-nav__primary-item">
                <button class="usa-nav__link" :class="{ 'usa-current': activeTab === 'general' }" @click="switchTab('general')">
                  Cross-Cutting Core
                </button>
              </li>
              <li class="usa-nav__primary-item">
                <button class="usa-nav__link" :class="{ 'usa-current': activeTab === 'dcat' }" @click="switchTab('dcat')">
                  DCAT-US v3.0 Ext
                </button>
              </li>
              <li class="usa-nav__primary-item">
                <button class="usa-nav__link" :class="{ 'usa-current': activeTab === 'stac' }" @click="switchTab('stac')">
                  STAC Geospatial Ext
                </button>
              </li>
              <li class="usa-nav__primary-item">
                <button class="usa-nav__link" :class="{ 'usa-current': activeTab === 'aws' }" @click="switchTab('aws')">
                  AWS RODA Ext
                </button>
              </li>
              <li class="usa-nav__primary-item">
                <button class="usa-nav__link" :class="{ 'usa-current': activeTab === 'glue' }" @click="switchTab('glue')">
                  AWS Glue Catalog Ext
                </button>
              </li>
              <li class="usa-nav__primary-item">
                <button class="usa-nav__link" :class="{ 'usa-current': activeTab === 'alation' }" @click="switchTab('alation')">
                  Alation Governance Ext
                </button>
              </li>
            </ul>
          </div>
        </nav>
      </header>

      <main class="usa-section padding-y-3">
        <div class="grid-container">
          
          <!-- API Base URL Config Bar -->
          <div class="api-settings-panel border-base-light margin-bottom-3">
            <div class="grid-row grid-gap flex-align-center">
              <div class="grid-col-12 tablet:grid-col-8">
                <label class="usa-label margin-top-0" for="api-base-url"><strong>Posit Connect API Base URL</strong></label>
                <input v-model="apiBaseUrl" class="usa-input" id="api-base-url" type="text" />
              </div>
              <div class="grid-col-12 tablet:grid-col-4">
                <label class="usa-label margin-top-0" for="api-key"><strong>API Key (Optional)</strong></label>
                <input v-model="apiKey" class="usa-input" id="api-key" type="password" placeholder="Key xxx..." />
              </div>
            </div>
          </div>

          <!-- USWDS Action Toolbar -->
          <div class="grid-row grid-gap margin-bottom-3 display-flex flex-align-center">
            <div class="grid-col-auto">
              <label class="usa-button usa-button--outline margin-bottom-0" for="file-upload">
                Convert & Ingest File (API)
              </label>
              <input id="file-upload" type="file" class="usa-sr-only" @change="convertAndLoadFile" accept=".json,.xml,.yaml,.yml" />
            </div>
            <div class="grid-col-auto">
              <div class="display-flex flex-align-center">
                <select v-model="exportFormat" class="usa-select margin-y-0 margin-right-1">
                  <option value="all">All Formats (.zip Bundle)</option>
                  <option value="dcat30">DCAT-US v3.0 JSON</option>
                  <option value="dcat11">DCAT-US v1.1 JSON</option>
                  <option value="fgdc">FGDC CSDGM XML</option>
                  <option value="stac">STAC v1.0.0 GeoJSON</option>
                  <option value="aws">AWS RODA YAML</option>
                  <option value="glue">AWS Glue TableInput</option>
                  <option value="alation">Alation Payload</option>
                </select>
                <button class="usa-button usa-button--secondary margin-y-0" @click="exportTargetFormatApi">
                  Export Target Format (API)
                </button>
              </div>
            </div>
            <div class="grid-col-auto">
              <button class="usa-button margin-y-0" @click="syncCatalogsApi">
                Sync to Catalogs (API)
              </button>
            </div>
            <div class="grid-col-auto margin-left-auto">
              <span class="usa-tag" :class="record.accessRights === 'public' ? 'usa-tag--success' : 'usa-tag--warn'">
                {{ (record.accessRights || 'PUBLIC').toUpperCase() }}
              </span>
            </div>
          </div>

          <!-- USWDS Alert Banner -->
          <div v-if="statusMessage" class="usa-alert margin-bottom-3" :class="statusType === 'error' ? 'usa-alert--error' : 'usa-alert--info'" role="status">
            <div class="usa-alert__body">
              <h3 class="usa-alert__heading">{{ statusType === 'error' ? 'API Error' : 'System Message' }}</h3>
              <p class="usa-alert__text">{{ statusMessage }}</p>
            </div>
          </div>

          <!-- TAB 1: CROSS-CUTTING SCHEMA ELEMENTS (Applicable to All Schemas) -->
          <div v-show="activeTab === 'general'">
            <h2 class="font-heading-xl border-bottom-05 border-base-light padding-bottom-1">
              Cross-Cutting Core Metadata Elements
            </h2>
            <p class="usa-intro">General metadata fields applicable across all enterprise, open-data, and cloud catalog schemas.</p>

            <form class="usa-form usa-form--large" @submit.prevent>
              
              <!-- MANDATORY SECTION (TOP) -->
              <div class="margin-bottom-4">
                <h3 class="font-heading-l text-primary display-flex flex-align-center">
                  Mandatory Core Elements
                  <span class="usa-tag badge-mandatory margin-left-2">MANDATORY</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="title">
                    Dataset Title <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                  </label>
                  <input v-model="record.title" class="usa-input" id="title" type="text" required />
                  <div class="guidance-tooltip">
                    <strong>Guidance:</strong> Required by DCAT-US v3.0, CSDGM (citeinfo/title), ISO 19115 (title), and AWS RODA (Name). Human-readable dataset name.
                  </div>
                </div>

                <div class="usa-form-group">
                  <label class="usa-label" for="description">
                    Abstract / Description <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                  </label>
                  <textarea v-model="record.description" class="usa-textarea" id="description" rows="4" required></textarea>
                  <div class="guidance-tooltip">
                    <strong>Guidance:</strong> Summary outlining dataset contents, purpose, and spatial/temporal scope. Required by all major metadata standards.
                  </div>
                </div>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="identifier">
                        Persistent Identifier (DOI / URI) <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <input v-model="record.identifier" class="usa-input" id="identifier" type="text" required />
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> Unique persistent URI, DOI, or internal agency identifier.
                      </div>
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="modified">
                        Last Modified Date <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <input v-model="record.modified" class="usa-input" id="modified" type="text" placeholder="YYYY-MM-DD" required />
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> ISO 8601 date (YYYY-MM-DD) indicating when the data asset or metadata was last modified.
                      </div>
                    </div>
                  </div>
                </div>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="publisher-name">
                        Publishing Organization <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <input v-model="record.publisher.name" class="usa-input" id="publisher-name" type="text" required />
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> Publishing agency or sub-agency (e.g., U.S. Environmental Protection Agency).
                      </div>
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="contact-email">
                        Contact Point Email <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <input v-model="record.contactPoint.hasEmail" class="usa-input" id="contact-email" type="email" required />
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> Email address for data custodian or point of contact. Must be valid email.
                      </div>
                    </div>
                  </div>
                </div>

                <div class="grid-row grid-gap">
                  <div class="grid-col-4">
                    <div class="usa-form-group">
                      <label class="usa-label" for="access-rights">
                        Access Rights <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <select v-model="record.accessRights" class="usa-select" id="access-rights" required>
                        <option value="public">Public</option>
                        <option value="restricted public">Restricted Public</option>
                        <option value="non-public">Non-Public</option>
                      </select>
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> DCAT-US v3.0 public access rights classification.
                      </div>
                    </div>
                  </div>
                  <div class="grid-col-4">
                    <div class="usa-form-group">
                      <label class="usa-label" for="bureau-code">
                        Bureau Code <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <input v-model="record.bureauCodeStr" class="usa-input" id="bureau-code" type="text" placeholder="020:00" required />
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> OMB Circular A-11 Bureau Code ('020:00' for EPA).
                      </div>
                    </div>
                  </div>
                  <div class="grid-col-4">
                    <div class="usa-form-group">
                      <label class="usa-label" for="program-code">
                        Program Code <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                      </label>
                      <input v-model="record.programCodeStr" class="usa-input" id="program-code" type="text" placeholder="020:000" required />
                      <div class="guidance-tooltip">
                        <strong>Guidance:</strong> Federal Program Inventory Code ('020:000' for EPA).
                      </div>
                    </div>
                  </div>
                </div>

                <div class="usa-form-group">
                  <label class="usa-label" for="keywords">
                    Keywords / Tags (Comma Separated) <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                  </label>
                  <input v-model="record.keywordsStr" class="usa-input" id="keywords" type="text" required />
                  <div class="guidance-tooltip">
                    <strong>Guidance:</strong> Controlled tags describing subject matter. Automatically populates AWS Tags and CSDGM theme keys.
                  </div>
                </div>

                <!-- LEAFLET MAP & BOUNDING BOX WIDGET -->
                <div class="usa-form-group margin-top-4">
                  <label class="usa-label font-heading-m">
                    Spatial Coverage & Bounding Box Map Widget <abbr title="required" class="usa-hint usa-hint--required">*</abbr>
                  </label>
                  <div class="guidance-tooltip margin-bottom-2">
                    <strong>Spatial Extent Guidance:</strong> Interactive Leaflet map synchronized with bounding box inputs [West, South, East, North]. Edit input numbers or click preset buttons to adjust map rectangle.
                  </div>
                  
                  <div id="bbox-map"></div>
                  
                  <div class="margin-bottom-2 display-flex gap-1 flex-wrap">
                    <button type="button" class="usa-button usa-button--outline usa-button--accent-cool margin-y-0" @click="setPresetBbox([-125.0, 24.5, -66.9, 49.4])">Preset: CONUS</button>
                    <button type="button" class="usa-button usa-button--outline usa-button--accent-cool margin-y-0" @click="setPresetBbox([-179.1, 17.8, -65.2, 71.4])">Preset: USA & Territories</button>
                    <button type="button" class="usa-button usa-button--outline usa-button--accent-cool margin-y-0" @click="setPresetBbox([-180.0, -90.0, 180.0, 90.0])">Preset: Global</button>
                  </div>

                  <div class="grid-row grid-gap">
                    <div class="grid-col-3">
                      <label class="usa-label" for="westbc">West Longitude</label>
                      <input v-model.number="record.spatial.bbox[0]" @input="updateMapFromInputs" class="usa-input" id="westbc" type="number" step="any" />
                    </div>
                    <div class="grid-col-3">
                      <label class="usa-label" for="southbc">South Latitude</label>
                      <input v-model.number="record.spatial.bbox[1]" @input="updateMapFromInputs" class="usa-input" id="southbc" type="number" step="any" />
                    </div>
                    <div class="grid-col-3">
                      <label class="usa-label" for="eastbc">East Longitude</label>
                      <input v-model.number="record.spatial.bbox[2]" @input="updateMapFromInputs" class="usa-input" id="eastbc" type="number" step="any" />
                    </div>
                    <div class="grid-col-3">
                      <label class="usa-label" for="northbc">North Latitude</label>
                      <input v-model.number="record.spatial.bbox[3]" @input="updateMapFromInputs" class="usa-input" id="northbc" type="number" step="any" />
                    </div>
                  </div>
                </div>

              </div>

              <!-- OPTIONAL SECTION (BOTTOM) -->
              <div class="section-divider margin-bottom-4">
                <h3 class="font-heading-l text-secondary display-flex flex-align-center">
                  Optional Core Elements
                  <span class="usa-tag badge-optional margin-left-2">OPTIONAL</span>
                </h3>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="issued">Release / Issued Date</label>
                      <input v-model="record.issued" class="usa-input" id="issued" type="text" placeholder="YYYY-MM-DD" />
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="contact-fn">Contact Person Name</label>
                      <input v-model="record.contactPoint.fn" class="usa-input" id="contact-fn" type="text" />
                    </div>
                  </div>
                </div>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="license">License URL</label>
                      <input v-model="record.license" class="usa-input" id="license" type="text" />
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="landing-page">Landing Page URL</label>
                      <input v-model="record.landingPage" class="usa-input" id="landing-page" type="text" />
                    </div>
                  </div>
                </div>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="periodicity">Accrual Periodicity (ISO 8601)</label>
                      <input v-model="record.accrualPeriodicity" class="usa-input" id="periodicity" type="text" placeholder="R/P1M" />
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="temporal">Temporal Coverage Range</label>
                      <input v-model="record.temporal" class="usa-input" id="temporal" type="text" placeholder="YYYY-MM-DD/YYYY-MM-DD" />
                    </div>
                  </div>
                </div>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="spatial-ref">Coordinate Reference System (EPSG)</label>
                      <input v-model="record.spatial.spatial_reference" class="usa-input" id="spatial-ref" type="text" placeholder="EPSG:4269 (NAD83)" />
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="primary-uii">Primary IT Investment UII</label>
                      <input v-model="record.primaryITInvestmentUII" class="usa-input" id="primary-uii" type="text" placeholder="020-000001000" />
                    </div>
                  </div>
                </div>

              </div>

            </form>
          </div>

          <!-- TAB 2: DCAT-US v3.0 EXTENSIONS -->
          <div v-show="activeTab === 'dcat'">
            <h2 class="font-heading-xl border-bottom-05 border-base-light padding-bottom-1">
              DCAT-US v3.0 Specific Extensions
            </h2>

            <form class="usa-form usa-form--large" @submit.prevent>
              <div class="margin-bottom-4">
                <h3 class="font-heading-l text-primary display-flex flex-align-center">
                  Data Services (APIs) & Distributions
                  <span class="usa-tag badge-mandatory margin-left-2">MANDATORY</span>
                </h3>

                <h4 class="font-heading-m margin-top-2">Data Services (REST / OGC APIs)</h4>
                <div v-for="(service, index) in record.dataServices" :key="index" class="border-1px border-base-lighter padding-2 margin-bottom-2">
                  <div class="usa-form-group">
                    <label class="usa-label">Service Title *</label>
                    <input v-model="service.title" class="usa-input" required />
                  </div>
                  <div class="usa-form-group">
                    <label class="usa-label">Endpoint URL *</label>
                    <input v-model="service.endpointURL" class="usa-input" required />
                  </div>
                </div>
              </div>

              <div class="section-divider margin-bottom-4">
                <h3 class="font-heading-l text-secondary display-flex flex-align-center">
                  EPA Governance & Scientific Quality Assurance
                  <span class="usa-tag badge-optional margin-left-2">OPTIONAL</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="qapp">Quality Assurance Plan (QAPP) URL</label>
                  <input v-model="record.governance_and_quality.quality_assurance_plan_qapp" class="usa-input" id="qapp" type="text" />
                  <div class="guidance-tooltip"><strong>EPA Quality Policy:</strong> URL to approved Quality Assurance Project Plan (QAPP) per EPA Order 5360.1 A2.</div>
                </div>

                <div class="usa-checkbox margin-top-2">
                  <input v-model="record.governance_and_quality.influential_data_flag" class="usa-checkbox__input" id="influential" type="checkbox" />
                  <label class="usa-checkbox__label" for="influential">OMB M-19-15 Influential Scientific Information Flag</label>
                </div>

                <div class="usa-checkbox margin-top-2">
                  <input v-model="record.governance_and_quality.ml_training_data_suitable" class="usa-checkbox__input" id="ml-suitable" type="checkbox" />
                  <label class="usa-checkbox__label" for="ml-suitable">AI/ML Training Data Suitable (usg:ml-training-data)</label>
                </div>
              </div>
            </form>
          </div>

          <!-- TAB 3: STAC GEOSPATIAL EXTENSIONS -->
          <div v-show="activeTab === 'stac'">
            <h2 class="font-heading-xl border-bottom-05 border-base-light padding-bottom-1">
              STAC Spatiotemporal Extensions
            </h2>

            <form class="usa-form usa-form--large" @submit.prevent>
              <div class="margin-bottom-4">
                <h3 class="font-heading-l text-primary display-flex flex-align-center">
                  STAC Item & Collection Identity
                  <span class="usa-tag badge-mandatory margin-left-2">MANDATORY</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="stac-id">STAC Item ID *</label>
                  <input v-model="record.stac_metadata.id" class="usa-input" id="stac-id" type="text" required />
                </div>
                <div class="usa-form-group">
                  <label class="usa-label" for="stac-collection">STAC Parent Collection ID *</label>
                  <input v-model="record.stac_metadata.collection" class="usa-input" id="stac-collection" type="text" required />
                </div>
              </div>

              <div class="section-divider margin-bottom-4">
                <h3 class="font-heading-l text-secondary display-flex flex-align-center">
                  STAC Extension Attributes
                  <span class="usa-tag badge-optional margin-left-2">OPTIONAL</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="stac-epsg">EPSG Projection Code</label>
                  <input v-model.number="record.stac_metadata.properties['proj:epsg']" class="usa-input" id="stac-epsg" type="number" placeholder="4269" />
                </div>
              </div>
            </form>
          </div>

          <!-- TAB 4: AWS RODA EXTENSIONS -->
          <div v-show="activeTab === 'aws'">
            <h2 class="font-heading-xl border-bottom-05 border-base-light padding-bottom-1">
              AWS Registry of Open Data (RODA) Extensions
            </h2>

            <form class="usa-form usa-form--large" @submit.prevent>
              <div class="margin-bottom-4">
                <h3 class="font-heading-l text-primary display-flex flex-align-center">
                  AWS Cloud Resources (S3 / SNS)
                  <span class="usa-tag badge-mandatory margin-left-2">MANDATORY</span>
                </h3>

                <div v-for="(res, index) in record.aws_roda.Resources" :key="index" class="border-1px border-base-lighter padding-2 margin-bottom-2">
                  <div class="usa-form-group">
                    <label class="usa-label">AWS Resource ARN *</label>
                    <input v-model="res.ARN" class="usa-input" required />
                  </div>
                  <div class="grid-row grid-gap">
                    <div class="grid-col-6">
                      <label class="usa-label">Region *</label>
                      <input v-model="res.Region" class="usa-input" required />
                    </div>
                    <div class="grid-col-6">
                      <label class="usa-label">Type *</label>
                      <select v-model="res.Type" class="usa-select" required>
                        <option value="S3 Bucket">S3 Bucket</option>
                        <option value="SNS Topic">SNS Topic</option>
                        <option value="CloudFront Distribution">CloudFront Distribution</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>

              <div class="section-divider margin-bottom-4">
                <h3 class="font-heading-l text-secondary display-flex flex-align-center">
                  AWS Community Metadata
                  <span class="usa-tag badge-optional margin-left-2">OPTIONAL</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="managed-by">Managed By Organization</label>
                  <input v-model="record.aws_roda.ManagedBy" class="usa-input" id="managed-by" type="text" />
                </div>
              </div>
            </form>
          </div>

          <!-- TAB 5: AWS GLUE CATALOG EXTENSIONS -->
          <div v-show="activeTab === 'glue'">
            <h2 class="font-heading-xl border-bottom-05 border-base-light padding-bottom-1">
              AWS Glue Data Catalog Extensions
            </h2>

            <form class="usa-form usa-form--large" @submit.prevent>
              <div class="margin-bottom-4">
                <h3 class="font-heading-l text-primary display-flex flex-align-center">
                  Glue Database & Column Dictionary
                  <span class="usa-tag badge-mandatory margin-left-2">MANDATORY</span>
                </h3>

                <div class="grid-row grid-gap">
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="glue-db">Glue Database Name *</label>
                      <input v-model="record.aws_glue_catalog.DatabaseName" class="usa-input" id="glue-db" type="text" required />
                    </div>
                  </div>
                  <div class="grid-col-6">
                    <div class="usa-form-group">
                      <label class="usa-label" for="glue-table">Glue Table Name *</label>
                      <input v-model="record.aws_glue_catalog.TableName" class="usa-input" id="glue-table" type="text" required />
                    </div>
                  </div>
                </div>

                <h4 class="font-heading-m margin-top-3">Column Dictionary *</h4>
                <table class="usa-table usa-table--borderless width-full">
                  <thead>
                    <tr>
                      <th scope="col">Column Name *</th>
                      <th scope="col">Data Type *</th>
                      <th scope="col">Comment</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(col, index) in record.aws_glue_catalog.StorageDescriptor.Columns" :key="index">
                      <td><input v-model="col.Name" class="usa-input margin-y-0" required /></td>
                      <td><input v-model="col.Type" class="usa-input margin-y-0" required /></td>
                      <td><input v-model="col.Comment" class="usa-input margin-y-0" /></td>
                      <td>
                        <button type="button" class="usa-button usa-button--unstyled text-error" @click="removeColumn(index)">
                          Remove
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <button type="button" class="usa-button usa-button--outline margin-top-1" @click="addColumn">
                  + Add Column
                </button>
              </div>

              <div class="section-divider margin-bottom-4">
                <h3 class="font-heading-l text-secondary display-flex flex-align-center">
                  Storage Location & Format
                  <span class="usa-tag badge-optional margin-left-2">OPTIONAL</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="glue-location">S3 Storage Location Path</label>
                  <input v-model="record.aws_glue_catalog.StorageDescriptor.Location" class="usa-input" id="glue-location" type="text" placeholder="s3://bucket/path/" />
                </div>
              </div>
            </form>
          </div>

          <!-- TAB 6: ALATION GOVERNANCE EXTENSIONS -->
          <div v-show="activeTab === 'alation'">
            <h2 class="font-heading-xl border-bottom-05 border-base-light padding-bottom-1">
              Alation Enterprise Governance Extensions
            </h2>

            <form class="usa-form usa-form--large" @submit.prevent>
              <div class="margin-bottom-4">
                <h3 class="font-heading-l text-primary display-flex flex-align-center">
                  Alation Asset Identity
                  <span class="usa-tag badge-mandatory margin-left-2">MANDATORY</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="alation-ds">Alation Data Source ID (ds_id) *</label>
                  <input v-model.number="record.alation_governance.ds_id" class="usa-input" id="alation-ds" type="number" required />
                </div>
              </div>

              <div class="section-divider margin-bottom-4">
                <h3 class="font-heading-l text-secondary display-flex flex-align-center">
                  Trust Certification & Governance Flags
                  <span class="usa-tag badge-optional margin-left-2">OPTIONAL</span>
                </h3>

                <div class="usa-form-group">
                  <label class="usa-label" for="alation-trust">Trust Check Flag</label>
                  <select v-model="record.alation_governance.trust_flags.status" class="usa-select" id="alation-trust">
                    <option value="ENDORSED">ENDORSED (Certified Data)</option>
                    <option value="WARNING">WARNING (Review Required)</option>
                    <option value="DEPRECATED">DEPRECATED</option>
                  </select>
                </div>
              </div>
            </form>
          </div>

        </div>
      </main>
    </div>
  </div>

  <!-- USWDS Main JS -->
  <script src="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.0/dist/js/uswds.min.js"></script>

  <!-- Vue 3 Application Logic -->
  <script>
    const { createApp, ref, reactive, onMounted, nextTick } = Vue;

    createApp({
      setup() {
        const activeTab = ref('general');
        const exportFormat = ref('all');
        const apiBaseUrl = ref(window.location.origin + window.location.pathname.replace(/\/$/, ''));
        const apiKey = ref('');
        const statusMessage = ref('Connected to Posit Connect API Base URL.');
        const statusType = ref('info');

        const record = reactive({
          title: "EPA Envirofacts - Facility Registry Service (FRS) National Asset",
          description: "Geospatial database and REST API providing facility location and compliance data.",
          identifier: "https://doi.org/10.5066/F7EPA-FRS-ENVIROFACTS-2026",
          modified: "2026-10-01",
          issued: "2015-05-15",
          accessRights: "public",
          license: "https://creativecommons.org/publicdomain/zero/1.0/",
          landingPage: "https://enviro.epa.gov/enviro/efsystemquery.frs",
          accrualPeriodicity: "R/P1M",
          temporal: "1970-01-01/2026-10-01",
          keywordsStr: "envirofacts, facility-registry-service, frs, geospatial, rest-api",
          bureauCodeStr: "020:00",
          programCodeStr: "020:000",
          spatial: { type: "BoundingBox", bbox: [-125.0, 24.5, -66.9, 49.4], spatial_reference: "EPSG:4269" },
          publisher: { name: "U.S. Environmental Protection Agency" },
          contactPoint: { fn: "Envirofacts Data Custodian", hasEmail: "envirofacts@epa.gov" },
          dataServices: [{ title: "EPA Envirofacts REST API", endpointURL: "https://enviro.epa.gov/enviro/efservice/" }],
          stac_metadata: { id: "epa-envirofacts-frs-2026-v1", collection: "epa-envirofacts-national-assets", properties: { "proj:epsg": 4269 } },
          aws_roda: { ManagedBy: "U.S. EPA OMS", Resources: [{ ARN: "arn:aws:s3:::epa-envirofacts-frs-geospatial", Region: "us-east-1", Type: "S3 Bucket" }] },
          aws_glue_catalog: {
            DatabaseName: "epa_envirofacts",
            TableName: "frs_facilities",
            StorageDescriptor: {
              Location: "s3://epa-envirofacts-frs-geospatial/v2026/",
              Columns: [
                { Name: "registry_id", Type: "string", Comment: "Unique 12-digit FRS facility identifier" },
                { Name: "primary_name", Type: "string", Comment: "Official facility business name" },
                { Name: "latitude83", Type: "double", Comment: "NAD83 Latitude coordinate" },
                { Name: "longitude83", Type: "double", Comment: "NAD83 Longitude coordinate" }
              ]
            }
          },
          alation_governance: { ds_id: 42, trust_flags: { status: "ENDORSED" } },
          governance_and_quality: { primaryITInvestmentUII: "020-000001000", quality_assurance_plan_qapp: "https://www.epa.gov/frs_qapp.pdf", influential_data_flag: true, ml_training_data_suitable: true }
        });

        let map, bboxLayer;

        onMounted(() => {
          nextTick(() => {
            initMap();
          });
        });

        function switchTab(tabName) {
          activeTab.value = tabName;
          if (tabName === 'general') {
            nextTick(() => {
              if (map) { map.invalidateSize(); } else { initMap(); }
            });
          }
        }

        function initMap() {
          const mapEl = document.getElementById('bbox-map');
          if (!mapEl || map) return;

          map = L.map('bbox-map').setView([37.8, -96.0], 4);
          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '&copy; OpenStreetMap contributors'
          }).addTo(map);

          updateMapFromInputs();
        }

        function updateMapFromInputs() {
          if (!map) return;
          const bbox = record.spatial.bbox;
          if (!bbox || bbox.length < 4) return;

          if (bboxLayer) { map.removeLayer(bboxLayer); }

          const bounds = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]];
          bboxLayer = L.rectangle(bounds, { color: "#d9381e", weight: 2, fillOpacity: 0.25 }).addTo(map);
          map.fitBounds(bounds, { padding: [20, 20] });
        }

        function setPresetBbox(newBbox) {
          record.spatial.bbox = [...newBbox];
          updateMapFromInputs();
        }

        function getAuthHeaders() {
          const headers = {};
          if (apiKey.value && apiKey.value.trim() !== '') {
            headers["Authorization"] = "Key " + apiKey.value.trim();
          }
          return headers;
        }

        function addColumn() {
          record.aws_glue_catalog.StorageDescriptor.Columns.push({ Name: "", Type: "string", Comment: "" });
        }

        function removeColumn(index) {
          record.aws_glue_catalog.StorageDescriptor.Columns.splice(index, 1);
        }

        async function convertAndLoadFile(event) {
          const file = event.target.files[0];
          if (!file) return;

          statusMessage.value = `Uploading '${file.name}' to Posit Connect API for conversion...`;
          statusType.value = 'info';

          const formData = new FormData();
          formData.append("file", file);

          try {
            const cleanBase = apiBaseUrl.value.replace(/\/$/, '');
            const res = await fetch(`${cleanBase}/convert/from-file`, {
              method: "POST",
              headers: getAuthHeaders(),
              body: formData
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

            const data = await res.json();
            Object.assign(record, data.unified_record);

            if (Array.isArray(record.keyword)) record.keywordsStr = record.keyword.join(', ');
            if (Array.isArray(record.bureauCode)) record.bureauCodeStr = record.bureauCode.join(', ');
            if (Array.isArray(record.programCode)) record.programCodeStr = record.programCode.join(', ');

            updateMapFromInputs();
            statusMessage.value = `Successfully converted '${file.name}' (${data.detected_format.toUpperCase()}) via Posit Connect API.`;
          } catch (err) {
            statusMessage.value = `API Conversion Error: ${err.message}`;
            statusType.value = 'error';
          }
        }

        async function exportTargetFormatApi() {
          statusMessage.value = `Generating '${exportFormat.value}' export via Posit Connect API...`;
          statusType.value = 'info';

          const exportPayload = JSON.parse(JSON.stringify(record));
          exportPayload.keyword = record.keywordsStr ? record.keywordsStr.split(',').map(s => s.trim()) : [];
          exportPayload.bureauCode = record.bureauCodeStr ? record.bureauCodeStr.split(',').map(s => s.trim()) : [];
          exportPayload.programCode = record.programCodeStr ? record.programCodeStr.split(',').map(s => s.trim()) : [];

          try {
            const cleanBase = apiBaseUrl.value.replace(/\/$/, '');
            const res = await fetch(`${cleanBase}/export/to-target?format=${exportFormat.value}`, {
              method: "POST",
              headers: { "Content-Type": "application/json", ...getAuthHeaders() },
              body: JSON.stringify(exportPayload)
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

            const contentType = res.headers.get("content-type") || "";
            let blob;
            let filename = `exported_${exportFormat.value}_metadata`;

            if (exportFormat.value === "all" || contentType.includes("zip")) {
              blob = await res.blob();
              filename = "all_metadata_formats.zip";
            } else if (exportFormat.value === "fgdc" || contentType.includes("xml")) {
              const textData = await res.text();
              blob = new Blob([textData], { type: "application/xml" });
              filename += ".xml";
            } else if (exportFormat.value === "aws" || contentType.includes("yaml")) {
              const textData = await res.text();
              blob = new Blob([textData], { type: "text/yaml" });
              filename += ".yaml";
            } else {
              const jsonData = await res.json();
              blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: "application/json" });
              filename += ".json";
            }

            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);

            statusMessage.value = `Successfully downloaded '${filename}' via Posit Connect API.`;
          } catch (err) {
            statusMessage.value = `API Export Error: ${err.message}`;
            statusType.value = 'error';
          }
        }

        async function syncCatalogsApi() {
          statusMessage.value = `Triggering catalog sync via Posit Connect API...`;
          statusType.value = 'info';

          const syncPayload = JSON.parse(JSON.stringify(record));
          syncPayload.keyword = record.keywordsStr ? record.keywordsStr.split(',').map(s => s.trim()) : [];

          try {
            const cleanBase = apiBaseUrl.value.replace(/\/$/, '');
            const res = await fetch(`${cleanBase}/sync/catalogs`, {
              method: "POST",
              headers: { "Content-Type": "application/json", ...getAuthHeaders() },
              body: JSON.stringify({ record: syncPayload, execute: false })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

            const result = await res.json();
            const glueAct = result.aws_glue_status.action || 'OK';
            const alationAct = result.alation_status.action || 'OK';

            statusMessage.value = `Catalog Sync Successful! AWS Glue Action: ${glueAct} | Alation Action: ${alationAct}`;
          } catch (err) {
            statusMessage.value = `API Sync Error: ${err.message}`;
            statusType.value = 'error';
          }
        }

        return {
          activeTab,
          switchTab,
          exportFormat,
          apiBaseUrl,
          apiKey,
          statusMessage,
          statusType,
          record,
          setPresetBbox,
          updateMapFromInputs,
          addColumn,
          removeColumn,
          convertAndLoadFile,
          exportTargetFormatApi,
          syncCatalogsApi
        };
      }
    }).mount('#app');
  </script>
</body>
</html>
"""


def ingest_dcat_json(data: Dict[str, Any]) -> Dict[str, Any]:
    acc = data.get("accessRights") or data.get("accessLevel", "public")
    if acc not in ["public", "restricted public", "non-public"]:
        acc = "public"
        
    return {
        "@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
        "@type": "dcat:Dataset",
        "identifier": data.get("identifier", "dcat-ingested-dataset"),
        "title": data.get("title", "Untitled Dataset"),
        "description": data.get("description", "No description provided."),
        "publisher": data.get("publisher", {"@type": "org:Organization", "name": "Unknown Publisher"}),
        "contactPoint": data.get("contactPoint", {"fn": "Data Custodian", "hasEmail": "mailto:admin@agency.gov"}),
        "modified": data.get("modified", "2026-10-01T00:00:00Z"),
        "keyword": data.get("keyword", ["open-data"]),
        "bureauCode": data.get("bureauCode", ["000:00"]),
        "programCode": data.get("programCode", ["000:000"]),
        "accessRights": acc,
        "license": data.get("license", "https://creativecommons.org/publicdomain/zero/1.0/"),
        "landingPage": data.get("landingPage"),
        "distribution": data.get("distribution", []),
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
    
    keywords = []
    if idinfo is not None:
        for themekey in idinfo.findall("keywords/theme/themekey"):
            if themekey.text:
                keywords.append(themekey.text)
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
        "contactPoint": {"fn": contact_fn, "hasEmail": f"mailto:{contact_email}"},
        "modified": "2026-10-01T00:00:00Z",
        "keyword": keywords,
        "bureauCode": ["020:00"],
        "programCode": ["020:000"],
        "accessRights": "public",
        "spatial": {"type": "BoundingBox", "bbox": bbox}
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
            "properties": props,
            "assets": data.get("assets", {})
        }
    }


def ingest_aws_roda_yaml(yaml_str: str) -> Dict[str, Any]:
    data = yaml.safe_load(yaml_str)
    contact_str = data.get("Contact", "RODA Owner (mailto:open-data@aws.amazon.com)")
    return {
        "@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
        "@type": "dcat:Dataset",
        "identifier": f"aws-roda-{data.get('Name', 'dataset').lower().replace(' ', '-')[:40]}",
        "title": data.get("Name", "AWS RODA Dataset"),
        "description": data.get("Description", "No description provided."),
        "publisher": {"@type": "org:Organization", "name": data.get("ManagedBy", "AWS Registry of Open Data")},
        "contactPoint": {"fn": contact_str.split("(")[0].strip(), "hasEmail": "mailto:opendata@aws.amazon.com"},
        "modified": "2026-10-01T00:00:00Z",
        "keyword": data.get("Tags", ["aws-pds"]),
        "bureauCode": ["000:00"],
        "programCode": ["000:000"],
        "accessRights": "public",
        "license": data.get("License", "https://creativecommons.org/publicdomain/zero/1.0/"),
        "landingPage": data.get("Documentation"),
        "aws_roda": {
            "ManagedBy": data.get("ManagedBy"),
            "UpdateFrequency": data.get("UpdateFrequency"),
            "Resources": data.get("Resources", []),
            "DataAtWork": data.get("DataAtWork", {})
        }
    }


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
    cntemail.text = rec.get("contactPoint", {}).get("hasEmail", "").replace("mailto:", "")
    
    keywords = ET.SubElement(idinfo, "keywords")
    theme = ET.SubElement(keywords, "theme")
    for kw in rec.get("keyword", []):
        themekey = ET.SubElement(theme, "themekey")
        themekey.text = kw
        
    spdom = ET.SubElement(idinfo, "spdom")
    bounding = ET.SubElement(spdom, "bounding")
    bbox = rec.get("spatial", {}).get("bbox", [-180, -90, 180, 90])
    westbc = ET.SubElement(bounding, "westbc")
    westbc.text = str(bbox[0])
    southbc = ET.SubElement(bounding, "southbc")
    southbc.text = str(bbox[1])
    eastbc = ET.SubElement(bounding, "eastbc")
    eastbc.text = str(bbox[2])
    northbc = ET.SubElement(bounding, "northbc")
    northbc.text = str(bbox[3])
    
    xml_str = ET.tostring(metadata, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent="  ")


def export_stac_item(rec: Dict[str, Any]) -> Dict[str, Any]:
    stac_meta = rec.get("stac_metadata", {})
    bbox = rec.get("spatial", {}).get("bbox", [-180, -90, 180, 90])
    return {
        "stac_version": stac_meta.get("stac_version", "1.0.0"),
        "stac_extensions": stac_meta.get("stac_extensions", []),
        "type": "Feature",
        "id": stac_meta.get("id", rec.get("identifier", "").split("/")[-1]),
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


class ConvertLegacyRequest(BaseModel):
    content: str = Field(..., description="Raw text, XML, YAML, or JSON string of legacy metadata record")
    format: Optional[str] = Field(None, description="Explicit format: 'dcat', 'fgdc', 'stac', or 'aws'")


class SyncCatalogRequest(BaseModel):
    record: Dict[str, Any] = Field(..., description="Unified Metadata Record JSON object")
    execute: bool = Field(False, description="Set to True for live API execution; False for dry-run validation")


@app.get("/", summary="Serve USWDS Vue 3 Web UI", response_class=HTMLResponse)
def serve_ui():
    return HTMLResponse(content=EMBEDDED_UI_HTML)


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

    glue_meta = rec.get("aws_glue_catalog", {})
    db_name = glue_meta.get("DatabaseName", "default")
    tbl_name = glue_meta.get("TableName", rec.get("identifier", "dataset").split("/")[-1].replace("-", "_"))
    glue_input = export_glue_table_input(rec)

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
