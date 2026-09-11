---
kind: "skill"
id: "java-spring-gradle"
name: "Java · Spring Boot · Gradle"
description: "Spring Boot service conventions with a Gradle build."
version: "1.0.0"
tags: ["java", "spring", "gradle", "backend"]
---

# Java · Spring Boot · Gradle

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

com.<org>.<service>, layered controller / service / repository; one package per bounded context, not per layer at the top level.

## Build and test

`./gradlew build` · `./gradlew test` · `./gradlew spotlessApply` · `./gradlew bootRun`

## Coding standards and framework idioms

- Constructor injection only. Field injection hides the dependency graph
  and defeats construction in tests.
- `@Transactional` on the service, never the controller, and never across a
  network call.
- DTOs at the boundary; never serialise a JPA entity out of a controller —
  lazy loading turns into an N+1 at the edge of the process.
- Validate with Bean Validation on the DTO, not by hand in the service.
- `Optional` for return values, never for fields or parameters.
- Fail fast at startup: validate configuration with `@ConfigurationProperties`
  and let the context fail rather than discovering it on first request.

## Review checklist

- Is the transaction boundary where the unit of work actually is?
- Is any entity escaping the service layer?
- Does every new endpoint have a validation annotation set and an error mapping?
- Are `@Value` strings actually bound config, or scattered magic?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
