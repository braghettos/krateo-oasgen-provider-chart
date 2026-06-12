# krateo-oasgen-provider-chart

Krateo PlatformOps **oasgen-provider** blueprint — a fork of
[`krateoplatformops/oasgen-provider-chart`](https://github.com/krateoplatformops/oasgen-provider-chart)
packaged as a Krateo blueprint: the upstream Helm chart plus a `values.schema.json` and a
`CompositionDefinition`.

`oasgen-provider` generates **operators from OpenAPI specs**: it turns a `RestDefinition` into
CRDs + a controller, replacing hand-written imperative integrations. The installer uses it (when
`features.oasgenprovider=true`) to stand up the HyperDX provider.

Part of the [krateo-installer](https://github.com/braghettos/krateo-installer) ecosystem.

## What it ships

| Path | Chart | OCI artifact |
|------|-------|--------------|
| `chart/` | `oasgen-provider` (appVersion 0.8.0) | `oci://ghcr.io/braghettos/krateo/oasgen-provider` |
| `crd-chart/` | `oasgen-provider-crd` | `oci://ghcr.io/braghettos/krateo/oasgen-provider-crd` |

## How the installer consumes it

The installer umbrella emits a `CompositionDefinition` that points `core-provider` at the OCI
chart; `core-provider` generates `OasgenProvider.composition.krateo.io` and reconciles one
Composition per instance:

```yaml
apiVersion: core.krateo.io/v1alpha1
kind: CompositionDefinition
metadata:
  name: oasgen-provider
  namespace: krateo-system
spec:
  chart:
    url: oci://ghcr.io/braghettos/krateo/oasgen-provider
    version: "0.9.0"
```

## Local validation

```sh
helm lint chart
helm template smoke chart
```

## Release

Push a semver tag (`X.Y.Z`) — CI packages `chart/` and `crd-chart/` and publishes both to
`oci://ghcr.io/braghettos/krateo`.

## Links

- Installer umbrella: https://github.com/braghettos/krateo-installer
- Upstream: https://github.com/krateoplatformops/oasgen-provider-chart
