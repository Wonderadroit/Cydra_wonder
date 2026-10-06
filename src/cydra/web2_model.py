from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Web2IdentityModel:
    identity_id: str
    label: str
    authenticated: bool = False


@dataclass(frozen=True)
class Web2ResourceModel:
    resource_id: str
    label: str
    owner_identity_id: str | None = None
    identifier: str | None = None


@dataclass(frozen=True)
class Web2EndpointModel:
    endpoint_id: str
    method: str
    path: str
    resource_ids: tuple[str, ...] = ()
    action: str | None = None


@dataclass(frozen=True)
class Web2ObservationModel:
    observation_id: str
    endpoint_id: str
    identity_id: str | None
    status_code: int
    body_sha256: str
    body_length: int
    evidence_id: str


@dataclass(frozen=True)
class Web2AuthorizationRelation:
    relation_id: str
    identity_id: str
    resource_id: str
    expected: str
    evidence_ids: tuple[str, ...] = ()


@dataclass
class Web2TargetModel:
    target: str
    identities: dict[str, Web2IdentityModel] = field(default_factory=dict)
    resources: dict[str, Web2ResourceModel] = field(default_factory=dict)
    endpoints: dict[str, Web2EndpointModel] = field(default_factory=dict)
    observations: list[Web2ObservationModel] = field(default_factory=list)
    authorization: dict[str, Web2AuthorizationRelation] = field(default_factory=dict)

    def add_identity(self, identity: Web2IdentityModel) -> None:
        self._add_unique(self.identities, identity.identity_id, identity)

    def add_resource(self, resource: Web2ResourceModel) -> None:
        if resource.owner_identity_id is not None and resource.owner_identity_id not in self.identities:
            raise ValueError("resource owner must be a modeled identity")
        self._add_unique(self.resources, resource.resource_id, resource)

    def add_endpoint(self, endpoint: Web2EndpointModel) -> None:
        missing = [rid for rid in endpoint.resource_ids if rid not in self.resources]
        if missing: raise ValueError(f"endpoint references unknown resources: {', '.join(missing)}")
        self._add_unique(self.endpoints, endpoint.endpoint_id, endpoint)

    def add_observation(self, observation: Web2ObservationModel) -> None:
        if observation.endpoint_id not in self.endpoints: raise ValueError("observation references an unknown endpoint")
        if observation.identity_id is not None and observation.identity_id not in self.identities: raise ValueError("observation references an unknown identity")
        if any(item.observation_id == observation.observation_id for item in self.observations): raise ValueError(f"duplicate observation: {observation.observation_id}")
        self.observations.append(observation)

    def infer_ownership_authorization(self) -> tuple[Web2AuthorizationRelation, ...]:
        relations = []
        for resource in sorted(self.resources.values(), key=lambda item: item.resource_id):
            if resource.owner_identity_id is None: continue
            for endpoint in sorted(self.endpoints.values(), key=lambda item: item.endpoint_id):
                if resource.resource_id not in endpoint.resource_ids: continue
                relation = Web2AuthorizationRelation(
                    f"auth:{resource.resource_id}:{endpoint.endpoint_id}:{resource.owner_identity_id}",
                    resource.owner_identity_id, resource.resource_id, "allow_owner")
                self.authorization.setdefault(relation.relation_id, relation)
                relations.append(relation)
        return tuple(relations)

    def candidate_cross_identity_pairs(self) -> tuple[tuple[str, str, str], ...]:
        pairs = []
        for resource in sorted(self.resources.values(), key=lambda item: item.resource_id):
            owner = resource.owner_identity_id
            if owner is None: continue
            for identity_id in sorted(self.identities):
                if identity_id != owner: pairs.append((owner, identity_id, resource.resource_id))
        return tuple(pairs)

    @staticmethod
    def _add_unique(store: dict[str, object], key: str, value: object) -> None:
        if not key.strip(): raise ValueError("model identifiers must not be empty")
        if key in store and store[key] != value: raise ValueError(f"conflicting model object: {key}")
        store[key] = value
