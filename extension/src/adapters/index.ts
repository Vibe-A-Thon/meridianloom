/**
 * F1 Workstream A tasks 2–4 surface (FR-M34-02/03/04): adapter = ACP agent +
 * Meridian governance manifest. No bespoke agent protocol exists anywhere —
 * the wire is ACP, governance is declared data.
 */
export {
  PERMISSION_KINDS,
  parseAdapterManifest,
  validateAdapterManifest,
  type AdapterManifest,
  type AutonomyTier,
  type ManifestValidation,
  type PermissionKind,
  type Provenance,
  type TrainableSurface,
} from './manifest';
export {
  discoverAdapters,
  TIER_PRECEDENCE,
  type AdapterFs,
  type AdapterTier,
  type DiscoveredAdapter,
  type DiscoveryResult,
  type DiscoveryRoots,
  type InvalidAdapter,
} from './discovery';
export { AdapterRegistry, type AdapterRegistryOptions, type WatcherFactory } from './registry';
export {
  ProbationTracker,
  type AdapterState,
  type ProbationRecord,
  type ProbationResult,
} from './probation';
export { launchAdapter, type AdapterSession, type LaunchOptions } from './launch';
export {
  ACP_REGISTRY_DEFAULT_URL,
  AcpRegistrySource,
  mapRegistryEntryToManifest,
  parseRegistryIndex,
  type RegistryEntry,
  type RegistryMapResult,
  type RegistryParseResult,
  type RegistrySourceOptions,
  type RegistryStatus,
} from './registry-source';
