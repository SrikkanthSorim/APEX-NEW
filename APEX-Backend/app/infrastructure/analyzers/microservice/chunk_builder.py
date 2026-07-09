"""Classifies scanned Java classes and groups them into business "chunks".

A chunk is formed per REST controller (matching the product's flowchart:
"Identify All Controllers" -> "Iterate Through Each Controller -> Form
Chunks"): starting from the controller, its dependency graph is walked to
pull in the services/repositories/entities it actually uses — real coupling
data from the source, not naming guesses alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.infrastructure.analyzers.microservice.java_class_scanner import JavaClassInfo

_REPOSITORY_BASES = {
    "JpaRepository",
    "CrudRepository",
    "PagingAndSortingRepository",
    "MongoRepository",
    "ReactiveCrudRepository",
    "ReactiveMongoRepository",
}

_CONTROLLER_SUFFIX_RE = re.compile(r"Controller$")
_ROLE_SUFFIXES = {
    "repository": ("Repository", "Repo", "Dao"),
    "service": ("ServiceImpl", "Service", "Manager"),
    "entity": ("Entity",),
}


def classify_role(cls: JavaClassInfo) -> str:
    if "RestController" in cls.annotations or "Controller" in cls.annotations:
        return "controller"
    if cls.class_name.endswith("Controller"):
        return "controller"

    if "Repository" in cls.annotations or (cls.extends and cls.extends in _REPOSITORY_BASES):
        return "repository"
    if any(cls.class_name.endswith(suffix) for suffix in _ROLE_SUFFIXES["repository"]):
        return "repository"

    if "Service" in cls.annotations:
        return "service"
    if any(cls.class_name.endswith(suffix) for suffix in _ROLE_SUFFIXES["service"]):
        return "service"

    if "Entity" in cls.annotations or "Document" in cls.annotations:
        return "entity"
    if cls.class_name.endswith("Entity"):
        return "entity"

    return "other"


@dataclass
class ModuleChunk:
    chunk_name: str
    base_name: str
    controller: JavaClassInfo
    services: list[JavaClassInfo] = field(default_factory=list)
    repositories: list[JavaClassInfo] = field(default_factory=list)
    entities: list[JavaClassInfo] = field(default_factory=list)

    @property
    def member_names(self) -> set[str]:
        names = {self.controller.class_name}
        names.update(c.class_name for c in self.services)
        names.update(c.class_name for c in self.repositories)
        names.update(c.class_name for c in self.entities)
        return names

    @property
    def all_members(self) -> list[JavaClassInfo]:
        return [self.controller, *self.services, *self.repositories, *self.entities]


def build_chunks(classes: list[JavaClassInfo]) -> list[ModuleChunk]:
    by_name: dict[str, JavaClassInfo] = {cls.class_name: cls for cls in classes}
    roles: dict[str, str] = {cls.class_name: classify_role(cls) for cls in classes}

    controllers = [cls for cls in classes if roles[cls.class_name] == "controller"]
    chunks: list[ModuleChunk] = []
    claimed: set[str] = set()

    for controller in sorted(controllers, key=lambda c: c.class_name):
        base_name = _CONTROLLER_SUFFIX_RE.sub("", controller.class_name) or controller.class_name
        chunk = ModuleChunk(
            chunk_name=f"{base_name} Module",
            base_name=base_name,
            controller=controller,
        )
        claimed.add(controller.class_name)

        # BFS the real dependency graph (not just naming) so a controller's
        # chunk includes whatever services/entities/repositories it actually
        # uses, however many hops away (e.g. Controller -> Service -> Repository).
        frontier = list(controller.dependencies)
        visited = {controller.class_name}
        depth = 0
        while frontier and depth < 4:
            next_frontier: list[str] = []
            for dep_name in frontier:
                if dep_name in visited:
                    continue
                visited.add(dep_name)
                dep_cls = by_name.get(dep_name)
                if dep_cls is None:
                    continue
                dep_role = roles[dep_name]
                if dep_role == "controller":
                    continue  # don't cross into another controller's territory
                if dep_name in claimed:
                    continue  # already owned by an earlier chunk

                if dep_role == "service":
                    chunk.services.append(dep_cls)
                elif dep_role == "repository":
                    chunk.repositories.append(dep_cls)
                elif dep_role == "entity":
                    chunk.entities.append(dep_cls)
                else:
                    continue

                claimed.add(dep_name)
                next_frontier.extend(dep_cls.dependencies)
            frontier = next_frontier
            depth += 1

        chunks.append(chunk)

    return chunks
