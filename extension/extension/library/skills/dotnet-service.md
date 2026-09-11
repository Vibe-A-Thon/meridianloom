---
kind: "skill"
id: "dotnet-service"
name: ".NET Service"
description: "ASP.NET Core service conventions."
version: "1.0.0"
tags: ["dotnet", "csharp", "backend"]
---

# .NET Service

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

One project per bounded context with `*.Tests` alongside; `Program.cs` wires and nothing else.

## Build and test

`dotnet build` · `dotnet test` · `dotnet format` · `dotnet run`

## Coding standards and framework idioms

- Nullable reference types enabled, and warnings not suppressed.
- Async all the way: no `.Result`, no `.Wait()`, no `async void` outside event
  handlers. Each of those is a deadlock waiting for load.
- `CancellationToken` accepted and passed through every async call.
- `IHttpClientFactory` rather than a new `HttpClient` per call — socket
  exhaustion is the classic production failure here.
- Options pattern with validation at startup; fail the host rather than the
  first request.
- `IDisposable` honoured with `using`, including `IAsyncDisposable`.

## Review checklist

- Is there any synchronous wait on async work?
- Is the cancellation token threaded through, or dropped?
- Is configuration validated at startup?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
