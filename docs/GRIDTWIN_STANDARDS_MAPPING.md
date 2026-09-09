# GridTwin safeguard concept mapping

This document is a non-normative design aid. GridTwin Ops has not been assessed,
certified or shown compliant with IEC 62443, NIST CSF 2.0, NIST SP 800-82, a
utility security program, or any regulatory requirement. A demonstrator control
can illustrate a concept without satisfying the corresponding outcome or
requirement in an operating organization.

Authoritative references: [NIST CSF 2.0](https://doi.org/10.6028/NIST.CSWP.29),
[NIST SP 800-82 Rev. 3](https://doi.org/10.6028/NIST.SP.800-82r3), and the
[IEC 62443-3-2 product page](https://webstore.iec.ch/en/publication/30727).

## IEC 62443 concepts

| Demonstrated safeguard | Concept-level relationship | Important missing assurance |
|---|---|---|
| Five logical Compose networks and gateway-only controller conduit | System under consideration, zones and conduits; restricted data flow | No 62443-3-2 risk process, SL-T selection, industrial firewall or assessment |
| Separate human, control, emergency and gateway credentials | Identification/authentication and use-control concepts | No OIDC/IAM, MFA, device certificates or credential lifecycle |
| Input/result digests, physical envelope, server-derived set-points | System-integrity concept | No secure boot, signed software/update path or independent model validation |
| Correlated events and hash-chained GridTwin evidence | Timely-response and audit concepts | No live SIEM, trusted timestamp, signature or WORM store |
| Bounded retries, heartbeat and validated fallback schedule | Resource-availability concept | No functional-safety analysis, redundancy, HIL or failover proof |

The seven IEC 62443-3-3 foundational-requirement themes are used only as a
vocabulary: identification/authentication control, use control, system
integrity, data confidentiality, restricted data flow, timely response to
events and resource availability. No security level is selected or claimed.

## NIST CSF 2.0 functions

| Function | GridTwin evidence | Boundary |
|---|---|---|
| Govern | scope, owners, risk register, dependency/data rules and claim restrictions | No organization-wide policy, profile, tier or risk acceptance |
| Identify | named assets, CIGRE topology, interfaces, threats and residual risks | Inventory covers this repository only |
| Protect | role separation, digest binding, allowlist, envelope validation and segmentation | Shared demo keys and unauthenticated Modbus remain |
| Detect | telemetry/physics residual, constraint disagreement, replay/heartbeat events | Four-sample synthetic evaluation only |
| Respond | deterministic denial, reason codes, correlated audit and recovery choice | No SOC exercise or external communications plan |
| Recover | validated schedule fallback, zero remaining violations, measured objective loss | No physical restoration, backup site or safety authority |

## NIST SP 800-82 Rev. 3 themes

| Guidance theme | Implemented evidence | Residual gap |
|---|---|---|
| OT architecture and asset characterization | data/control-flow diagram, named buses/resources and register map | Synthetic balanced network, no site survey |
| Segmentation and boundary protection | internal Docker networks; only gateway shares PLC zone | Docker networking is not an industrial security appliance |
| Least privilege and access enforcement | role-specific API keys, immutable approval and separate emergency path | No enterprise identity, PAM or certificate authentication |
| Application and command integrity | immutable fixture hash, result hash, freshness/replay and AC constraint gates | No signed commands or authenticated Modbus transport |
| Monitoring and anomaly detection | structured events, physical residual, heartbeat and example Sigma/KQL | No live sensor diversity, SIEM tuning or operational baseline |
| Incident response and recovery | no-frame rejection and safe validated schedule | No field procedure, safety case, RTO/RPO or personnel exercise |

## Claim rule

Use “mapped to concepts from,” “used as a design vocabulary,” or “aligned with
selected guidance themes.” Never shorten this to “IEC 62443 compliant,” “NIST
compliant,” “certified,” “security level achieved,” or equivalent wording.
