# Data Sources — ATKIS Raw Data by State

Reference for downloading ATKIS Basis-DLM raw data per German state. The
object-art schema (ATKIS/AAA catalog) is nationally standardized — only
the download portal, file format, and dataset/layer naming differ between
states. The shared mapping rules from raw ATKIS object classes into
IB-Tool 3's HU/RN/Aux layers are documented once, in
[data-preparation.md → Mapping & Merging](data-preparation.md#5-mapping--merging-into-hu--rn--aux) —
not repeated per state here.

Currently documented: Brandenburg, Sachsen, Sachsen-Anhalt, Berlin.

---

## Brandenburg

| Property | Value |
|---|---|
| Portal | GeoBroker (GeoBasis-DE/LGB) |
| URL | [geobroker.geobasis-bb.de](https://geobroker.geobasis-bb.de/gbss.php?MODE=GetProductInformation&PRODUCTID=6de36219-3e68-489e-8ebc-632e5ffb6dc9) |
| Download format | Shapefile (select "Shape" as the data format) |
| Required datasets / layers | From ATKIS Basis-DLM: **Vegetation**, **Verkehr** (traffic/roads), **Gewässer** (water bodies). From ALKIS: **Gebäude** (buildings) only. |
| Notes | Requires a portal login/registration. Select the study area generously first, then submit the download order — processing time before the data becomes available depends on the requested area size. |

---

## Sachsen

| Property | Value |
|---|---|
| Portal | GeoMIS.Sachsen / Downloadbereich Basis-DLM |
| URL | [geomis.sachsen.de](https://geomis.sachsen.de/geomis-client/?lang=de#/), download: [geodaten.sachsen.de → Downloadbereich Basis-DLM](https://www.geodaten.sachsen.de/downloadbereich-basis-dlm-4168.html), buildings: [geodaten.sachsen.de → Downloadbereich Hausumringe](https://www.geodaten.sachsen.de/downloadbereich-hausumringe-4174.html) |
| Download format | Shapefile |
| Required datasets / layers | Complete Basis-DLM dataset for Saxony — a single download contains all data needed for RN/Aux (no separate layer selection). For the building dataset, download **Hausumringe** (building outlines) separately. |
| Notes | No registration required. The complete-state download is a large file (over 1 GB) — expect a longer download time. |

---

## Sachsen-Anhalt

| Property | Value |
|---|---|
| Portal | Geodatenportal Sachsen-Anhalt — Open Data |
| URL | [geodatenportal.sachsen-anhalt.de → Open Data](https://geodatenportal.sachsen-anhalt.de/gfds/de/gdp-open-data.html) |
| Download format | Shapefile |
| Required datasets / layers | Complete dataset for the whole state, available as a single download (no separate layer selection). For the building dataset, download **Hausumringe** (building outlines). |
| Notes | No registration required — freely accessible Open Data. |

---

## Berlin

| Property | Value |
|---|---|
| Portal | GeoBroker (GeoBasis-DE/LGB) — same portal as [Brandenburg](#brandenburg) |
| URL | [geobroker.geobasis-bb.de](https://geobroker.geobasis-bb.de/gbss.php?MODE=GetProductInformation&PRODUCTID=6de36219-3e68-489e-8ebc-632e5ffb6dc9) |
| Download format | Shapefile (select "Shape" as the data format) |
| Required datasets / layers | From ATKIS Basis-DLM: **Vegetation**, **Verkehr** (traffic/roads), **Gewässer** (water bodies). From ALKIS: **Gebäude** (buildings) only. |
| Notes | Requires a portal login/registration. Select the study area generously first, then submit the download order — processing time before the data becomes available depends on the requested area size. |
