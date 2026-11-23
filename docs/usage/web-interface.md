# Web Interface Guide

The GeoDE web interface provides an interactive way to monitor and manage your GNSS network.

## Login

Open the configured URL and enter your GeoDE username and password below the
GeoDE logo. For the first account on a new installation, follow the
[administrator setup instructions](../installation/web-interface.md).

---

## Map Interface

The main map interface displays your station network with the following features:

### Key Features

- **Search Bar**: Locate stations by code. Apply filters for specific countries and networks.
- **Map Controls**: Zoom in/out buttons for detailed views
- **Station Markers**:
  - **Green Square**: Standard station locations
  - **Red Triangle**: Stations with alerts or specific statuses
- **Station List**: Sidebar for managing and viewing individual stations
- **Map Base**: OpenStreetMap cartographic data

![Map Interface](https://github.com/user-attachments/assets/36e1166b-5b0f-4a8a-909f-b697cd91ec41)

### Station Popup

Click on a station marker to view basic details:

![Station Popup](https://github.com/user-attachments/assets/75fb4351-35c2-4569-9965-d5b77809ec11)

Stations with errors display warnings:

![Station Errors](https://github.com/user-attachments/assets/75346cc6-950e-4441-a3e9-ed59635c61d1)

---

## Station Detail Interface

View comprehensive information about individual stations.

### Information Summary

- **Station Code**: Four-letter identifier
- **Network**: Network code
- **Country**: Country code
- **Coordinates**: Latitude, longitude, and height
- **Last Gaps Update**: When the station was last checked for RINEX/metadata gaps

### Sidebar Navigation

| Section | Description |
|---------|-------------|
| Information | Station metadata (station information) |
| Metadata | Additional station details |
| Visits | Site visit logs and records |
| Rinex | RINEX data files |
| People | Personnel associated with station |

![Station Detail](https://github.com/user-attachments/assets/e0209616-f70c-4c93-acfc-140bbf0591d0)

---

## Equipment and Antenna Information

Track equipment configurations including receivers, antennas, and operational dates.

### Data Columns

| Column | Description |
|--------|-------------|
| RX Code | Receiver model |
| RX Serial | Receiver serial number |
| RX FW | Receiver firmware |
| ANT Code | Antenna model code |
| ANT Serial | Antenna serial number |
| Height | Height relative to reference point |
| North/East | Offset values |
| HC | Height code (e.g., DHARP) |
| RAD | Radome code |
| Date Start/End | Operational period |

![Equipment Interface](https://github.com/user-attachments/assets/97645104-db5c-4480-b536-195789c14453)

### Editing Equipment

Use the pencil icon to modify existing entries or the Add button for new records.

When you upload a station.info file for a station, GeoDE imports rows whose
four-character code matches that station. A file with no matching records
returns a validation error and creates no equipment history.

![Edit Equipment](https://github.com/user-attachments/assets/5eddbaf3-0145-4976-8150-87897b8ff25c)

---

## Metadata Interface

View and edit detailed station metadata.

### General Information

- **Station Type**: Campaign, Continuous, etc.
- **Monument**: Monument name and picture
- **Status**: Active Online, Active Offline, Destroyed, etc.
- **Battery/Communications**: Status indicators
- **First/Last RINEX**: Data timestamps
- **Navigation File**: KMZ route file

### Coordinates

- **Geodetic**: Latitude, longitude, height
- **Cartesian**: ECEF X, Y, Z values

![Metadata Interface](https://github.com/user-attachments/assets/5f47cbba-d309-441c-8880-32d91339fe75)

---

## Visits Interface

Log field visits with photos, dates, and campaign associations.

### Visit Entry Details

- **Visit Date**: When the visit occurred
- **Campaign**: Associated project/campaign
- **Photos**: Documentation of site conditions

![Visits Interface](https://github.com/user-attachments/assets/98d19c62-760e-47d1-bacc-066e16c9d1ee)

### Adding a Visit

Capture new visits with log sheets, navigation files, and participant information.

![Add Visit](https://github.com/user-attachments/assets/6a49864c-c398-498c-8d6c-b67b1e29409f)

---

## RINEX Interface

Manage RINEX data files and identify inconsistencies.

### Status Indicators

| Indicator | Meaning |
|-----------|---------|
| Yellow `!` | Minor inconsistencies (informational) |
| Red `!` | Missing or incomplete station information (action required) |

### Row Colors

| Color | Meaning |
|-------|---------|
| Gray | Less than 12 hours of data (won't be processed) |
| Green | Complete metadata, no errors |
| Red | Metadata problems requiring attention |
| Light Red | Problems but <12 hours data |

### Actions

| Icon | Action |
|------|--------|
| V | View station information |
| E | Edit station information |
| + | Create new station info from external file or RINEX metadata |
| ↥/↧ | Extend adjacent record to cover this file |

![RINEX Interface](https://github.com/user-attachments/assets/89f4193b-03dd-4ce8-ab89-109c830bf9a7)

### RINEX Filters

Filter by time, equipment, or completion:

![RINEX Filters](https://github.com/user-attachments/assets/152bd3a2-ddb4-4aab-9ae0-afa235ee1dcc)
