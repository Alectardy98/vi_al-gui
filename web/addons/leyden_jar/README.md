# Leyden Jar browser add-on

- `protocol.js`: native packet framing, UID/matrix gates, mapping/capability
  negotiation and acknowledged settings/readback.
- `provider.js`: Controller, Calibration and Live sensors pages.
- `view.js` / `style.css`: device-layout rendering, matrices and bounded charts.
- `profiles.json`: same identities and dimensions as the desktop add-on.

No private USB handle or desktop helper is used. All exchanges share the
selected WebHID transport and page-operation queue. Configuration writes are
explicit and never retried. Captures stay in bounded RAM; navigation stops
polling. Firmware is unchanged. See the main [web README](../../README.md) for
limits and the controller acceptance checklist.
