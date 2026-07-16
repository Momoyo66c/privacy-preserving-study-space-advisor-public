# License Analysis

Last verified from the locally cloned repository license files: 2026-07-16.

This report is an engineering reuse screen, not legal advice. Preserve the exact upstream license and copyright notices for every reused file, and re-check licenses again before distribution.

## Summary

| Repository | License found | Modification allowed? | Copy into this project? | Notice requirement | GPL/AGPL propagation risk | Decision for this project |
|---|---|---|---|---|---|---|
| SparkFun MLX90640 Arduino Example | Code/firmware: MIT; hardware materials: CC BY-SA 4.0 | Yes | Code may be copied/modified under MIT with notice. Hardware materials require attribution and ShareAlike for adaptations | Keep MIT copyright/license for code; follow CC BY-SA attribution and change indication for hardware materials | No GPL/AGPL; CC BY-SA applies to covered hardware materials | Code may be reused selectively after ESP32 adaptation; do not treat every repository asset as MIT |
| Adafruit CircuitPython MLX90640 | Top-level code license: MIT; per-file SPDX and `LICENSES/` include MIT, CC BY 4.0 and Unlicense for different file categories | Yes, subject to the applicable file license | MIT code may be reused with notice; documentation/assets must follow their per-file license | Preserve SPDX headers and relevant license/copyright text | No GPL/AGPL | Driver may be used on Raspberry Pi; verify the header/license of each copied example or document |
| PiThermalCam | AGPL-3.0 | Yes, under AGPL | Technically yes only if AGPL obligations are accepted; network use can trigger corresponding-source obligations | Keep notices, license and source availability requirements | **High: AGPL network interaction clause** | Reference and independently reimplement only; do not copy server or heatmap code into the formal project by default |
| HLK-LD2450 | MIT | Yes | Yes, with MIT notice | Keep copyright and permission notice | None | Protocol code can be ported selectively, but verify behaviour against vendor protocol documentation |
| Zone Presence Detection LD2450 | GPL-3.0 | Yes, under GPL | Avoid copying into a differently licensed formal firmware/application unless GPL compatibility is intentionally accepted | GPL notice, source and corresponding obligations apply on distribution | **High: GPL copyleft** | Architecture/protocol reference only; independently implement required ESP32 behaviour |
| CrowdAware Node | GPL-3.0 | Yes, under GPL | Avoid copying into formal project unless the combined work is intentionally GPL-compatible | GPL notice, source and corresponding obligations apply on distribution | **High: GPL copyleft** | Algorithm and architecture reference only; independently reimplement on Raspberry Pi 5 |
| Classroom Occupancy | MIT | Yes | Yes, with MIT notice | Keep copyright and permission notice | None | Data schema/notebook ideas may be reused; retain provenance for any copied dataset or code |
| ArduinoJson | MIT | Yes | Yes; normal library dependency or vendored copy is permitted with notice | Keep copyright and permission notice | None | Approved candidate dependency, subject to version/memory tests |
| async-mqtt-client | MIT | Yes | Yes, with MIT notice | Keep copyright and permission notice | None | License permits use, but technical/TLS suitability must be evaluated separately |

## Detailed handling rules

### Permissive repositories

The MIT-licensed code in SparkFun, Adafruit, HLK-LD2450, Classroom Occupancy, ArduinoJson and async-mqtt-client permits use, copying, modification, merging, publication, distribution, sublicensing and sale, provided the copyright and permission notice is included in copies or substantial portions.

Engineering practice:

- Copy only files that are actually needed.
- Retain upstream headers where present.
- Add a `THIRD_PARTY_NOTICES.md` before distributing the formal system.
- Record source URL, commit hash, original path, local destination, changes and applicable license for every vendored file.
- A permissive license does not guarantee technical fitness, security or compatibility.

### SparkFun mixed licensing

`LICENSE.md` separates repository content:

- code, firmware and software: MIT;
- hardware: CC BY-SA 4.0.

Therefore, do not label the whole repository simply “MIT.” Firmware reuse can follow MIT, while covered hardware adaptations require attribution, a license link, change indication and ShareAlike treatment.

### Adafruit per-file licensing

The top-level driver is MIT and carries SPDX markers. The repository also contains separate license texts for some documentation/support files. Check the SPDX header or `.license` sidecar before copying any non-code file. Preserve those markers.

### GPL-3.0 repositories

Zone Presence Detection LD2450 and CrowdAware Node are GPL-3.0. For this preparation phase:

- reading and studying are allowed;
- do not copy source blocks into `esp32/`, `raspberry_pi/`, `laptop/` or `shared/`;
- write a fresh implementation from the protocol/algorithm description and project requirements;
- do not combine GPL code into firmware/backend unless the team deliberately chooses a GPL-compatible distribution model.

### AGPL-3.0 repository

PiThermalCam is AGPL-3.0. Its Flask/network functionality makes the AGPL network-source requirement particularly relevant. The default project decision is:

- use screenshots, behaviour and high-level processing steps as research evidence;
- independently implement matrix normalization, interpolation, colour mapping and dashboard delivery;
- do not import or paste PiThermalCam server/source code into the Laptop backend.

### No-license rule

All nine requested repositories contain a license file. If a future reference repository has no clear license:

- do not assume permission to copy or modify;
- limit use to reading, factual protocol understanding and independently written implementation;
- record “No explicit license” in the manifest.

## Reuse approval matrix

| Reuse action | Default approval |
|---|---|
| Read README, documentation and source to understand behaviour | Allowed |
| Link to an upstream repository in documentation | Allowed |
| Copy a short MIT-licensed code portion with its notice and provenance | Potentially allowed; review necessity and integration |
| Use ArduinoJson as a declared dependency | Allowed after version and memory tests |
| Use Adafruit MLX90640 on Raspberry Pi as a declared dependency | Allowed after hardware/version tests |
| Copy GPL CrowdAware processing code into the Raspberry Pi service | Not approved |
| Copy GPL LD2450 zone firmware into ESP32 firmware | Not approved |
| Copy AGPL PiThermalCam Flask/streaming code into the backend | Not approved |
| Reimplement an algorithm described by GPL/AGPL code without copying expression | Preferred approach; document independent implementation and tests |
| Copy code from an unlicensed future repository | Not approved |

## Required provenance record for future reused files

Before any third-party code enters a formal source directory, record:

1. Repository and URL.
2. Exact commit hash.
3. Original file path.
4. Destination file path.
5. Applicable license and copyright owner.
6. Whether the file was copied, modified, translated or independently reimplemented.
7. Summary of modifications.
8. Location of the retained license/notice.

This prevents untraceable mixing of third-party code and supports a later release audit.
