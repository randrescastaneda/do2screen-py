# API Reference

Auto-generated from source docstrings.

---

## `trace`

::: do2screen.trace.trace

## CLI

::: do2screen.cli.main

## Project Tracing

The three project functions return the same `TraceResult` contract as `trace()`.
They differ only in ingestion: explicit file lists and manifests are ordered;
directory discovery is deterministic but unordered.

::: do2screen.trace.trace_files

::: do2screen.trace.trace_directory

::: do2screen.trace.trace_manifest

---

## Models

### TraceResult

::: do2screen.models.TraceResult

---

### LineRange

::: do2screen.models.LineRange

---

### RangeAttribution

::: do2screen.models.RangeAttribution

---

### VariableTrace

::: do2screen.models.VariableTrace

---

### UnresolvedBlock

::: do2screen.models.UnresolvedBlock

---

### SourceProvenance

::: do2screen.models.SourceProvenance

---

### VariableContext

::: do2screen.models.VariableContext

---

### VariableIdentity

::: do2screen.models.VariableIdentity

---

### ProjectDiagnostic

::: do2screen.models.ProjectDiagnostic

---

## Exceptions

### RegistryIncompatibilityError

::: do2screen.registry.RegistryIncompatibilityError
